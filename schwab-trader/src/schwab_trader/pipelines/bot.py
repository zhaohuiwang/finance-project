# schwab-trader/src/schwab_trader/pipelines/bot.py

import os
import time
import hashlib
import json
import schwabdev
import threading
import yaml

from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.prompt import Confirm

from schwab_trader.config.bot.config import SymbolConfig, TradingConfig
from schwab_trader.utils.db import (
    init_db,
    log_transaction,
    save_state,
    get_last_buy_price,
    load_state,
)
from schwab_trader.orders.utils import get_orders
from schwab_trader.orders.equity import sell_limit_sell_stoplimit_oco_dict
from zoneinfo import ZoneInfo

load_dotenv()
console = Console()


class TradingBot:
    def __init__(self, cfg: TradingConfig, mode: str = "cli"):
        """Initialize client, caches, state flags, and start DB."""
        init_db()
        self.client = schwabdev.Client(
            os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
        )
        self.mode = mode
        self.streamer = schwabdev.Stream(self.client)

        self.risk_config = cfg.risk
        self.symbols_config = cfg.symbols

        self.current_market_prices = {
            sym: None for sym in self.symbols
        }  # in-memory catch stores the latest known market price.
        self.holdings = {}  # symbols in conf.yaml
        self.all_holdings = {}  # all positions in the entire account

        # Duplicate-buy protection + manual approval
        self.auto_buy_allowed = {
            sym: True for sym in self.symbols
        }  # True = next trigger is AUTO
        self.pending_buy_orders = (
            set()
        )  # prevents double-submit while order is in flight

        self.last_holdings_sync = time.time()
        self.first_api_pull = True
        self.holding_sync_interval = (
            60  # 1 minutes, first start has to wait to get values populated
        )
        self.account_cache_ttl = 60

        # live for account_cache_ttl, less frequency to all API
        self._account_snapshot_cache_time = None
        self._account_snapshot_cache = None

        self.lock = (
            threading.RLock()
        )  # ensures only one thread can execute a critical section at a time, and no deadlock
        self.running = True
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        # Open orders cache
        self._open_orders_cache = None
        self._open_orders_cache_time = None
        self.open_orders_cache_ttl = 45  # seconds, 30–90 is a good range

        # Daily risk tracking
        self.daily_start_equity = self.get_account_snapshot()["equity"]
        self.today = date.today()

        # For streamer health monitoring
        self.last_message_time = time.time()  # updated on ANY stream message
        self.stream_heartbeat_interval = 30  # seconds - expected heartbeat freq
        self.stream_silence_threshold = 90  # seconds without message → consider dead
        self.reconnect_cooldown = 10  # min seconds between reconnect attempts
        self.last_reconnect_attempt = 0
        self.stream_running = False  # flag

        # Shutdown config
        self._load_shutdown_config(cfg)
        self._shutdown_timer = None

    @property
    def symbols(self):
        """for easy access self.symbols in a statement like `for sym in self.symbols:`"""
        return list(self.symbols_config.keys())

    # =============================================================
    # ACCOUNT MANAGEMENT (snapshot, holdings, cache invalidation)
    # =============================================================
    def _get_account_hash(self):
        """Retrieve the primary account hashValue (used for all API calls)."""
        accounts = self.client.linked_accounts().json()
        if not accounts:
            raise RuntimeError("No linked accounts found")
        return accounts[0]["hashValue"]

    def invalidate_open_orders_cache(self):
        """Force next get_open_orders() to hit the API (called after every trade)."""
        self._open_orders_cache = None
        self._open_orders_cache_time = 0

    def get_account_snapshot(self):
        """Returns (cached or fresh) account equity, buying power, cash, etc."""
        now = time.time()
        # If self._account_snapshot_cache has been assinged with a value (other than initial None), the API will only be called every account_cache_ttl, less frequently.
        if (
            self._account_snapshot_cache is not None
            and now - self._account_snapshot_cache_time < self.account_cache_ttl
        ):
            account_snapshot = self._account_snapshot_cache

        try:
            acc = self.client.account_details(self.account_hash).json()
            bal = acc.get("securitiesAccount", {}).get("currentBalances", {})

            account_snapshot = {
                "equity": float(
                    bal.get("liquidationValue") or bal.get("equity") or 0.0
                ),
                "cashBalance": float(bal.get("cashBalance") or 0.0),
                "buyingPower": float(bal.get("buyingPower") or 0.0),
                "dayTradingBP": float(bal.get("dayTradingBuyingPower") or 0.0),
                "nonMarginableBP": float(
                    bal.get("buyingPowerNonMarginableTrade") or 0.0
                ),
            }

            self._account_snapshot_cache_time = now
            self._account_snapshot_cache = account_snapshot

        except Exception as e:
            console.print(f"[dim red]Account snapshot failed: {e}[/dim red]")
            account_snapshot = {
                "equity": 0.0,
                "cashBalance": 0.0,
                "buyingPower": 0.0,
                "dayTradingBP": 0.0,
                "nonMarginableBP": 0.0,
            }
        return account_snapshot

    def update_holdings_from_api(self):
        """Sync current positions from Schwab API (called on startup + every 60 s)."""
        try:
            pos = self.client.account_details(
                self.account_hash, fields="positions"
            ).json()
            positions = pos.get("securitiesAccount", {}).get("positions", [])

            new_watched = {}
            new_all = {}
            for p in positions:
                sym = p["instrument"]["symbol"]
                net_change = p["instrument"].get("netChange", 0.0)  # today's $ change
                day_pct = p["currentDayProfitLossPercentage"]  # positional level
                long_qty = float(p.get("longQuantity", 0))
                if long_qty > 0:
                    avg_price = float(p.get("averagePrice") or 0)
                    market_val = float(p.get("marketValue") or 0)
                    current_price = market_val / long_qty if long_qty > 0 else 0.0

                    # Calculate today's % price change
                    if current_price > 0 and (current_price - net_change) != 0:
                        day_pct = (net_change / (current_price - net_change)) * 100
                    else:
                        day_pct = 0.0

                    entry = {
                        "shares": long_qty,
                        "buy_price": avg_price,
                        "current_price": current_price,
                        "day_change_pct": day_pct,  # calculated price %
                    }
                    new_all[sym] = entry
                    if sym in self.symbols_config:
                        new_watched[sym] = entry.copy()

            with self.lock:
                self.holdings = new_watched
                self.all_holdings = new_all
                # unlock auto-buy flag for any watched symbol that is now flat (zero shares, no current position)
                for sym in list(self.auto_buy_allowed.keys()):
                    if sym not in new_watched:
                        self.auto_buy_allowed[sym] = True
                        # clear any lingering pending buy orders
                        self.pending_buy_orders = {
                            t for t in self.pending_buy_orders if t[0] != sym
                        }
        except Exception as e:
            console.print(f"[dim red]Holdings sync failed: {e}[/dim red]")

    def force_sync_holdings(self):
        """Call after any trade fill for instant accuracy."""
        self.update_holdings_from_api()
        self.last_holdings_sync = time.time()

    # =============================================================
    # ORDER QUERYING (open orders + safety checks)
    # =============================================================
    def iter_orders(self, order, cancelable_only=False):
        """
        Recurse through the FULL order tree (TRIGGER → OCO → legs)
        and yield every real trading leg (orderLegCollection).
        The cancelable filter now only affects yielding, never skips recursion.
        """
        # 1. ALWAYS recurse first — never skip subtrees
        for child in order.get("childOrderStrategies", []):
            yield from self.iter_orders(child, cancelable_only=cancelable_only)

        # 2. Only yield if this is an actual trading leg
        if "orderLegCollection" not in order:
            return

        # 3. Apply cancelable filter only here
        if cancelable_only and not order.get(
            "cancelable", True
        ):  # default True if key missing
            return

        # Extract price (handles price, stopPrice, stopLimitPrice, etc.)
        price_value = (
            order.get("price") or order.get("stopPrice") or order.get("stopLimitPrice")
        )
        if price_value is None:
            for k, v in order.items():
                if "price" in k.lower() or "stop" in k.lower():
                    price_value = v
                    break

        legs = [
            {
                "instruction": leg["instruction"],
                "symbol": leg["instrument"]["symbol"],
                "quantity": leg["quantity"],
            }
            for leg in order["orderLegCollection"]
        ]

        yield {
            "orderId": order.get("orderId"),
            "orderType": order.get("orderType"),
            "duration": order.get("duration"),
            "price": price_value,
            "legs": legs,
        }

    def get_open_orders(self):
        """
        Fetch open orders using client.account_orders() and handle both:
        - Simple SINGLE orders
        - orders with childOrderStrategies (brackets)
        Returns flattened list of dicts suitable for table display.
        """

        now = time.time()

        # Return cached result if still fresh
        if (
            self._open_orders_cache is not None
            and now - self._open_orders_cache_time < self.open_orders_cache_ttl
        ):
            return self._open_orders_cache

        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(days=30, hours=0, minutes=0)

        try:
            # Use your confirmed method name
            response = self.client.account_orders(
                self.account_hash,
                fromEnteredTime=from_time,
                toEnteredTime=to_time,
                status="WORKING",
            )
            orders = response.json()

            orders_flat_cancelable = [
                o
                for root in orders
                for o in self.iter_orders(root, cancelable_only=True)
            ]

            displayed = []

            for order in orders_flat_cancelable:
                displayed.append(
                    {
                        "orderId": order.get("orderId", "N/A"),
                        "symbol": order.get("legs")[0].get("symbol"),
                        "quantity": order.get("legs")[0].get("quantity", 0),
                        "price": order.get("price"),
                        "instruction": order.get("legs")[0].get("instruction", "N/A"),
                        "type": order.get("orderType", "N/A"),
                        "duration": order.get("duration", "N/A"),
                    }
                )

            # Update cache
            self._open_orders_cache = displayed
            self._open_orders_cache_time = now

            return displayed

        except Exception as e:
            console.print(f"[red]Failed to fetch open orders: {str(e)}[/red]")
            # Return last known good cache if available, otherwise empty
            return self._open_orders_cache or []

    def has_open_buy_order(self, symbol: str) -> bool:
        """Extra safety net: check Schwab API (cached) for any live BUY order."""
        orders = self.get_open_orders()
        return any(o["symbol"] == symbol and o["instruction"] == "BUY" for o in orders)

    def get_recent_fills(
        self,
        lookback_minutes: int = 60,
        symbol: str | None = None,
        side: str | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        """
        Fetch confirmed filled executions using the reliable get_orders utility.
        Returns sorted list (newest first).
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

        try:
            fills = get_orders(
                hashValue=self.account_hash,
                status="FILLED",
                fromTime=since.isoformat() + "Z",
            )
        except Exception as e:
            console.print(f"[red]Failed to fetch recent fills: {e}[/red]")
            return []

        if symbol:
            fills = [f for f in fills if f.get("symbol", "").upper() == symbol.upper()]

        if side:
            fills = [f for f in fills if f.get("side", "").upper() == side.upper()]

        # Sort by executedTime descending (newest first)
        MIN_DT = datetime.min.replace(
            tzinfo=timezone.utc
        )  # MIN_DT is the earliest possible datetime value in Python, explicitly set to use the UTC timezone. It is used as a default "earliest" timestamp or a sentinel value for comparisons.
        return sorted(
            fills, key=lambda x: x.get("executedTime") or MIN_DT, reverse=True
        )[:max_results]

    # =============================================================
    # RISK MANAGEMENT
    # =============================================================
    def calculate_shares(self, symbol, buy_price):
        """Determine buy quantity: fixed_shares (preferred) or risk-based (currently commented)."""
        cfg: SymbolConfig = self.symbols_config[symbol]
        fixed = cfg.fixed_shares

        if fixed > 0:
            # Manual / fixed mode takes priority
            shares = fixed
            console.print(
                f"[cyan]Using fixed quantity for {symbol}: {shares} shares[/cyan]"
            )
        # else:
        #     # Fall back to risk-based sizing
        #     if buy_price <= 0:
        #         shares = self.risk_config.get("default_shares")
        #     else:
        #         equity = self.get_account_snapshot()["equity"]
        #         risk_dollars = equity * (self.risk_config.get(risk_per_trade_pct") / 100)
        #         stop_pct = cfg.get("stop_loss_pct", 5.0) / 100
        #         stop_distance = buy_price * stop_pct

        #         if stop_distance <= 0:
        #             shares = self.risk_config.get("default_shares")
        #         else:
        #             shares = int(risk_dollars / stop_distance)
        #             shares = max(1, min(shares, 1000))  # safety bounds

        return shares

    def risk_checks_pass(self, symbol):
        """All pre-trade risk validations (daily loss, min equity, max positions, BP)."""
        snapshot = self.get_account_snapshot()
        equity = snapshot["equity"]
        bp = snapshot["buyingPower"]

        if self.trading_paused:
            return False

        # Daily loss limit
        current_equity = self.get_account_snapshot()["equity"]
        daily_pnl_pct = (
            (current_equity - self.daily_start_equity) / self.daily_start_equity * 100
        )
        if daily_pnl_pct <= -self.risk_config.max_daily_loss_pct:
            console.print(
                f"[bold red]🚨 DAILY LOSS LIMIT HIT ({daily_pnl_pct:.1f}%) — TRADING PAUSED[/bold red]"
            )
            self.trading_paused = True
            return False

        # Minimum equity guard
        if current_equity < self.risk_config.min_account_equity:
            console.print(
                f"[bold red]🚨 ACCOUNT BELOW MIN EQUITY (${current_equity:,.0f}) — TRADING PAUSED[/bold red]"
            )
            self.trading_paused = True
            return False

        # Max positions
        if len(self.holdings) >= self.risk_config.max_positions:
            console.print("[yellow]Max positions reached — skipping new buys[/yellow]")
            return False

        # Buying power check - Use real calculated qty instead
        estimated_cost = self.current_market_prices.get(
            symbol, 0
        ) * self.calculate_shares(symbol, self.current_market_prices.get(symbol, 0))

        if bp < estimated_cost * 1.05:
            console.print(
                f"[yellow]Insufficient buying power (${bp:,.0f}) — skipping[/yellow]"
            )
            return False
        return True

    # SUGGESTION: The risk-based sizing code above is commented out.
    # Uncommenting it (and removing the fixed_shares path when you want dynamic sizing)
    # would make position size respect your 1% risk-per-trade rule automatically.

    # =============================================================
    # STREAM HANDLING
    # =============================================================
    def unified_receiver(self, message):
        """Unified callback that routes LEVELONE_EQUITIES or ACCT_ACTIVITY messages."""
        with self.lock:
            self.last_message_time = time.time()

        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                return

        if not isinstance(message, dict):
            return

        if "response" in message:
            return

        data_list = message.get("data", [])
        if not data_list:
            return

        for data_item in data_list:
            service = data_item.get("service")
            if not service:
                continue

            if service == "LEVELONE_EQUITIES":
                self.handle_price_message(data_item)
            elif service in ("ACCT_ACTIVITY", "USER_ACTIVITY"):
                self.handle_account_activity(data_item)

    def handle_price_message(self, item):
        """Update self.current_market_prices from LEVELONE_EQUITIES stream (field 3 = last)."""
        content_list = item.get("content", [])
        if not content_list:
            return

        for content in content_list:
            symbol = content.get("key")
            if symbol not in self.current_market_prices:
                continue

            # prev_close = content.get("16")  # previous close
            last_str = content.get("3")  # last price
            if last_str is not None:
                try:
                    last_price = float(last_str)
                    if last_price > 0:
                        with self.lock:
                            self.current_market_prices[symbol] = last_price
                except (ValueError, TypeError):
                    pass

            # Optional fallback to mid bid/ask if last price is missing
            # (uncomment if you want it)
            # else:
            #     bid = content.get('1')
            #     ask = content.get('2')
            #     if bid is not None and ask is not None:
            #         try:
            #             mid = (float(bid) + float(ask)) / 2
            #             if mid > 0:
            #                 with self.lock:
            #                     self.current_market_prices[symbol] = mid
            #         except:
            #             pass

    def handle_account_activity(self, item):
        content_list = item.get("content", [])
        for content in content_list:
            msg_type = content.get("messageType", "").upper()
            if msg_type not in ("EXECUTION", "FILL", "ORDER_FILL"):
                continue

            # Extract rough info from stream (still useful as fast trigger)
            symbol = content.get("symbol") or content.get("instrument", {}).get(
                "symbol", ""
            )
            if not symbol or symbol not in self.symbols:
                continue

            qty_str = content.get("quantity") or content.get("filledQuantity", "0")
            price_str = content.get("price") or content.get("executionPrice", "0")
            try:
                qty_stream = float(qty_str)
                price_stream = float(price_str)
            except:
                continue

            instruction = content.get("instruction", "").upper()

            lookback = datetime.now(timezone.utc) - timedelta(
                minutes=10
            )  # recent window
            recent_execs = get_orders(
                hashValue=self.account_hash,
                status="FILLED",
                fromEnteredTime=lookback.isoformat() + "Z",
            )

            matched_fill = None
            for execution in recent_execs:  #
                if (
                    execution["symbol"] == symbol
                    and execution["side"]
                    == ("BUY" if instruction in ("BUY", "BUY_TO_COVER") else "SELL")
                    and abs(execution["quantity"] - qty_stream) < 0.01
                ):
                    matched_fill = execution
                    break

            if matched_fill:
                # Use the **API-confirmed** values instead of stream approximation
                qty = matched_fill["quantity"]
                price = matched_fill["price"]
                side = matched_fill["side"]
                order_id = matched_fill["orderId"]
                executed_time = matched_fill["executedTime"]
                note_suffix = f" (API-confirmed at {executed_time})"
            else:
                # Fallback to stream values if API lookup didn't match yet
                qty = qty_stream
                price = price_stream
                side = "BUY" if instruction in ("BUY", "BUY_TO_COVER") else "SELL"
                order_id = None
                note_suffix = " (stream only - no recent API match)"

            console.print(
                f"[dim]{side} fill detected for {symbol} @ ${price:.2f} x {qty} {note_suffix}[/dim]"
            )

            with self.lock:
                if side in ("SELL", "SELL_SHORT"):
                    if symbol in self.holdings:
                        del self.holdings[symbol]
                        log_transaction(
                            action="SELL_FILLED",
                            symbol=symbol,
                            qty=qty,
                            price=price,
                            note=f"OCO fill {note_suffix}",
                            order_id=order_id,
                            order_status="FILLED",
                        )
                        self.auto_buy_allowed[symbol] = True
                        self.force_sync_holdings()

                        # update so that a buy order wont be blocked
                        self.pending_buy_orders = {
                            t for t in self.pending_buy_orders if t[0] != symbol
                        }
                        console.print(
                            f"[dim green]Cleared stale pending buys for {symbol} after sell[/dim green]"
                        )

                elif side in ("BUY", "BUY_TO_COVER"):
                    self.pending_buy_orders.discard((symbol, qty))
                    self.holdings[symbol] = {
                        "shares": qty,
                        "buy_price": price,
                        "limit_price": None,
                        "stop_price": None,
                    }
                    log_transaction(
                        action="BUY_FILLED",
                        symbol=symbol,
                        qty=qty,
                        price=price,
                        note=f"Initial buy fill {note_suffix}",
                        order_id=order_id,
                        order_status="FILLED",
                    )
                    self.submit_sell_bracket_oco(
                        symbol, price, self.symbols_config[symbol].limit_sell_price
                    )
                    self.save_state(symbol, price, qty)
                    self.force_sync_holdings()
                    self.invalidate_open_orders_cache()
                    # # Clear pending
                    # if symbol in self.pending_buy_orders:
                    #     self.pending_buy_orders.remove(symbol)

    def start_stream(self):
        """
        Start (or restart) the streamer and (re)subscribe.
        Ref for level_one_equities: https://schwab-py.readthedocs.io/en/latest/streaming.html#schwab.streaming.StreamClient.LevelOneEquityFields
        #"""
        try:
            # Always stop cleanly if something exists
            if hasattr(self, "streamer") and self.streamer:
                try:
                    self.streamer.stop()
                    console.print("[yellow]Previous streamer stopped[/yellow]")
                except Exception as e:
                    console.print(
                        f"[dim red]Error stopping previous streamer: {e}[/dim red]"
                    )
                time.sleep(1.5)  # Give it time to close sockets cleanly

            # Create a brand new Stream instance every time (avoids stale state)
            self.streamer = schwabdev.Stream(self.client)

            # Start the receiver loop in background
            self.streamer.start(receiver=self.unified_receiver)

            # (Re)subscribe quotes for ALL current symbols
            symbols_str = ",".join(self.symbols)
            if symbols_str:
                self.streamer.send(
                    self.streamer.level_one_equities(
                        symbols_str,
                        "0,1,2,3,4,5,6,7,8,9,10,12,13,14,15,16,17,18",  # full fields as in original
                    )
                )
                console.print(
                    f"[green]Subscribed to LEVELONE_EQUITIES ({len(self.symbols_config)} symbols)[/green]"
                )
            else:
                console.print(
                    "[yellow]No symbols to subscribe — add some first[/yellow]"
                )

            # Always (re)subscribe account activity
            self.streamer.send(
                self.streamer.account_activity("Account Activity", "0,1,2,3")
            )
            console.print("[green]Subscribed to ACCT_ACTIVITY[/green]")

            # Reset heartbeat
            with self.lock:
                self.last_message_time = time.time()

            console.print("[bold green]Stream (re)started successfully[/bold green]")

            # Sell holding shares once the price meet the specification
            self.attach_brackets_to_existing_holdings()

        except Exception as e:
            console.print(f"[bold red]Stream start/restart failed: {e}[/bold red]")

    # =============================================================
    # ORDER PLACEMENT
    # =============================================================
    def attach_brackets_to_existing_holdings(self):
        """Attach OCO brackets to existing holdings that don't have them."""
        console.print("[cyan]Checking and attaching brackets to existing holdings...[/cyan]")
        time.sleep(0.8)                    # small buffer after restart
        self.update_holdings_from_api()    # ensure fresh data
        self.invalidate_open_orders_cache()
        
        open_orders = self.get_open_orders()
        symbols_with_open_sell = {o.get("symbol") for o in open_orders if o.get("instruction") in ("SELL", "SELL_SHORT")}

        with self.lock:
            for symbol, holding in list(self.holdings.items()):
                if symbol not in self.symbols_config:
                    continue
                if symbol in symbols_with_open_sell:
                    continue  # already has bracket

                qty = holding.get("shares", 0)
                if qty <= 0:
                    continue

                buy_price = holding.get("buy_price") or self.current_market_prices.get(symbol, 0)
                if buy_price <= 0:
                    console.print(f"[yellow]Skipping bracket for {symbol} — no valid buy price[/yellow]")
                    continue

                self.submit_sell_bracket_oco(symbol, buy_price, self.symbols_config[symbol].limit_sell_price)
                console.print(f"[green]Attached new bracket to {symbol} ({qty} shares)[/green]")

    def place_buy_order(self, symbol: str, qty: float) -> bool:
        """Submit a MARKET BUY order (used only after all safety checks pass)."""
        if not self.risk_checks_pass(symbol):
            return False

        order = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": qty,  # ← use the passed qty
                    "instrument": {"symbol": symbol, "assetType": "EQUITY"},
                }
            ],
        }

        try:
            resp = self.client.place_order(self.account_hash, order)
            location = resp.headers.get("Location")
            order_id = location.split("/")[-1] if location else None
            log_transaction(
                action="BUY_SUBMITTED",
                symbol=symbol,
                qty=qty,
                price=self.current_market_prices.get(symbol, 0),
                note=f"Risk-sized: {qty} shares | session={order.get('session', 'NORMAL')}",
                order_id=order_id,
                order_status="PENDING",
            )
            console.print(f"[green]BUY SUBMITTED → {qty} shares of {symbol}[/green]")

            self.invalidate_open_orders_cache()
            return True

        except Exception as e:
            console.print(f"[red]Buy failed: {e}[/red]")
            with self.lock:
                self.pending_buy_orders.discard((symbol, qty))  # cleanup
            return False

    def submit_sell_bracket_oco(self, symbol, buy_price, limit_sell_price):
        """Place OCO bracket (LIMIT SELL + STOP LOSS)"""
        cfg: SymbolConfig = self.symbols_config[symbol]
        qty = self.holdings[symbol]["shares"]

        # Confirm the logic here
        # limit_sell_price has high priority, otherwise fallback to limit_sell_pct
        limit_price = (
            limit_sell_price
            if limit_sell_price is not None
            else round(buy_price * (1 + cfg.limit_sell_pct / 100), 2)
        )
        console.print(
            f"[dim cyan]Using limit_price for {symbol}: "
            f"→ sell limit price @ ${limit_sell_price:.2f}[/dim cyan]"
        )
        if cfg.stop_loss_dollar > 0:
            if buy_price > limit_price:
                stop_price = round(limit_price - cfg.stop_loss_dollar, 2)
            else:
                stop_price = round(buy_price - cfg.stop_loss_dollar, 2)
            console.print(
                f"[dim cyan]Using fixed $ stop for {symbol}: "
                f"${cfg.stop_loss_dollar:.2f} below entry → stop @ ${stop_price:.2f}[/dim cyan]"
            )
        else:
            stop_price = round(buy_price * (1 - cfg.stop_loss_pct / 100), 2)
            console.print(
                f"[dim]Using % stop for {symbol}: "
                f"{cfg.stop_loss_pct}% below entry → stop @ ${stop_price:.2f}[/dim]"
            )

        # Prevent invalid stop (shouldn't happen with config validation, but safety)
        if stop_price >= buy_price or stop_price <= 0:
            console.print(
                f"[yellow]Invalid stop price calculated for {symbol} — skipping bracket[/yellow]"
            )
            return

        stoplimit_price = round(stop_price * 0.99, 2)
        # Requirement: order above $1 can be entered in no more than two decimals.

        oco = sell_limit_sell_stoplimit_oco_dict(
            symbol=symbol,
            quantity=qty,
            sell_limit_price=str(limit_price),
            sell_stop_price=str(stop_price),
            sell_stoplimit_price=str(stoplimit_price),
            session_sell_limit="NORMAL",
            session_sell_stoplimit="NORMAL",
            duration="DAY",
        )

        try:
            resp = self.client.place_order(self.account_hash, oco)
            location = resp.headers.get("Location")
            order_id = location.split("/")[-1] if location else None
            self.invalidate_open_orders_cache()  # Invalidate the cache after order
            log_transaction(
                action="OCO_PLACED",
                symbol=symbol,
                qty=qty,
                price=buy_price,
                note=f"Limit ${limit_price:.2f} | Stop ${stop_price:.2f}",
                order_id=order_id,
                order_status="WORKING",
            )
            with self.lock:
                self.holdings[symbol].update(
                    {"limit_price": limit_price, "stop_price": stop_price}
                )
        except Exception as e:
            console.print(f"[red]OCO failed: {e}[/red]")

    def _confirm_manual_buy(self, symbol: str, price: float) -> bool:
        """Ask user in terminal for manual approval when auto_buy_allowed is False."""
        console.print(
            f"[yellow]🚨 BUY TRIGGER {symbol} @ ${price:.2f} — AUTO already used this cycle.[/yellow]"
        )
        return Confirm.ask(
            f"[bold]Approve MANUAL buy for {symbol} now?[/bold]",
            default=False,
            console=console,
        )

    # =============================================================
    # UI / DASHBOARD
    # =============================================================
    def make_dashboard(self):
        """Build the rich live dashboard (positions + open orders + account summary)."""
        equity = self.get_account_snapshot()["equity"]
        daily_pnl = (
            (equity - self.daily_start_equity) / self.daily_start_equity * 100
            if self.daily_start_equity > 0
            else 0
        )

        table = Table(title=f"Schwab Bot ─ {datetime.now().strftime('%H:%M:%S')}")
        table.add_column("Symbol", style="cyan")
        table.add_column("Price", justify="right")
        table.add_column("Position", justify="right")
        table.add_column("Avg Buy", justify="right")
        table.add_column("P/L %", justify="right")
        table.add_column("Status")

        with self.lock:
            for sym in self.symbols:
                price = self.current_market_prices.get(sym)
                h = self.holdings.get(sym, {})
                shares = h.get("shares", 0)
                buy_p = h.get("buy_price")
                pl = ((price - buy_p) / buy_p * 100) if price and buy_p else 0

                status = "HOLDING" if shares > 0 else "WATCHING"
                table.add_row(
                    sym,
                    f"${price:,.2f}" if price else "—",
                    f"{shares:,.0f}",
                    f"${buy_p:,.2f}" if buy_p else "—",
                    f"{pl:+.1f}%",
                    status,
                )

        risk_used = len(self.holdings) / self.risk_config.get("max_positions") * 100
        footer = (
            f"Equity: ${equity:,.0f} | Daily: {daily_pnl:+.1f}% | "
            f"Risk: {risk_used:.0f}% | {'PAUSED' if self.trading_paused else 'ACTIVE'}"
        )

        orders = self.get_open_orders()

        ord_table = Table(title="Open Orders")
        ord_table.add_column("ID", style="dim")
        ord_table.add_column("Sym")
        ord_table.add_column("Qty", justify="right")
        ord_table.add_column("Price")
        ord_table.add_column("Side")
        ord_table.add_column("Type")
        ord_table.add_column("Duration")

        if not orders:
            ord_table.add_row("—", "No open orders", "—", "—", "—", "—", "—")
        else:
            for o in orders[:8]:  # limit clutter
                ord_table.add_row(
                    str(o["orderId"]),
                    o["symbol"],
                    str(o["quantity"]),
                    str(o["price"] or "—"),
                    o["instruction"],
                    o["type"],
                    o["duration"],
                )

        # Small account metrics panel
        acc_panel = Table(title="Account Summary", show_header=False)
        acc_panel.add_column("Metric", style="bold cyan")
        acc_panel.add_column("Value", justify="right")

        snap = self.get_account_snapshot()
        acc_panel.add_row("Equity(Net Liq)", f"${snap['equity']:,.0f}")
        acc_panel.add_row("Cash & Sweep Vehicle", f"${snap['cashBalance']:,.0f}")
        acc_panel.add_row("Buying Power", f"${snap['buyingPower']:,.0f}")
        acc_panel.add_row("Day Trading Buying Power", f"${snap['dayTradingBP']:,.0f}")
        acc_panel.add_row(
            "Non-Marginable Buying Power", f"${snap['nonMarginableBP']:,.0f}"
        )

        # ── All Account Holdings Table ────────────────────────────────────────
        all_table = Table(title="All Account Holdings")
        all_table.add_column("Symbol", style="cyan")
        all_table.add_column("Price", justify="right")
        all_table.add_column("Today's % Chg", justify="right")
        all_table.add_column("Shares", justify="right")
        all_table.add_column("Avg Buy", justify="right")
        all_table.add_column("P/L %", justify="right")
        with self.lock:
            sorted_holdings = sorted(
                self.all_holdings.items(), key=lambda item: item[0]
            )
            for sym, h in sorted_holdings:
                price = self.current_market_prices.get(sym) or h.get("current_price")
                shares = h.get("shares", 0)
                buy_p = h.get("buy_price")
                pl = (
                    round((price - buy_p) / buy_p * 100, 1)
                    if price and buy_p and buy_p > 0
                    else 0.0
                )
                day_chg_pct = h.get("day_change_pct", 0.0)
                day_style = (
                    "green"
                    if day_chg_pct > 0
                    else "red" if day_chg_pct < 0 else "white"
                )

                all_table.add_row(
                    sym,
                    f"{shares:,.0f}",
                    f"${buy_p:,.2f}" if buy_p else "—",
                    f"${price:,.2f}" if price else "—",
                    (
                        f"[{day_style}]{day_chg_pct:+.2f}%[/{day_style}]"
                        if day_chg_pct != 0
                        else "—"
                    ),
                    f"{pl:+.1f}%",
                )

        return Panel(
            Columns([table, all_table, ord_table, acc_panel], equal=True, expand=True),
            title="Dashboard",
            subtitle=footer,
            border_style="blue",
        )

    def monitor_display(self):
        """Display-only thread (used in --mode full). Keeps rich Live updated."""
        last_hash = None
        with Live(console=console, refresh_per_second=4, screen=True) as live:
            while self.running:
                time.sleep(6)
                # daily + sync (identical to logic thread)
                if date.today() != self.today:
                    self.daily_start_equity = self.get_account_snapshot()["equity"]
                    self.today = date.today()
                    self.trading_paused = False
                if self.first_api_pull:
                    self.update_holdings_from_api()
                    self.first_api_pull = False
                now = time.time()
                if now - self.last_holdings_sync > self.holding_sync_interval:
                    self.update_holdings_from_api()
                    self.last_holdings_sync = now

                with self.lock:
                    holdings_copy = dict(self.holdings)
                    prices_copy = dict(self.current_market_prices)
                    view = {}
                    for sym in self.symbols:
                        p = prices_copy.get(sym)
                        h = holdings_copy.get(sym, {})
                        view[sym] = (p, h.get("shares", 0), h.get("buy_price"))
                    view["equity"] = self.get_account_snapshot()["equity"]
                    view["paused"] = self.trading_paused
                    view["orders"] = len(self.get_open_orders())

                state_str = str(sorted(view.items()))
                current_hash = hashlib.md5(state_str.encode()).hexdigest()

                if current_hash != last_hash:
                    last_hash = current_hash
                    live.update(self.make_dashboard())

    # =============================================================
    # MONITORING LOGIC (core buy-trigger loop)
    # =============================================================
    def monitor_logic(self):
        """Pure background logic thread (runs every 6 s). Handles all buy triggers."""
        while self.running:
            time.sleep(6)

            if date.today() != self.today:
                self.daily_start_equity = self.get_account_snapshot()["equity"]
                self.today = date.today()
                self.trading_paused = False

            if self.first_api_pull:
                self.update_holdings_from_api()
                self.first_api_pull = False
            now = time.time()
            if now - self.last_holdings_sync > self.holding_sync_interval:
                self.update_holdings_from_api()
                self.last_holdings_sync = now

            with self.lock:
                holdings_copy = dict(self.holdings)
                pending_copy = set(self.pending_buy_orders)
                auto_copy = dict(self.auto_buy_allowed)
                prices_copy = dict(self.current_market_prices)

            # ── Buy trigger logic ──
            for sym in self.symbols:
                if sym in holdings_copy and holdings_copy[sym].get("shares", 0) > 0:
                    continue
                price = prices_copy.get(sym)
                if not price:
                    continue
                cfg: SymbolConfig = self.symbols_config.get(sym)
                if not cfg:
                    continue
                last_buy = get_last_buy_price(sym)
                trigger = price <= cfg.buy_target_price or (
                    last_buy and price <= last_buy * (1 - cfg.buy_drop_pct / 100)
                )

                if not (
                    trigger and not self.trading_paused and self.risk_checks_pass(sym)
                ):
                    continue

                console.print(f"[bold red]BUY TRIGGER {sym} @ ${price:.2f}[/bold red]")

                qty = self.calculate_shares(sym, price)

                if (sym, qty) in pending_copy or self.has_open_buy_order(sym):
                    console.print(
                        f"[dim yellow]Order already pending/open for {sym} — skipping[/dim yellow]"
                    )
                    continue

                if auto_copy[sym]:
                    approved = True
                else:
                    approved = self._confirm_manual_buy(sym, price)

                if approved:
                    with self.lock:
                        self.pending_buy_orders.add((sym, qty))
                    success = self.place_buy_order(sym, qty)
                    if success:
                        with self.lock:
                            self.auto_buy_allowed[sym] = False
                            # REMOVED: self.last_buy_time (unused – we use DB)
                    else:
                        with self.lock:
                            self.pending_buy_orders.discard((sym, qty))
                else:
                    console.print("[dim]Manual buy declined.[/dim]")

    def monitor_loop(self):
        """Legacy combined monitor (display + logic). No longer used — kept for reference only."""
        last_hash = None

        with Live(console=console, refresh_per_second=4, screen=True) as live:
            while self.running:
                time.sleep(6)

                if date.today() != self.today:  # in case of overnight runs
                    self.daily_start_equity = self.get_account_snapshot()["equity"]
                    self.today = date.today()
                    self.trading_paused = False

                # only sync after holding_sync_interval
                if self.first_api_pull:  # No waiting when first start
                    self.update_holdings_from_api()
                    self.first_api_pull = False
                now = time.time()
                if now - self.last_holdings_sync > self.holding_sync_interval:
                    self.update_holdings_from_api()
                    self.last_holdings_sync = now

                with self.lock:
                    # # Copy all mutable state UNDER LOCK so streamer thread can't change it while we decide
                    holdings_copy = dict(self.holdings)
                    pending_copy = set(self.pending_buy_orders)
                    auto_copy = dict(self.auto_buy_allowed)
                    prices_copy = dict(self.current_market_prices)

                    view = {}
                    for sym in self.symbols:
                        p = prices_copy.get(sym)
                        h = holdings_copy.get(sym, {})
                        view[sym] = (p, h.get("shares", 0), h.get("buy_price"))

                    view["equity"] = self.get_account_snapshot()["equity"]
                    view["paused"] = self.trading_paused
                    view["orders"] = len(self.get_open_orders())

                state_str = str(sorted(view.items()))
                current_hash = hashlib.md5(state_str.encode()).hexdigest()

                if current_hash != last_hash:
                    last_hash = current_hash
                    live.update(self.make_dashboard())

                    # Buy logic (only when changed or periodically)
                    for sym in self.symbols:
                        if (
                            sym in holdings_copy
                            and holdings_copy[sym].get("shares", 0) > 0
                        ):
                            continue

                        price = prices_copy.get(sym)
                        if not price:
                            continue

                        cfg: SymbolConfig = self.symbols_config.get(sym)
                        if not cfg:
                            continue
                        last_buy = get_last_buy_price(sym)
                        trigger = (price <= cfg.buy_target_price or float("inf")) or (
                            last_buy
                            and price <= last_buy * (1 - cfg.buy_drop_pct / 100)
                        )

                        if not (
                            trigger
                            and not self.trading_paused
                            and self.risk_checks_pass(sym)
                        ):
                            continue

                        console.print(
                            f"[bold red]BUY TRIGGER {sym} @ ${price:.2f}[/bold red]"
                        )

                        # Decide quantity
                        qty = self.calculate_shares(
                            sym, price
                        )  # ← your existing function

                        # Check if this exact (symbol, qty) is already pending
                        if (sym, qty) in pending_copy:
                            console.print(
                                f"[dim yellow]Exact same order ({sym}, {qty} shares) already pending — skipping[/dim yellow]"
                            )
                            continue
                        if self.has_open_buy_order(sym):
                            console.print(
                                f"[dim yellow]Open BUY order already exists for {sym} — skipping[/dim yellow]"
                            )
                            continue

                        # Decide AUTO vs MANUAL
                        if auto_copy[sym]:
                            console.print(
                                f"[green]→ AUTO BUY allowed for {sym}[/green]"
                            )
                            approved = True
                        else:
                            approved = self._confirm_manual_buy(sym, price)

                        if approved:
                            with self.lock:
                                self.pending_buy_orders.add((sym, qty))

                            success = self.place_buy_order(
                                sym, qty
                            )  # ← pass qty explicitly (see next step)

                            if success:
                                with self.lock:
                                    self.auto_buy_allowed[sym] = False
                                    self.last_buy_time[sym] = time.time()
                            else:
                                with self.lock:
                                    self.pending_buy_orders.discard(
                                        (sym, qty)
                                    )  # rollback on failure
                        else:
                            console.print(f"[dim]Manual buy declined.[/dim]")

    def cli_loop(self):
        """
        CLI command loop (add/remove/update/pause/stop/etc.) — runs in its own thread.
        add and remove commands
            update in-memory config, affect monitoring loop (buy/sell triggers), updates streaming subscription, affect trading logic, persis to conf.yaml.
        reload-config command
            can be applied after you updated any values in the conf.yaml file, like limit price, stop price etc.


        """
        console.print(
            "[bold cyan]CLI mode active - type 'help' for commands[/bold cyan]"
        )
        while self.running:
            try:
                cmd_line = input("> ").strip()
                if not cmd_line:
                    continue
                parts = cmd_line.split(maxsplit=1)
                command = parts[0].lower()

                if command == "help":
                    console.print("""Available commands:
    help                        Show this help
    list                        List currently monitored symbols
    config                      Show current full configuration
    add SYMBOL {json}           Add a new symbol with config
    update SYMBOL {json}        Update config for existing symbol
    remove SYMBOL               Remove a symbol from monitoring
    attach-brackets [SYMBOL]    Attach OCO brackets to current holdings
    pause                       Pause new buy orders
    resume                      Resume trading
    reload-config               Reload (updated) configuration from conf.yaml
    stop                        Gracefully stop the bot (Cancel open orders, UI stays active)
    restart                     Restart streaming and threads
    
    Ctl + c or z                Shut down the bot completely
    lsof -i :8050               Clean up localHost  
    kill -i <pid>
                    """)
                    continue

                elif command == "list":
                    with self.lock:
                        active = (
                            ", ".join(sorted(self.symbols_config.keys())) or "(none)"
                        )
                    console.print(f"[cyan]Currently monitoring: {active}[/cyan]")
                    continue

                elif command == "add":
                    if len(parts) < 2:
                        console.print(
                            "[yellow]Usage: add SYMBOL {json-config-dict}[/yellow]\n"
                            'Example: add AAPL {"buy_target_price": 10.0, "limit_sell_price": 25.0, '
                            '"buy_drop_pct": 5.0, "limit_sell_pct": 10.0, "stop_loss_pct": 5.0, "fixed_shares": 10}'
                        )
                        continue
                    try:
                        rest = parts[1]
                        sym_part, json_part = rest.split(" ", 1)
                        sym = sym_part.strip().upper()
                        cfg_dict = json.loads(json_part.strip())
                        cfg = SymbolConfig(**cfg_dict)
                        self.add_new_symbol(sym, cfg)
                    except Exception as e:
                        console.print(f"[red]Add error: {e}[/red]")
                        console.print(
                            "[yellow]Make sure there's a SPACE between SYMBOL and the {json} part[/yellow]"
                        )
                    continue

                elif command == "update":
                    if len(parts) < 2:
                        console.print(
                            "[yellow]Usage: update SYMBOL {new-json-config}[/yellow]\n"
                            'Example: update IREN {"buy_target_price": 0.75, "limit_sell_price": 80.0}'
                        )
                        continue
                    try:
                        rest = parts[1]
                        sym_part, json_part = rest.split(" ", 1)
                        sym = sym_part.strip().upper()
                        if sym not in self.symbols_config:
                            console.print(
                                f"[red]{sym} not found — use 'add' to create it[/red]"
                            )
                            continue
                        cfg_dict = json.loads(json_part.strip())
                        new_cfg = SymbolConfig(**cfg_dict)
                        with self.lock:
                            old_cfg = self.symbols_config[sym]
                            self.symbols_config[sym] = new_cfg
                        console.print(
                            f"[green]Updated {sym}:[/green]\n"
                            f" Old → {old_cfg.model_dump()}\n"
                            f" New → {new_cfg.model_dump()}"
                        )
                        self.save_config_to_yaml()
                        # Re-attach bracket if holding
                        if (
                            sym in self.holdings
                            and self.holdings[sym].get("shares", 0) > 0
                        ):
                            console.print(
                                f"[cyan]Re-attaching bracket to existing {sym} position[/cyan]"
                            )
                            buy_price = self.holdings[sym].get(
                                "buy_price", self.current_market_prices.get(sym, 0)
                            )
                            if buy_price > 0:
                                self.submit_sell_bracket_oco(
                                    sym,
                                    buy_price,
                                    self.symbols_config[sym].limit_sell_price,
                                )
                            else:
                                console.print(
                                    f"[yellow]No valid buy price for {sym} — bracket not re-attached[/yellow]"
                                )
                    except Exception as e:
                        console.print(f"[red]Update failed: {e}[/red]")
                    continue

                elif command == "remove":
                    if len(parts) < 2:
                        console.print("[yellow]Usage: remove SYMBOL[/yellow]")
                        continue
                    sym = parts[1].strip().upper()
                    self.remove_symbol(sym)
                    continue

                elif command == "attach-brackets":
                    if len(parts) > 1:
                        sym = parts[1].strip().upper()
                        if (
                            sym in self.holdings
                            and self.holdings[sym].get("shares", 0) > 0
                        ):
                            buy_price = self.holdings[sym].get(
                                "buy_price", self.current_market_prices.get(sym, 0)
                            )
                            if buy_price > 0:
                                self.submit_sell_bracket_oco(
                                    sym,
                                    buy_price,
                                    self.symbols_config[sym].limit_sell_price,
                                )
                                console.print(
                                    f"[green]Bracket attached to {sym}[/green]"
                                )
                            else:
                                console.print(
                                    f"[yellow]No buy price available for {sym}[/yellow]"
                                )
                        else:
                            console.print(
                                f"[yellow]No current position in {sym}[/yellow]"
                            )
                    else:
                        self.attach_brackets_to_existing_holdings()
                        console.print(
                            "[green]Checked and attached brackets where needed[/green]"
                        )
                    continue

                elif command == "fills":
                    if len(parts) < 2:
                        console.print(
                            "[yellow]Usage: fills [SYMBOL] [minutes-back (default 60)][/yellow]"
                        )
                        return
                    sym = None
                    mins = 60
                    try:
                        if len(parts) >= 2:
                            sym = parts[1].strip().upper()
                        if len(parts) >= 3:
                            mins = int(parts[2])
                    except ValueError:
                        console.print("[red]Invalid minutes value[/red]")
                        return
                    fills = self.get_recent_fills(lookback_minutes=mins, symbol=sym)
                    if not fills:
                        console.print(
                            "[yellow]No fills found in the selected period.[/yellow]"
                        )
                        return
                    console.print(
                        f"[bold cyan]Recent fills ({len(fills)} found):[/bold cyan]"
                    )
                    for f in fills:
                        t = f.get("executedTime", "—")
                        console.print(
                            f" {t} | {f['side']:4} {f['quantity']:>6.0f} {f['symbol']:6} "
                            f"@ ${f['price']:>7.2f} (order {f.get('orderId','—')}) "
                            f"[{f.get('note','—')}]"
                        )
                    continue

                elif command in ("pause", "resume"):
                    self.trading_paused = command == "pause"
                    console.print(
                        "[yellow]Trading paused (no new buys)[/yellow]"
                        if self.trading_paused
                        else "[green]Trading resumed[/green]"
                    )
                    continue

                elif command == "stop":
                    self.graceful_shutdown()
                    # break

                elif command == "restart":
                    self.restart()
                    continue

                elif command in ("reload-config", "reload"):
                    try:
                        config_path = Path(__file__).parents[3] / "conf/bot/conf.yaml"
                        console.print(f"[yellow]Reloading configuration from: {config_path.resolve()}[/yellow]")

                        new_cfg = TradingConfig.load_from_file(config_path)

                        # Apply new shutdown settings
                        self._load_shutdown_config(new_cfg)

                        # Update symbol configuration (no cancellation here)
                        new_symbols = set(new_cfg.symbols.keys())

                        with self.lock:
                            old_symbols = set(self.symbols_config.keys())
                            self.symbols_config = new_cfg.symbols

                            # Add new symbols
                            for sym in new_symbols - old_symbols:
                                self.current_market_prices[sym] = None
                                self.auto_buy_allowed[sym] = True

                            # Clean removed symbols
                            for sym in old_symbols - new_symbols:
                                self.current_market_prices.pop(sym, None)
                                self.auto_buy_allowed.pop(sym, None)
                                self.pending_buy_orders = {(s, q) for s, q in self.pending_buy_orders if s != sym}

                        # Re-attach brackets using NEW config (will be done again cleanly in restart)
                        self.attach_brackets_to_existing_holdings()

                        # Summary
                        console.print("[bold green]Configuration reloaded successfully![/bold green]")
                        console.print(f"Active symbols : {', '.join(sorted(self.symbols)) or '(none)'}")
                        console.print(f"Auto-shutdown  : {'ENABLED' if self.auto_shutdown_after_close else 'DISABLED'} "
                                      f"(buffer: {self.shutdown_buffer_minutes} min)")

                        # Restart bot — this will cleanly cancel old orders once, then re-attach fresh brackets
                        console.print("[yellow]Restarting bot to apply new config and refresh orders/streamer...[/yellow]")
                        time.sleep(1.0)
                        self.restart()

                    except Exception as e:
                        console.print(f"[bold red]Reload failed: {e}[/bold red]")
                        console.print("[dim]Manual 'restart' recommended if brackets look wrong.[/dim]")
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                console.print(f"[dim red]CLI error: {e}[/dim red]")

    def stream_watchdog(self):
        """Background thread: monitors stream health and auto-reconnects if silent too long."""
        console.print("[dim cyan]Streamer watchdog started[/dim cyan]")

        while self.running:
            time.sleep(10)

            if not self.running:
                break

            now = time.time()
            time_since_last = now - self.last_message_time

            if now - self.last_reconnect_attempt < self.reconnect_cooldown:
                continue

            if time_since_last > self.stream_silence_threshold:
                console.print(
                    f"[bold yellow]Stream silence ({time_since_last:.0f}s) → reconnecting[/bold yellow]"
                )
                self.last_reconnect_attempt = now

                try:
                    self.start_stream()  # ← now handles stop + new instance + subs
                except Exception as e:
                    console.print(f"[red]Watchdog reconnect failed: {e}[/red]")

    # =============================================================
    # DYNAMIC SYMBOL MANAGEMENT
    # =============================================================
    def save_config_to_yaml(self):
        """Persist current symbols_config back to conf.yaml"""
        console.print("[dim]Saving updated config to conf_insession.yaml...[/dim]")
        try:
            path = Path(__file__).parents[3] / "conf/bot/conf_insession.yaml"
            data = {
                "symbols": {
                    sym: cfg.model_dump() for sym, cfg in self.symbols_config.items()
                },
                "risk": self.risk_config.model_dump(),
            }
            with open(path, "w") as f:
                yaml.safe_dump(data, f, sort_keys=False)
            console.print("[green]Configuration saved to conf_insession.yaml[/green]")
        except Exception as e:
            console.print(f"[red]Failed to save config: {e}[/red]")

    def add_new_symbol(self, symbol: str, cfg: SymbolConfig):
        """Add a symbol dynamically"""

        if symbol in self.symbols_config:
            console.print(f"[yellow]{symbol} already exists[/yellow]")
            return

        with self.lock:
            self.symbols_config[symbol] = (
                cfg  # Now new symbol added to in-memory configuration
            )
            self.current_market_prices[symbol] = (
                None  # ready to receive real-time prices
            )
            self.auto_buy_allowed[symbol] = True  # can auto-buy once

        try:
            self.streamer.send(
                self.streamer.level_one_equities(symbol, "0,1,2,3,4,5,6,7,8")
            )
            console.print(f"[green]✅ Added {symbol} and subscribed[/green]")
            self.save_config_to_yaml()  # the change is persisted to disk

        except Exception as e:
            console.print(f"[red]Stream subscribe failed: {e}[/red]")

    def remove_symbol(self, symbol: str):
        """Dynamically remove a symbol from monitoring (unsubscribes + cleans up state)"""
        symbol = symbol.upper()

        if symbol not in self.symbols_config:
            console.print(f"[yellow]{symbol} not found[/yellow]")
            return

        with self.lock:

            self.symbols_config.pop(symbol, None)
            self.current_market_prices.pop(symbol, None)
            self.auto_buy_allowed.pop(symbol, None)

            if symbol in self.holdings:
                console.print(
                    f"[yellow]{symbol} has open position (not closing automatically)[/yellow]"
                )

            self.pending_buy_orders = {
                (s, q) for s, q in self.pending_buy_orders if s != symbol
            }

        self.save_config_to_yaml()
        console.print(f"[green]Removed {symbol}[/green]")

    # =============================================================
    # SHUTDOWN & RESTART
    # ============================================================

    def graceful_shutdown(self, reason: str = "User requested"):
        """Gracefully shut down the bot. Safe to call multiple times."""
        if not self.running:
            console.print("[dim yellow]Shutdown already in progress or completed.[/dim yellow]")
            return

        console.print(f"[bold red]=== GRACEFUL SHUTDOWN INITIATED ({reason}) ===[/bold red]")
        self.running = False

        # Cancel all DAY orders
        try:
            console.print("[yellow]Cancelling open DAY orders...[/yellow]")
            open_orders = self.get_open_orders()
            canceled = 0
            for order in open_orders:
                if order.get("duration") == "DAY" and order.get("orderId"):
                    try:
                        self.client.cancel_order(self.account_hash, order["orderId"])
                        console.print(f"[green]✓ Cancelled {order['orderId']} ({order['symbol']})[/green]")
                        canceled += 1
                    except Exception as e:
                        console.print(f"[dim red]Cancel failed for {order.get('orderId')}: {e}[/dim red]")
            if canceled > 0:
                self.invalidate_open_orders_cache()
                console.print(f"[green]Cancelled {canceled} DAY order(s)[/green]")
        except Exception as e:
            console.print(f"[dim red]Error cancelling orders: {e}[/dim red]")

        # Stop streamer
        try:
            if hasattr(self, 'streamer') and self.streamer:
                self.streamer.stop()
                console.print("[yellow]Streamer stopped[/yellow]")
        except Exception as e:
            console.print(f"[dim red]Error stopping streamer: {e}[/dim red]")

        # Log final shutdown
        try:
            equity = self.get_account_snapshot()["equity"]
            log_transaction(
                action="BOT_SHUTDOWN",
                symbol="SYSTEM",
                qty=0,
                price=equity,
                note=f"Shutdown ({reason}) | Equity: ${equity:,.2f}",
                order_id=None,
                order_status="SHUTDOWN"
            )
        except:
            pass

        time.sleep(1.2)
        console.print("[bold green]=== GRACEFUL SHUTDOWN COMPLETED ===[/bold green]")

    def restart(self):
        """Restart the bot cleanly: shutdown → full re-initialization."""
        console.print("[bold yellow]=== RESTARTING BOT ===[/bold yellow]")

        # Perform shutdown ONLY if still running
        if self.running:
            self.graceful_shutdown(reason="Restart requested")
        else:
            console.print("[dim]Bot already stopped — proceeding with restart[/dim]")

        # ── Full re-initialization ─────────────────────────────────────
        with self.lock:
            self.current_market_prices = {sym: None for sym in self.symbols}
            self.holdings = {}
            self.all_holdings = {}
            self.auto_buy_allowed = {sym: True for sym in self.symbols}
            self.pending_buy_orders = set()

        self.running = True
        self.trading_paused = False
        self.first_api_pull = True
        self.last_holdings_sync = time.time()
        self.invalidate_open_orders_cache()
        self._account_snapshot_cache_time = None
        self._account_snapshot_cache = None
        self._open_orders_cache = None
        self._open_orders_cache_time = None

        try:
            self.account_hash = self._get_account_hash()
        except Exception as e:
            console.print(f"[red]Failed to refresh account hash: {e}[/red]")
            return

        # Re-start stream + timer
        try:
            self.start_stream()
            self.start_market_close_timer()        # ← Important: restart timer with latest config
            console.print("[bold green]Bot restarted successfully[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Restart failed: {e}[/bold red]")

    def start_market_close_timer(self):
        """Start (or restart) the configurable auto-shutdown timer based on current config."""
        # Stop any existing timer thread safely
        if (
            hasattr(self, "_shutdown_timer")
            and self._shutdown_timer
            and self._shutdown_timer.is_alive()
        ):
            console.print(
                "[dim yellow]Stopping previous shutdown timer...[/dim yellow]"
            )
            # We can't easily kill daemon threads, so we rely on the flag + new thread

        if not self.auto_shutdown_after_close:  # We'll add this attribute below
            console.print(
                "[yellow]Auto-shutdown after market close is currently DISABLED[/yellow]"
            )
            return

        def shutdown_at_close():
            while self.running:
                try:
                    now_et = datetime.now(ZoneInfo("America/New_York"))

                    # Skip weekends if configured
                    if (
                        not self.shutdown_on_weekends and now_et.weekday() >= 5
                    ):  # Sat=5, Sun=6
                        time.sleep(3600)
                        continue

                    # Calculate shutdown time today (4:00 PM ET + buffer)
                    shutdown_time = now_et.replace(
                        hour=16, minute=0, second=0, microsecond=0
                    )
                    shutdown_time += timedelta(minutes=self.shutdown_buffer_minutes)

                    # If already past today's shutdown time, schedule for tomorrow
                    if now_et > shutdown_time:
                        shutdown_time += timedelta(days=1)

                    seconds_to_wait = (shutdown_time - now_et).total_seconds()

                    console.print(
                        f"[dim cyan]Auto-shutdown timer active → "
                        f"Next shutdown at {shutdown_time.strftime('%Y-%m-%d %H:%M ET')} "
                        f"({int(seconds_to_wait//3600)}h {int((seconds_to_wait%3600)//60)}m)[/dim cyan]"
                    )

                    time.sleep(seconds_to_wait)

                    if self.running and self.auto_shutdown_after_close:
                        console.print(
                            f"[bold red]🛑 Market close + {self.shutdown_buffer_minutes} min buffer reached → initiating graceful shutdown[/bold red]"
                        )
                        self.graceful_shutdown(reason="Market close + buffer")
                        break

                except Exception as e:
                    console.print(f"[red]Shutdown timer error: {e}[/red]")
                    time.sleep(300)  # retry after 5 min

        # Store reference so we can detect/restart it later
        self._shutdown_timer = threading.Thread(
            target=shutdown_at_close, daemon=True, name="MarketCloseAutoShutdown"
        )
        self._shutdown_timer.start()
        console.print(
            f"[bold green]✅ Auto-shutdown timer (re)started — buffer: {self.shutdown_buffer_minutes} min[/bold green]"
        )

    def _load_shutdown_config(self, cfg: TradingConfig):
        """Internal helper to apply shutdown settings from config object."""
        self.auto_shutdown_after_close = cfg.auto_shutdown_after_close
        self.shutdown_buffer_minutes = cfg.shutdown_buffer_minutes
        self.shutdown_on_weekends = cfg.shutdown_on_weekends
