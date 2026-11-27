#!/usr/bin/env python3
"""
Schwabdev tracer + trailing-stop / limit-buy strategy.
- Streams level-one quotes for tracer symbols + the holding.
- Trailing stop on the holding when 1+ tracers exceed upper % limits.
- Limit-buy the holding when tracers are below lower % limits.
- Buy only allowed if current price is sufficiently below the last sell price.
- All fills recorded in SQLite.
- Restricted to configured days-of-week and time window (America/New_York).

Always paper-trade (DRY_RUN=True) first.

During the regualr trading hours (inside the window) the streamer is on and strategy logic is active and it consume low CPU and network. Outsides the window or weekend, the strategy logic is blocked and CPU/network comsumption is near zero (while the streamer.start_auto(...) manages the websocket lifecycle and stop outside the window. Main thread is in an infinite loop doing time.sleep(30).) so it is safe to leave it running 24/7.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import schwabdev
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# CONFIG – edit everything here
# ---------------------------------------------------------------------------
CONFIG = {
    "token_path": Path(
        "~/.schwabdev/tokens.db"
    ).expanduser(),  # The .expanduser() method replaces a leading tilde (~) or ~user in a file path with the user's home directory.
    # Account
    "account_Number": "29308909",  # or hard-code the number string
    # Trading window (America/New_York)
        # Safety / runtime
    "DRY_RUN": True,  # True = log only, never send orders
    "timezone": "America/New_York",
    "trade_days": (0, 1, 2, 3, 4),  # Mon-Fri (0=Mon … 6=Sun)
    "start_time": dtime(9, 35),  # after open
    "stop_time": dtime(15, 55),  # before close
    # Symbols
    "tracer_symbols": [
        "QQQ",
        "$COMPX",
        ],  # symbols we watch for signals
    # "$COMPX" = NASDAQ Composite; change to "$NDX" if you prefer Nasdaq-100
    "holding_symbol": "NBIS",  # the stock we actually trade
    "buy_qty": 1,  # shares per buy
    "sell_qty": 1,  # None = sell entire position
    # Strategy parameters (all percentages are absolute, e.g. 1.5 = 1.5 %)
    "trail_percent": 0.1,  # trailing-stop distance from high-water mark
    # Per-symbol limits
    "tracer_upper_limit_pct": {
        "QQQ": 0.1,
        "$COMPX": .1,
    },# sell if any tracer net-%-change >= this
    "tracer_lower_limit_pct": {
        "QQQ": -0.1,
        "$COMPX": -0.1,
    }, # buy if any tracer net-%-change <= this

    "min_tracers_for_signal": 1,  # 1 or 2 (how many tracers must confirm)
    "rebuy_discount_pct": 0.1,  # buy only if price <= last_sell * (1 - this/100)
    "db_path": "trace_trigger_trades.db",
    "log_level": logging.INFO,
    "stream_fields": "0,1,2,3,8,18,42",  # symbol,bid,ask,last,volume,net change,net % chg
}
# ---------------------------------------------------------------------------
# Globals / state (thread-safe enough for this use-case)
# ---------------------------------------------------------------------------
TZ = ZoneInfo(CONFIG["timezone"])
logger = logging.getLogger("tracer_strategy")
state_lock = threading.Lock()

# Live quotes: symbol -> {last, bid, ask, net_pct, volume, ...}
quotes: Dict[str, Dict[str, float]] = {}

# Position tracking for the holding
position = {
    "qty": 0,
    "avg_cost": 0.0,
    "high_water": 0.0,  # for trailing stop
    "last_sell_price": None,  # used for re-buy guard
    "trailing_stop_active": False,
}

client: Optional[schwabdev.Client] = None
account_Number: Optional[str] = None


def get_hashvalue(client, accountNumber: str = "29308909") -> str:
    """Get account hashValue from its accountNumber."""
    response = client.linked_accounts()
    data = response.json()
    hashValue = next(
        (item["hashValue"] for item in data if item["accountNumber"] == accountNumber),
        None,
    )
    return hashValue


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db(path: str) -> None:
    """
    Initialize the SQLite database and create the transactions table if it does not exist.

    Parameters
    ----------
    path : str
        File path for the SQLite database (e.g. "trades.db").
    """
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,          -- BUY / SELL
            qty REAL NOT NULL,
            price REAL NOT NULL,
            order_id TEXT,
            reason TEXT,
            dry_run INTEGER NOT NULL,
            extra TEXT
        )
        """)
    conn.commit()
    conn.close()


def record_tx(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    order_id: Optional[str],
    reason: str,
    extra: Optional[dict] = None,
) -> None:
    """
    Insert a record into the transactions table.

    Parameters
    ----------
    symbol : str
        Ticker symbol that was traded.
    side : str
        Order side ("BUY" or "SELL").
    qty : float
        Number of shares.
    price : float
        Limit price (or fill price) of the order.
    order_id : Optional[str]
        Broker order ID, or "DRY_RUN" when running in simulation mode.
    reason : str
        Human-readable reason for the trade (e.g. "trailing_stop", "tracer_lower").
    extra : Optional[dict], default None
        Optional additional data stored as JSON.
    """

    conn = sqlite3.connect(CONFIG["db_path"])
    conn.execute(
        """
        INSERT INTO transactions
        (ts, symbol, side, qty, price, order_id, reason, dry_run, extra)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(TZ).isoformat(),
            symbol,
            side,
            qty,
            price,
            order_id,
            reason,
            1 if CONFIG["DRY_RUN"] else 0,
            json.dumps(extra or {}),
        ),
    )
    conn.commit()
    conn.close()
    logger.info(
        "DB recorded: %s %s %.0f @ %.4f  reason=%s  dry_run=%s",
        side,
        symbol,
        qty,
        price,
        reason,
        CONFIG["DRY_RUN"],
    )


# ---------------------------------------------------------------------------
# Time / session helpers
# ---------------------------------------------------------------------------
def in_trading_window() -> bool:
    """
    Check whether the current time falls inside the configured trading window.

    Returns
    -------
    bool
        True if today is an allowed weekday and the current time is between
        start_time and stop_time (in the configured timezone); otherwise False.
    """

    now = datetime.now(TZ)
    if now.weekday() not in CONFIG["trade_days"]:
        return False
    t = now.time()
    return CONFIG["start_time"] <= t <= CONFIG["stop_time"]


# ---------------------------------------------------------------------------
# Order helpers
# ---------------------------------------------------------------------------
def build_limit_order(symbol: str, side: str, qty: float, limit_price: float) -> dict:
    """
    Construct a Schwab-compatible limit-order payload.

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    side : str
        "BUY" or "SELL".
    qty : float
        Number of shares (will be cast to int).
    limit_price : float
        Limit price for the order.

    Returns
    -------
    dict
        Order dictionary ready to be passed to client.place_order().
    """

    instruction = "BUY" if side.upper() == "BUY" else "SELL"
    return {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "price": f"{limit_price:.2f}",
        "orderLegCollection": [
            {
                "instruction": instruction,
                "quantity": int(qty),
                "instrument": {"symbol": symbol, "assetType": "EQUITY"},
            }
        ],
    }


def place_order(
    side: str, qty: float, limit_price: float, reason: str
) -> Optional[str]:
    """
    Place a limit order (or simulate it when DRY_RUN is True) and record the transaction.

    Parameters
    ----------
    side : str
        "BUY" or "SELL".
    qty : float
        Number of shares.
    limit_price : float
        Limit price to use.
    reason : str
        Reason string stored in the database (e.g. "trailing_stop").

    Returns
    -------
    Optional[str]
        Order ID returned by Schwab, "DRY_RUN" in simulation mode, or None if the
        order was skipped (e.g. zero quantity).
    """

    symbol = CONFIG["holding_symbol"]
    if qty <= 0:
        logger.warning("Zero qty – skip order")
        return None

    order = build_limit_order(symbol, side, qty, limit_price)
    logger.info(
        "%s ORDER: %s %s %.0f @ %.2f  reason=%s",
        "DRY-RUN" if CONFIG["DRY_RUN"] else "LIVE",
        side,
        symbol,
        qty,
        limit_price,
        reason,
    )

    if CONFIG["DRY_RUN"]:
        record_tx(symbol, side, qty, limit_price, order_id="DRY_RUN", reason=reason)
        return "DRY_RUN"

    assert client is not None and account_hash is not None
    resp = client.place_order(account_hash, order)
    order_id = None
    if resp is not None:
        # Schwab returns Location header with order id on success
        loc = resp.headers.get("location") or resp.headers.get("Location")
        if loc:
            order_id = loc.rstrip("/").split("/")[-1]
        logger.info(
            "Order response status=%s  order_id=%s",
            getattr(resp, "status_code", None),
            order_id,
        )
    record_tx(
        symbol,
        side,
        qty,
        limit_price,
        order_id,
        reason,
        extra={"raw_status": str(getattr(resp, "status_code", None))},
    )
    return order_id


# ---------------------------------------------------------------------------
# Strategy logic
# ---------------------------------------------------------------------------
def update_trailing_stop(last: float) -> None:
    """
    Update the high-water mark and trailing-stop state for the current position.

    If a long position exists and the latest price is higher than the recorded
    high-water mark, the high-water mark is raised. Trailing-stop mode is
    activated whenever a position is open.

    Parameters
    ----------
    last : float
        Most recent last price of the holding symbol.
    """

    with state_lock:
        if position["qty"] <= 0:
            position["trailing_stop_active"] = False
            position["high_water"] = 0.0
            return
        if last > position["high_water"]:
            position["high_water"] = last
        position["trailing_stop_active"] = True


def check_signals() -> None:
    """
    Evaluate the trading strategy and place orders when conditions are met.

    Logic summary
    -------------
    - Only runs inside the configured trading window.
    - Sells when the trailing stop is hit or enough tracer symbols exceed the
      upper percent-change limit.
    - Buys when enough tracer symbols are below the lower percent-change limit
      and the re-buy discount rule relative to the last sell price is satisfied.
    - Updates the in-memory position state optimistically after each order.
    """

    if not in_trading_window():
        return

    holding = CONFIG["holding_symbol"]
    with state_lock:
        q = quotes.get(holding)
        if not q or "last" not in q:
            return
        last = q["last"]
        bid = q.get("bid", last)
        ask = q.get("ask", last)

        # Collect how many tracers are above/below their own limits
        n_above, n_below, valid_tracers = 0, 0, 0
        tracer_details = []

        for t in CONFIG["tracer_symbols"]:
            tq = quotes.get(t)
            if not tq or "net_pct" not in tq:
                continue

            pct = tq["net_pct"]
            valid_tracers += 1

            upper = CONFIG["tracer_upper_limit_pct"].get(t)
            lower = CONFIG["tracer_lower_limit_pct"].get(t)

            if upper is not None and pct >= upper:
                n_above += 1
            if lower is not None and pct <= lower:
                n_below += 1
            tracer_details.append(f"{t}:{pct:+.2f}%")

        if valid_tracers < CONFIG["min_tracers_for_signal"]:
            return

        # --- SELL / Trailing stop ---
        if position["qty"] > 0 and position["trailing_stop_active"]:
            stop_price = position["high_water"] * (
                1.0 - CONFIG["trail_percent"] / 100.0
            )
            # Also force sell if enough tracers are strongly up
            force_sell = n_above >= CONFIG["min_tracers_for_signal"]
            logger.info(
                "HOLDING %s | qty=%.0f  last=%.2f  high=%.2f  stop=%.2f  | tracers: %s",
                holding, position["qty"], last, position["high_water"], stop_price,
                " | ".join(tracer_details)
            )
            if last <= stop_price or force_sell:
                qty = (
                    position["qty"]
                    if CONFIG["sell_qty"] is None
                    else min(CONFIG["sell_qty"], position["qty"])
                )
                reason = "trailing_stop" if last <= stop_price else "tracer_upper"
                logger.warning(
                    ">>> SELL SIGNAL (%s) | %s %.0f @ ~%.2f | high=%.2f stop=%.2f | tracers above limit: %d",
                    reason, holding, qty, bid, position["high_water"], stop_price, n_above
                )
                place_order("SELL", qty, bid, reason)  # use bid for conservative limit
                # Optimistic local update (real fills would come from account_activity stream)
                position["qty"] -= qty
                if position["qty"] <= 0:
                    position["qty"] = 0
                    position["last_sell_price"] = last
                    position["high_water"] = 0.0
                    position["trailing_stop_active"] = False
                return

        # --- BUY ---
        if position["qty"] == 0 and n_below >= CONFIG["min_tracers_for_signal"]:
            # Re-buy guard
            last_sell = position["last_sell_price"]
            logger.info(
                "NO POSITION | last=%.2f | tracers: %s | below limit: %d",
                last, " | ".join(tracer_details), n_below
            )
            if last_sell is not None:
                max_buy_price = last_sell * (1.0 - CONFIG["rebuy_discount_pct"] / 100.0)
                if last > max_buy_price:
                    logger.info(
                        "Buy blocked by rebuy guard: last=%.2f > max allowed=%.2f (last_sell=%.2f)",
                        last, max_buy_price, last_sell
                    )
                    return

                logger.warning(
                    ">>> BUY SIGNAL (tracer_lower) | %s %.0f @ ~%.2f | tracers below limit: %d",
                    holding, CONFIG["buy_qty"], ask, n_below
                )

            place_order("BUY", CONFIG["buy_qty"], ask, "tracer_lower")
            # Optimistic local update
            position["qty"] = CONFIG["buy_qty"]
            position["avg_cost"] = last
            position["high_water"] = last
            position["trailing_stop_active"] = True


# ---------------------------------------------------------------------------
# Stream handler
# ---------------------------------------------------------------------------
def on_message(message: str) -> None:
    """
    WebSocket message handler for level-one equity updates.

    Parses incoming JSON, updates the global quotes dictionary with the latest
    bid/ask/last/net-percent-change values, maintains the trailing-stop
    high-water mark for the holding, and triggers a strategy evaluation.

    Parameters
    ----------
    message : str
        Raw JSON string received from the Schwab streamer.
    """

    try:
        payload = json.loads(message)
    except Exception:
        return

    data_list = payload.get("data") or []
    for block in data_list:
        if block.get("service") != "LEVELONE_EQUITIES":
            continue
        for item in block.get("content") or []:
            sym = item.get("key")
            if not sym:
                continue
            with state_lock:
                q = quotes.setdefault(sym, {})
                # Field mapping (see schwabdev.stream_fields["LEVELONE_EQUITIES"])
                if "1" in item:  # Bid
                    q["bid"] = float(item["1"])
                if "2" in item:  # Ask
                    q["ask"] = float(item["2"])
                if "3" in item:  # Last
                    q["last"] = float(item["3"])
                if "8" in item:  # Volume
                    q["volume"] = float(item["8"])
                if "18" in item:  # Net Change
                    q["net_change"] = float(item["18"])
                if "42" in item:  # Net Percent Change
                    q["net_pct"] = float(item["42"])
                q["ts"] = time.time()

            # Update trailing high-water for the holding
            if sym == CONFIG["holding_symbol"] and "last" in quotes.get(sym, {}):
                update_trailing_stop(quotes[sym]["last"])

    # After processing a batch, evaluate strategy
    try:
        check_signals()
    except Exception as e:
        logger.exception("Signal check failed: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Entry point of the trading script.

    Performs the following steps:
    1. Loads environment variables and configures logging.
    2. Initializes the SQLite database.
    3. Creates the Schwab client and resolves the account hash.
    4. Loads any existing long position for the holding symbol.
    5. Starts the auto streamer (market-hours aware).
    6. Subscribes to level-one quotes for the holding and tracer symbols.
    7. Keeps the main thread alive while the streamer runs in the background.
    """

    global client, account_hash

    load_dotenv()
    logging.basicConfig(
        level=CONFIG["log_level"],
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Client
    client = schwabdev.Client(
        app_key = os.getenv("SCHWAB_API_KEY") or os.getenv("APP_KEY"),
        app_secret = os.getenv("SCHWAB_API_SECRET") or os.getenv("APP_SECRET"),
        callback_url = os.getenv("SCHWAB_CALLBACK_URL") or os.getenv("CALLBACK_URL"),
        tokens_db=str(CONFIG["token_path"]),
    )

    logger.info("Starting tracer strategy  DRY_RUN=%s", CONFIG["DRY_RUN"])
    
    init_db(CONFIG["db_path"])

    # Resolve account hash
    response = client.linked_accounts()
    data = response.json()
    account_hash = next(
        (item["hashValue"] for item in data if item["accountNumber"] == CONFIG["account_Number"]),
        None,
    )
    logger.info("Using account hash: %s", account_hash)

    # Optional: load existing position (simple version – expand as needed)
    try:
        details = client.account_details(account_hash, fields="positions").json()
        securities = details.get("securitiesAccount", {}).get("positions", [])
        for p in securities:
            inst = p.get("instrument", {})
            if inst.get("symbol") == CONFIG["holding_symbol"]:
                long_qty = float(p.get("longQuantity", 0))
                if long_qty > 0:
                    position["qty"] = long_qty
                    position["avg_cost"] = float(p.get("averagePrice", 0))
                    position["high_water"] = position["avg_cost"]
                    position["trailing_stop_active"] = True
                    logger.info(
                        "Loaded existing position: %.0f shares @ %.2f",
                        long_qty,
                        position["avg_cost"],
                    )
                break
    except Exception as e:
        logger.warning("Could not load positions: %s", e)

    # Streamer
    streamer = schwabdev.Stream(client)
    all_symbols = [CONFIG["holding_symbol"]] + CONFIG["tracer_symbols"]
    symbols_csv = ",".join(all_symbols)

    def handler(msg: str) -> None:
        on_message(msg)

    # Prefer auto start/stop aligned with market hours; we still enforce our tighter window inside check_signals
    streamer.start_auto(
        receiver=handler,
        start_time=dtime(9, 29),
        stop_time=dtime(16, 5),
        on_days=CONFIG["trade_days"],
        now_timezone=TZ,
        daemon=True,
    )

    # Subscribe
    time.sleep(1.5)  # let login complete
    streamer.send(
        streamer.level_one_equities(
            symbols_csv, CONFIG["stream_fields"], command="SUBS"
        )
    )
    logger.info("Subscribed to: %s", symbols_csv)

    # Keep main thread alive
    try:
        while True:
            time.sleep(30)
            # lightweight health log
            with state_lock:
                holding_q = quotes.get(CONFIG["holding_symbol"], {})
                logger.debug(
                    "Heartbeat | holding last=%.2f  qty=%.0f  high_water=%.2f  tracers=%s",
                    holding_q.get("last", 0),
                    position["qty"],
                    position["high_water"],
                    {
                        t: quotes.get(t, {}).get("net_pct")
                        for t in CONFIG["tracer_symbols"]
                    },
                )
    except KeyboardInterrupt:
        logger.info("Shutting down…")
        streamer.stop()


if __name__ == "__main__":
    main()
