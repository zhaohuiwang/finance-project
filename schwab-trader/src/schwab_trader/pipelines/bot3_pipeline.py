# schwab-trader/src/schwab_trader/pipelines/bot3_pipeline.py
"""
Trading pipeline for the Schwab automated trading bot.
This module implements the core trading engine responsible for:
- Connecting to the Schwab API and streaming market/account events.
- Synchronizing account holdings and open orders.
- Automatically placing market buy orders when configured entry
  conditions are met.
- Managing open positions with OCO (One Cancels Other) exit orders.
- Applying configurable risk management rules.
- Supporting hot-reloading of trading configuration during runtime.
The bot maintains an internal view of prices, holdings, and outstanding
orders to ensure desired trading state is continuously enforced.

https://tylerebowers.github.io/Schwabdev/

"""

import os
import decimal
import time     # stdlib: sleep, time.time()
import threading
import json
import signal

from datetime import (
    datetime,
    timedelta,
    timezone,
    date,
    time as dt_time
    )
from dotenv import load_dotenv
from pathlib import Path
from rich.console import Console
from zoneinfo import ZoneInfo

import schwabdev

from schwab_trader.config.bot.bot3_config import TradingConfig, SymbolConfig
from schwab_trader.orders.equity import (
    sell_limit_sell_stoplimit_oco_dict,
    sell_trailing_sell_limit_oco_dict,
)
from schwab_trader.utils.db import (
    init_db,
    log_transaction,
    get_last_buy_price,
    get_last_sell_price,
    get_high_price,
    save_state,
)

load_dotenv()
console = Console()
# Set the global context strategy to strictly round down
decimal.getcontext().rounding = decimal.ROUND_DOWN

class TradingBot:
    """
    Automated trading engine for Schwab brokerage accounts.
    The bot continuously monitors market prices and account activity,
    synchronizes holdings with the brokerage account, evaluates trading
    opportunities based on configuration, and manages orders throughout
    their lifecycle.
    """
    ET = ZoneInfo("America/New_York")  # class-level constant
    
    def __init__(self, cfg: TradingConfig, mode: str = "cli", config_path=None):
        """
        Initialize the trading bot.
        """
        init_db()
        self.client = schwabdev.Client(
            os.getenv("APP_KEY"), os.getenv("APP_SECRET"), os.getenv("CALLBACK_URL")
        )
        self.config_path = config_path
        self.mode = mode
        self.streamer = None
        self.risk_config = cfg.risk
        self.symbols_config: dict[str, SymbolConfig] = cfg.symbols
        self.day_prices: dict[str, dict[str, float]] = {sym: {p: None for p in ['market', 'low', 'high', 'close', 'hwm']} for sym in self.symbols}
        # for market, day low, day high, previous close and high water mark prices.
        self.holdings = {} # Only positions that are also in symbols_config
        self.all_holdings = {} # Every long position in the Schwab account
        self.pending_buy_orders = set()
        self.auto_buy_allowed = {sym: True for sym in self.symbols}
        self.lock = threading.RLock()
        self.running = True
        # Allow config reload via SIGHUP (used by systemd reload)
        signal.signal(signal.SIGHUP, self._on_sighup)
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        # Anti-duplicate protection
        self.last_order_placement = {}
        # Caches
        self._open_orders_cache = None
        self._open_orders_cache_time = 0
        self.open_orders_cache_ttl = 45

        self.daily_start_equity = self.get_account_snapshot()["equity"]
        self.today = date.today()

        # Shutdown config
        self.trading_enabled = False   # flipped by monitor based on clock
        
        console.print("[bold green]TradingBot initialized[/bold green]")

    @property
    def symbols(self):
        """Return the list of configured trading symbols."""
        return list(self.symbols_config.keys())

    def _get_account_hash(self):
        """Retrieve the Schwab account hash used by API requests."""
        accounts = self.client.linked_accounts().json()
        return accounts[0]["hashValue"]

    def get_account_snapshot(self):
        """Retrieve a snapshot of the current account balances."""
        try:
            acc = self.client.account_details(self.account_hash).json()
            bal = acc.get("securitiesAccount", {}).get("currentBalances", {})
            return {
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
        except Exception as e:
            console.print(f"[red]Snapshot error: {e}[/red]")
            return {
                "equity": 0.0,
                "cashBalance": 0.0,
                "buyingPower": 0.0,
                "dayTradingBP": 0.0,
                "nonMarginableBP": 0.0,
            }

    def _on_sighup(self, signum, frame):
        """Handle SIGHUP → hot-reload config without stopping the bot."""
        console.print("[bold cyan]SIGHUP received → reloading config...[/bold cyan]")
        try:
            self.reload_config()
            console.print("[bold green]Config reload complete[/bold green]")
        except Exception as e:
            console.print(f"[red]Config reload via SIGHUP failed: {e}[/red]")

    def update_holdings_from_api(self):
        """Synchronize portfolio holdings from the Schwab account."""
        try:
            pos = self.client.account_details(
                self.account_hash, fields="positions"
            ).json()
            positions = pos.get("securitiesAccount", {}).get("positions", [])
            new_holdings = {}
            new_all = {}
            for p in positions:
                sym = p["instrument"]["symbol"]
                long_qty = float(p.get("longQuantity", 0))
                day_pct = float(p.get("currentDayProfitLossPercentage", 0))
                if long_qty > 0:
                    avg = float(p.get("averagePrice") or 0)
                    mv = float(p.get("marketValue") or 0)
                    price = mv / long_qty if long_qty > 0 else 0
                    entry = {
                        "shares": long_qty,
                        "buy_price": avg,
                        "current_price": price,
                        "day_pct": day_pct,
                    }
                    new_all[sym] = entry
                    if sym in self.symbols_config:
                        new_holdings[sym] = entry

            with self.lock:
                self.holdings = new_holdings
                self.all_holdings = new_all
                for sym in self.symbols:
                    if sym not in new_holdings:
                        self.auto_buy_allowed[sym] = True
            # Seed/refresh in-momory HWM after holdings change
            self._sync_high_prices()

        except Exception as e:
            console.print(f"[red]Holdings update failed: {e}[/red]")

    def get_open_orders(self):
        """Return all currently working orders (with caching)."""
        now = time.time()
        if (
            self._open_orders_cache
            and now - self._open_orders_cache_time < self.open_orders_cache_ttl
        ):
            return self._open_orders_cache

        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(days=7)
        for attempt in range(2):
            try:
                resp = self.client.account_orders(
                    self.account_hash,
                    fromEnteredTime=from_time,
                    toEnteredTime=to_time,
                    status="WORKING",
                )
                orders = resp.json() or []
                flat = []
                for root in orders:
                    flat.extend(self._flatten_order(root))
                self._open_orders_cache = flat
                self._open_orders_cache_time = now
                return flat
            except Exception as e:
                console.print(f"[red]Open orders error: {e}[/red]")
                return self._open_orders_cache or []

    def _flatten_order(self, order):
        results = []
        if "orderLegCollection" in order:
            leg = order["orderLegCollection"][0]
            price = (
                order.get("price")
                or order.get("stopPrice")
                or order.get("stopLimitPrice")
                or order.get("limitPrice")
                or order.get("stopPriceOffset")
            )
            results.append(
                {
                    "orderId": order.get("orderId"),
                    "symbol": leg["instrument"]["symbol"],
                    "instruction": leg["instruction"],
                    "quantity": leg.get("quantity"),
                    "price": price,
                    "orderStrategyType": order.get("orderStrategyType"),
                    "type": order.get("orderType", ""),
                    "duration": order.get("duration", ""),
                }
            )
        for child in order.get("childOrderStrategies", []):
            results.extend(self._flatten_order(child))
        return results

    def has_open_order_for_symbol(self, symbol: str, instruction=None) -> bool:
            for o in self.get_open_orders():
                if o["symbol"] == symbol and (
                    not instruction or o["instruction"] == instruction
                ):
                    return True
            return False

    def can_place_order(self, symbol: str) -> bool:
        """Anti-duplicate protection."""
        now = time.time()
        last = self.last_order_placement.get(symbol, 0)
        if now - last < 25:
            return False
        self.last_order_placement[symbol] = now
        return True

    def cancel_all_orders_for_symbol(self, symbol: str):
        """Cancel every working order for a symbol."""
        try:
            orders = self.get_open_orders()
            for o in orders:
                if o.get("symbol") == symbol:
                    order_id = o.get("orderId")
                    if order_id:
                        try:
                            self.client.cancel_order(self.account_hash, order_id)
                            console.print(
                                f"[yellow]Cancelled order {order_id} for {symbol}[/yellow]"
                            )
                        except Exception as e:
                            console.print(
                                f"[red]Failed to cancel order {order_id}: {e}[/red]"
                            )
            self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]Error cancelling orders for {symbol}: {e}[/red]")

    # ====================== ORDER PLACEMENT ======================
    def place_limit_buy(self, symbol: str, limit_price: str, qty: int) -> bool:
        """Submit a market buy order."""
        if not self.risk_checks_pass(symbol) or not self.can_place_order(symbol):
            return False
        _cfg = self.symbols_config[symbol]
        order = {
            "orderType": "LIMIT",
            "session": _cfg.session,
            "duration": _cfg.duration,
            "price": str(self._conditional_truncate(limit_price)),
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": qty,
                    "instrument": {"symbol": symbol, "assetType": "EQUITY"},
                }
            ],
        }
        try:
            response = self.client.place_order(self.account_hash, order)
            location = response.headers.get("Location")
            order_id = location.split("/")[-1] if location else None
            if response.status_code == 201 and order_id is not None:
                console.print(f"[green]✓ BUY submitted for {symbol} x {qty}[/green]")
                self.invalidate_open_orders_cache()
                return True
        except Exception as e:
            console.print(f"[red]Buy failed: {e}[/red]")
            return False

    def _get_reference_price(self, symbol: str, holding: dict, sym_cfg) -> tuple[float, str]:
        """
        Return (reference_price, source_label).
        Preference order:
        1. In-memory high-water mark
        2. Persisted high-water mark (DB)
        3. Schwab average cost
        4. Config buy_target_price
        """
        # 1. Fast in-memory path
        hwm = self.day_prices.get(symbol).get("hwm")
        if hwm is not None and hwm > 0:
            return hwm, "HWM (memory)"

        # 2. DB fallback (and re-seed memory)
        hwm = get_high_price(symbol)
        if hwm is not None and hwm > 0:
            with self.lock:
                self.day_prices[symbol]["hwm"] = hwm
            return hwm, "HWM (DB)"

        # 3. Average cost from Schwab
        avg = float(holding.get("buy_price") or 0)
        if avg > 0:
            return avg, "avg cost"

        # 4. Config fallback
        return sym_cfg.buy_target_price, "buy_target"


    def submit_sell_bracket_oco(self, symbol: str):
        """
        Exit strategy:
        - If price >= limit_sell_price * 1.01 → immediate market sell
        - If price >= trail_activation_price → Trailing Stop + Limit OCO
        - Otherwise → Classic protective Stop + Limit OCO
            (stop is calculated from high-water mark when available)
        """
        if not self.can_place_order(symbol) or symbol not in self.holdings:
            return

        holding = self.holdings[symbol]
        _cfg = self.symbols_config[symbol]
        qty = int(holding["shares"])
        price = self.day_prices.get(symbol, {}).get("market") or holding.get("buy_price", 0)

        if price <= 0:
            console.print(f"[yellow]No valid price for {symbol}, skipping OCO[/yellow]")
            return

        # ------------------------------------------------------------------
        # Scenario 1 – Already past hard take-profit → market sell
        # ------------------------------------------------------------------
        if price >= _cfg.limit_sell_price * 1.01:
            self.place_limit_sell(symbol, _cfg.limit_sell_price)
            return

        # ------------------------------------------------------------------
        # Scenario 2 – Above trail activation → Trailing + Limit OCO
        # ------------------------------------------------------------------
        if price >= _cfg.trail_activation_price:
            oco = sell_trailing_sell_limit_oco_dict(
                symbol=symbol,
                quantity=qty,
                sell_limit_price=str(_cfg.limit_sell_price),
                
                stop_price_offset=_cfg.trail_offset_pct,
                session=_cfg.session,
                duration=_cfg.duration,
            )
            try:
                response = self.client.place_order(self.account_hash, oco)
                location = response.headers.get("Location")
                order_id = location.split("/")[-1] if location else None
                if response.status_code == 201 and order_id is not None:
                    console.print(
                        f"[green]✓ Trailing+Limit OCO placed for {symbol} "
                        f"(Trail {_cfg.trail_offset_pct}% | Limit ${_cfg.limit_sell_price})[/green]"
                    )
                    self.invalidate_open_orders_cache()
            except Exception as e:
                console.print(f"[red]Trailing OCO failed for {symbol}: {e}[/red]")
            return

        # ------------------------------------------------------------------
        # Scenario 3 – Protective classic OCO (uses high-water mark). OCO: 1. Sell limit order on limit_cell_price to ensure the profit 2. Sell stop limit order to avoid catastrophic loss during a fast crash.
        # ------------------------------------------------------------------
        reference_price, ref_source = self._get_reference_price(symbol, holding, _cfg)

        if _cfg.stop_loss_dollar and _cfg.stop_loss_dollar > 0:
            stop_price = round(reference_price - _cfg.stop_loss_dollar, 2)
            stop_source = f"${_cfg.stop_loss_dollar} below {ref_source}"
        else:
            stop_price = round(reference_price * (1 - _cfg.stop_loss_pct / 100), 2)
            stop_source = f"{_cfg.stop_loss_pct}% below {ref_source}"

        # Safety: stop must stay below current price
        if stop_price >= price:
            stop_price = round(price * 0.99, 2)

        oco = sell_limit_sell_stoplimit_oco_dict(
            symbol=symbol,
            quantity=qty,
            sell_limit_price=str(_cfg.limit_sell_price),
            sell_stop_price=str(stop_price),
            sell_stoplimit_price=str(round(stop_price * 0.99, 2)),
            session_sell_limit=_cfg.session,
            session_sell_stoplimit=_cfg.session,
            duration=_cfg.stop_loss_order_duration,
        )
        try:
            response = self.client.place_order(self.account_hash, oco)
            location = response.headers.get("Location")
            order_id = location.split("/")[-1] if location else None
            if response.status_code == 201 and order_id is not None:
                console.print(
                    f"[green]✓ Classic OCO placed for {symbol} "
                    f"(Stop ${stop_price:.2f} [{stop_source}] | Limit ${_cfg.limit_sell_price})[/green]"
                )
                self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]OCO failed for {symbol}: {e}[/red]")

    def place_limit_sell(self, symbol: str, limit_price):
        """Immediately liquidate position."""
        if not self.can_place_order(symbol) or symbol not in self.holdings:
            return
        holding = self.holdings[symbol]
        _cfg = self.symbols_config[symbol]
        order = {
            "orderType": "LIMIT",
            "session": _cfg.session,
            "duration": _cfg.duration,
            "price": str(self._conditional_truncate(limit_price)),
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": int(holding["shares"]),
                    "instrument": {"symbol": symbol, "assetType": "EQUITY"},
                }
            ],
        }
        try:
            response = self.client.place_order(self.account_hash, order)
            location = response.headers.get("Location")
            order_id = location.split("/")[-1] if location else None
            if response.status_code == 201 and order_id is not None:
                console.print(
                    f"[bold green]Immediate SELL executed for {symbol}[/bold green]"
                )
                self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]Immediate sell failed: {e}[/red]")

    def invalidate_open_orders_cache(self):
        self._open_orders_cache = None
        self._open_orders_cache_time = 0

    # ====================== CORE LOGIC ======================
    def ensure_orders(self, symbol: str):
        """Ensure correct order state for a symbol (with HWM-based stop ratcheting)."""
        if not getattr(self, "trading_enabled", False):
            return

        _cfg = self.symbols_config.get(symbol)
        if not _cfg:
            return

        price = self.day_prices.get(symbol, {}).get("market")
        if not price:
            return

        has_position = (
            symbol in self.holdings and self.holdings[symbol].get("shares", 0) > 0
        )

        has_sell = self.has_open_order_for_symbol(symbol, "SELL")
        has_buy = self.has_open_order_for_symbol(symbol, "BUY")

        # ------------------------------------------------------------------
        # No position → look for buy opportunity
        # ------------------------------------------------------------------
        if not has_position and not has_buy:
            last_sell = get_last_sell_price(symbol)
            trigger = price <= _cfg.buy_target_price or (
                last_sell and price <= last_sell * (1 - _cfg.buy_drop_pct / 100)
            )
            if trigger and self.risk_checks_pass(symbol):
                console.print(f"[yellow]Ensuring BUY order for {symbol}[/yellow]")
                price = round(price, 2) if price > 1 else round(price, 4)
                self.place_limit_buy(symbol, price, _cfg.fixed_shares)

        # ------------------------------------------------------------------
        # Have position but no sell order → place protective / trailing OCO
        # ------------------------------------------------------------------
        elif has_position and not has_sell:
            console.print(f"[yellow]Ensuring SELL bracket for {symbol}[/yellow]")
            self.submit_sell_bracket_oco(symbol)

        # ------------------------------------------------------------------
        # Have position + sell order already working
        # ------------------------------------------------------------------
        elif has_position and has_sell:
            # 1. Upgrade to trailing once price reaches activation
            if price >= _cfg.trail_activation_price:
                orders = self.get_open_orders()
                has_trailing = any(
                    o["symbol"] == symbol and o.get("type") == "TRAILING_STOP"
                    for o in orders
                )
                if not has_trailing:
                    console.print(f"[cyan]Upgrading {symbol} to Trailing+Limit OCO[/cyan]")
                    self.cancel_all_orders_for_symbol(symbol)
                    time.sleep(0.8)
                    self.submit_sell_bracket_oco(symbol)
                return  # already handled

            # 2. Still in protective phase → ratchet stop higher if HWM moved
            ideal_stop = self._compute_ideal_stop(symbol)
            if ideal_stop is None:
                return

            current_stop = self._get_current_stop_price(symbol)
            if current_stop is None:
                # Safety: place a stop if somehow missing
                self.cancel_all_orders_for_symbol(symbol)
                time.sleep(0.8)
                self.submit_sell_bracket_oco(symbol)
                return

            # Minimum move required before ratcheting (0.10% of current price)
            min_move = price * 0.0010

            if ideal_stop > current_stop + min_move:
                console.print(
                    f"[cyan]Ratcheting protective stop for {symbol} "
                    f"from ${current_stop:.2f} → ${ideal_stop:.2f}[/cyan]"
                )
                self.cancel_all_orders_for_symbol(symbol)
                time.sleep(0.8)
                self.submit_sell_bracket_oco(symbol)

    # Small helper methods
    def _conditional_truncate(self, x: float) -> float:
        """Achwab API: Orders above $1 can be endtered in no more than two decimals; orders below $1, no more than four decimals"""
        import math
        decimals = 2 if x > 1 else 4
        factor = 10 ** decimals
        return math.trunc(x * factor) / factor


    def _compute_ideal_stop(self, symbol: str) -> float | None:
        """
        Compute the stop price that *should* be active right now
        based on the current high-water mark (or fallbacks).
        Returns None if we cannot compute a sensible stop.
        """
        if symbol not in self.holdings:
            return None

        _cfg = self.symbols_config.get(symbol)
        if not _cfg:
            return None

        holding = self.holdings[symbol]
        price = self.day_prices.get(symbol, {}).get("market") or holding.get("buy_price") or 0
        if price <= 0:
            return None

        reference_price, _ = self._get_reference_price(symbol, holding, _cfg)

        # Prefer fixed $ stop when configured; otherwise use %
        if _cfg.stop_loss_dollar and _cfg.stop_loss_dollar > 0:
            stop_price = round(reference_price - _cfg.stop_loss_dollar, 2)
        else:
            stop_price = round(reference_price * (1 - _cfg.stop_loss_pct / 100), 2)

        # Safety: stop must stay below current market price
        if stop_price >= price:
            stop_price = round(price * 0.99, 2)

        return stop_price

    
    def _get_current_stop_price(self, symbol: str) -> float | None:
        """
        Best-effort extraction of the working stop price for a symbol.
        Looks at open orders and returns the first usable stop/limit price.
        """
        for o in self.get_open_orders():
            if o.get("symbol") != symbol:
                continue
            if o.get("instruction") not in ("SELL", "SELL_SHORT"):
                continue

            # Prefer explicit stop fields, then generic price
            for key in ("stopPrice", "stopLimitPrice", "stopPriceOffset", "price"):
                val = o.get(key)
                if val not in (None, "", 0):
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        continue
        return None
    

    def _sync_high_prices(self):
        """
        Populate / refresh self.day_prices from DB (persisted HWM)
        and current holdings. Call after holdings update, config reload,
        or on startup.
        """
        with self.lock:
            for sym in list(self.symbols):
                # Prefer DB value (survives restarts)
                hwm = get_high_price(sym)
                if hwm is not None and hwm > 0:
                    self.day_prices[sym]["hwm"] = hwm
                # Fallback: use current average cost if we hold the position
                elif sym in self.holdings and self.holdings[sym].get("buy_price"):
                    bp = float(self.holdings[sym]["buy_price"])
                    if bp > 0:
                        self.day_prices[sym]["hwm"] = bp
                        # Persist the seed so next restart is correct
                        save_state(symbol=sym, high_price=bp)
                # Clean up symbols we no longer care about
                if sym not in self.symbols_config and sym in self.day_prices:
                    self.day_prices.pop(sym, None)

    def reload_config(self):
        """Hot-reload configuration."""
        try:
            new_cfg = TradingConfig.load_from_file(self.config_path)
            with self.lock:
                self.risk_config = new_cfg.risk
                self.symbols_config = new_cfg.symbols
                for sym in self.symbols:
                    if sym not in self.day_prices:
                        self.day_prices[sym] == {p: None for p in ['market', 'low', 'high', 'close', 'hwm']}
                        self.auto_buy_allowed[sym] = True
                for sym in list(self.day_prices.keys()):
                    if sym not in self.symbols_config:
                        self.day_prices.pop(sym, None)
                        self.auto_buy_allowed.pop(sym, None)
            # Refresh HWM cache for (possibly) new symbol set
            self._sync_high_prices()

            console.print("[bold cyan]Config reloaded successfully[/bold cyan]")

            if self.streamer:
                self.start_stream()

            for sym in self.symbols:
                self.cancel_all_orders_for_symbol(sym)
                time.sleep(0.5)
                self.ensure_orders(sym)

        except Exception as e:
            console.print(f"[red]Config reload failed: {e}[/red]")


    # ====================== STREAM HANDLING ======================
    # ---------- Schwab decimal decoder ----------
    def _decode_schwab_decimal(self, obj) -> float:
        """Decode Schwab's {lo, signScale} decimal format. e.g. {"lo":"213500000","signScale":12} lower 64 bits of the decimal's integer/mantissa"""
        if obj is None:
            return 0.0
        if isinstance(obj, (int, float)):
            return float(obj)
        if isinstance(obj, dict) and "lo" in obj:
            from decimal import Decimal
            try:
                lo = Decimal(str(obj.get("lo"))) if obj.get("lo") is not None else Decimal("0.00")
                sign_scale = int(obj.get("signScale", 0))
                # 'lo' may not exist, but 'signScale' always in the streamed data
                value = lo / (Decimal(10) ** (sign_scale // 2))
                if sign_scale % 2:
                    value = -value
                return float(value)
            except Exception:
                return 0.0
        return 0.0

        
    def unified_receiver(self, message):
        """Dispatch streaming messages."""
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                return
        if not isinstance(message, dict):
            return
        # Three messages that Schwab's streaming server sends to your receiver: 'response', 'data' and 'notify'. They are all organized as (nested) lists of dictionaries. We only focus on 'data'.
        for item in message.get("data", []):
            service = item.get("service")
            if service == "LEVELONE_EQUITIES":
                self._handle_price(item)
            elif service == "ACCT_ACTIVITY":
                self._handle_fill(item)


    def _handle_price(self, item):
        """Process price updates and maintain high-water mark."""
        for content in item.get("content", []):
            sym = content.get("key")
            if sym not in self.day_prices:
                continue
            try:
                price = content.get("3") # Last price
                day_low = content.get("11")
                day_high = content.get("10")
                previous_close = content.get("12")
                # Not all fields will be returned by evey stream pulse. 

                if price is None:
                    continue

                with self.lock:
                    if price is not None:
                        self.day_prices[sym]["market"] = float(price)
                    if day_low is not None:
                        self.day_prices[sym]["low"] = float(day_low)
                    if day_high is not None:
                        self.day_prices[sym]["high"] = float(day_high)
                    if previous_close is not None:
                        self.day_prices[sym]["close"] = float(previous_close)

                    # Only track HWM while we actually hold the position
                    if sym in self.holdings and self.holdings[sym].get("shares", 0) > 0:
                        current_hwm = self.day_prices.get(sym).get("hwm")
                        if current_hwm is None or current_hwm < price:
                            self.day_prices[sym]["hwm"] = price
                            # Persist only when it actually moves (avoids DB spam)
                            save_state(symbol=sym, high_price=price)

            except (TypeError, ValueError):
                pass


            # console.print("self_price", self.day_prices)
            # console.print(price, previous_close, day_low, day_high)
            # console.print("content", content)
            

    def _handle_fill(self, item):
        """
        Process order execution events.
        Updates holdings, transaction history, and order state after buy or
        sell executions before re-evaluating the trading strategy.
        """
        for content in item.get("content", []):
            # Schwabdev account activity fields (common mapping):
            # "0" = SubscriptionKey / Symbol-ish
            # "1" = Account
            # "2" = MessageType (string)
            # "3" = MessageData (JSON string)
            msg_type = content.get('2', '')
            msg_data = content.get('3', '')

            ###################################################
            from pathlib import Path

            # Near the top of your file
            PROJECT_ROOT = Path(__file__).resolve().parents[3]
            STATE_DIR = PROJECT_ROOT / "logs"
            STATE_DIR.mkdir(parents=True, exist_ok=True)

            # /schwab-trader/logs/updates.log

            # Then use it like this:
            LOG_FILE = STATE_DIR / "fill_updates.log"
                    
            entry = {
                "timestamp": datetime.now().isoformat(),
                "streamed_content": content
                }
                    
            with open(LOG_FILE, "a") as f:          # "a" = append mode
                f.write(json.dumps(entry) + "\n\n")   # one JSON object per line
            ###################################################

            if not msg_data or msg_type not in (
                            #'OrderAccepted',
                            'OrderFillCompleted',
                        ): 
                            # Schwab does not have clear documentation, only based on https://tylerebowers.github.io/Schwabdev/?source=pages%2Fstream.html
                            continue

            try:
                msg_data_parsed = json.loads(msg_data) if isinstance(msg_data, str) else msg_data
            except (json.JSONDecodeError, TypeError):
                continue
            # Note: json.load() doesn't necessarily give you a dictionary. 
            # 1. json.loads('{"a": 1}')             # → dict 
            # 2. json.loads('[{"a": 1},{"a": 2}]')  # → list 
            # 3. json.loads('"hello"')              # → str
            # In the example from the above reference, it's a dict

            order_id = msg_data_parsed.get("SchwabOrderID", '')
            base_event = msg_data_parsed.get("BaseEvent", {})

            if base_event.get("EventType") != "OrderFillCompleted":
                continue

            fill_info = base_event.get(
                "OrderFillCompletedEventOrderLegQuantityInfo",
                {}
            )

            # Partial fill or complete fill
            leg_status = fill_info.get("LegSubStatus", "")
            if leg_status == "LegSubStatusFilled":
                action_status = "Filled"
            elif leg_status == "LegSubStatusPartiallyFilled":
                action_status = "PartiallyFilled"
            else:
                action_status = None

            # streamer.account_activity("Account Activity", "0,1,2,3")
            # In the message data (a list[dict-like]) returned, "data": [...]> when "service": "ACCT_ACTIVITY" and "content":{..., "2": "OrderFillCompleted", ...}, "content":{..., "3":{...,"BaseEvent": <there are three sections including "QuantityInfo", "ExecutionInfo", and "OrderInfoForTransactionPosting". All may contain quantity, price infomation.>, ...} 
            execution_info = fill_info.get("ExecutionInfo", {})
            order_info = fill_info.get("OrderInfoForTransactionPosting", {})

            try:
                symbol = order_info.get("Symbol", '').upper()
                side = order_info.get("BuySellCode", '').upper()

                qty = self._decode_schwab_decimal(execution_info.get("ExecutionQuantity", {}))
                price = self._decode_schwab_decimal(execution_info.get("ExecutionPrice", {}))
                timestamp = execution_info.get("ExecutionTimeStamp", {}).get("DateTimeString")
                # All the above three are {}s
            except Exception:
                continue


            console.print(f"[bold]{side} FILL: {symbol} @ ${price:.2f} x {qty}[/bold] (orde_id:{order_id})")

            with self.lock:
                if side in ("SELL", "SELL_SHORT"):
                    self.holdings.pop(symbol, None)
                    self.auto_buy_allowed[symbol] = True
                    self.day_prices.pop(symbol, None)

                    # Log the transaction and update the state
                    log_transaction(
                        action=action_status,
                        symbol=symbol,
                        qty=qty,
                        price=price,
                        order_id=str(order_id) if order_id else None,
                        note="OCO or manual sell",
                        ts=timestamp,
                    )

                    save_state(
                        symbol=symbol,
                        last_sell_price=price,
                        last_sell_qty=qty,
                        last_buy_price=None,  # Position closed
                        last_buy_qty=None,
                        high_price=None,
                        ts=timestamp,
                    )

                elif side in ("BUY", "BUY_TO_COVER"):
                    self.holdings[symbol] = {"shares": qty, "buy_price": price}
                    self.day_prices[symbol]["hwm"] = price

                    # Log the transaction and update the state
                    log_transaction(
                        action=action_status,
                        symbol=symbol,
                        qty=qty,
                        price=price,
                        order_id=str(order_id) if order_id else None,
                        note="Auto buy",
                        ts=timestamp,
                    )

                    save_state(
                        symbol=symbol,
                        last_buy_price=price,
                        last_buy_qty=qty,
                        high_price=price,
                        ts=timestamp,
                    )

            # Refresh data after any fill
            time.sleep(1.5)
            self.ensure_orders(symbol)
            self.update_holdings_from_api()
            self.invalidate_open_orders_cache()

    def start_stream(self):
        """Start market and account streaming."""
        if self.streamer:
            try:
                self.streamer.stop()
            except:
                pass

        self.streamer = schwabdev.Stream(self.client)
        self.streamer.start(receiver=self.unified_receiver)
        # Use start_auto instead of start
        # self.streamer.start_auto(
        #     receiver=self.unified_receiver,
        #     start_time=dt_time(9, 29, 0),      # slightly before open
        #     stop_time=dt_time(16, 0, 0),
        #     on_days=(0, 1, 2, 3, 4),           # Mon–Fri
        #     now_timezone=self.ET,
        #     daemon=True,
        # )
        # # It keep print "No subscriptions, starting stream anyways." in the terminal.

        # Subscriptions are remembered by start_auto and re-sent every day
        symbols_str = ",".join(self.symbols)
        if symbols_str:
            self.streamer.send(self.streamer.level_one_equities(symbols_str, "0,3,8,10,11,12,19,20,21")) # 0: Symbol, 1: BidPrice, 2: AskPrice, 3: Last tradePrice, 8:TotalVolumeTradedToday, 10: Today'sHighPrice, 11: Today'sLowPrice, 12: PreviousClosePrice,18: NetChange, 19: 52-week-high, 20: 52-week-low, 21: P/E 

            self.streamer.send(
                self.streamer.account_activity("Account Activity", "0,1,2,3")
            ) # 0: SubscriptionKey,Symbol, 1: Account, 2: MessageType, 3: MessageData.
            # MessageType ['SUBSCRIBED','ORDER_ENTRY','ORDER_CANCEL','ORDER_FILL','ORDER_PARTIAL_FILL']

        self.update_holdings_from_api()
        time.sleep(2)
        self._sync_high_prices()
        for sym in self.symbols:
            self.ensure_orders(sym)

    def monitor_logic(self):
        """Background monitoring thread."""
        while self.running:
            try:
                self.refresh_trading_window()

                today_et = self.now_et().date()
                if today_et != self.today:
                    self.today = today_et
                    self.daily_start_equity = self.get_account_snapshot()["equity"]
                    self.trading_paused = False

                if self.trading_enabled:
                    self.update_holdings_from_api()
                    for sym in self.symbols:
                        self.ensure_orders(sym)
                    time.sleep(15)
                else:
                    time.sleep(60)  # idle overnight / weekend
            except Exception as e:
                console.print(f"[red]monitor_logic error: {e}[/red]")
                time.sleep(15)

    # ====================== Market hours ======================
    # schwabdev has start_auto() alternative
    # https://tylerebowers.github.io/Schwabdev/?source=pages%2Fstream.html
    # streamer.start_auto() only manages WebSocket connection (connect at open, disconnect at close). You still need the Market hours section if you want the bot to: 1. Avoid placing new orders outside the 9:30-16:00 ET. 2. Pause the monitor_logic loop overnight / on weekends. 3. Rest daily equity / risk counteres. 4. Keep trading_enabled = False when the market is close.
    def now_et(self) -> datetime:
        return datetime.now(self.ET)

    def is_weekday(self, dt: datetime | None = None) -> bool:
        dt = dt or self.now_et()
        return dt.weekday() < 5  # Mon–Fri

    def is_regular_session(self, dt: datetime | None = None) -> bool:
        """True only 09:30 - 16:00 America/New_York on trading weekdays."""
        dt = dt or self.now_et()
        if not self.is_weekday(dt):
            return False
        t = dt.time()
        return dt_time(9, 30) <= t <= dt_time(16, 0)

    def refresh_trading_window(self) -> None:
        """
        Flip trading_enabled from the clock.
        Does NOT stop the process (avoids systemd restart storms).
        """
        was = getattr(self, "trading_enabled", False)
        self.trading_enabled = self.is_regular_session()

        if self.trading_enabled and not was:
            console.print("[bold green]Market open → TRADING mode[/bold green]")
            try:
                self.update_holdings_from_api()
                for sym in self.symbols:
                    self.ensure_orders(sym)
            except Exception as e:
                console.print(f"[red]Open transition error: {e}[/red]")

        elif not self.trading_enabled and was:
            console.print("[bold yellow]Market closed → IDLE mode[/bold yellow]")
            # Optional: cancel working DAY orders at close
            # for sym in list(self.symbols):
            #     self.cancel_all_orders_for_symbol(sym)

    def risk_checks_pass(self, symbol: str) -> bool:
        """
        Central risk gate. Returns True only if it is safe to place a new order.
        """
        # 1. Market must be open
        if not getattr(self, "trading_enabled", False):
            return False

        # 2. Manually or automatically paused
        if getattr(self, "trading_paused", False):
            return False

        # 3. Minimum account equity
        try:
            snap = self.get_account_snapshot()
            min_equity = getattr(self.risk_config, "min_account_equity", 5000.0)
            if snap["equity"] < min_equity:
                if not self.trading_paused:
                    console.print(
                        f"[bold red]Equity ${snap['equity']:.2f} below minimum "
                        f"${min_equity:.2f} → trading paused[/bold red]"
                    )
                self.trading_paused = True
                return False
        except Exception as e:
            console.print(f"[red]Risk check snapshot failed: {e}[/red]")
            return False

        # 4. Maximum number of positions
        max_pos = getattr(self.risk_config, "max_positions", 4)
        if len(self.holdings) >= max_pos:
            return False

        # 5. Optional: symbol already has a working order of the same side
        # (you can keep this in can_place_order or move it here)

        return True

    def start(self):
        """Start the trading bot."""
        self.start_stream()
        self.refresh_trading_window()  # set TRADING or IDLE immediately
        threading.Thread(
            target=self.monitor_logic, daemon=True, name="MonitorLogic"
        ).start()
        console.print("[bold green]✅ Bot started[/bold green]")

    def stop(self):
        """Stop the trading bot cleanly."""
        self.running = False
        if self.streamer:
            try:
                self.streamer.stop()
            except Exception:
                pass
        console.print("[bold yellow]Bot stopped[/bold yellow]")


"""
# https://tylerebowers.github.io/Schwabdev/?source=pages%2Fstream.html
# Schwabdev translation map for fields -level_one_equities.
# 0: "Symbol"
# 1: "Bid Price"
# 2: "Ask Price"
# 3: "Last Price"
# 4: "Bid Size"
# 5: "Ask Size"
# 6: "Ask ID"
# 7: "Bid ID"
# 8: "Total Volume"
# 9: "Last Size"
# 10: "High Price"
# 11: "Low Price"
# 12: "Close Price"
# 13: "Exchange ID"
# 14: "Marginable"
# 15: "Description"
# 16: "Last ID"
# 17: "Open Price"
# 18: "Net Change"
# 19: "52 Week High"
# 20: "52 Week Low"
# 21: "PE Ratio"
# 22: "Annual Dividend Amount"
# 23: "Dividend Yield"
# 24: "NAV"
# 25: "Exchange Name"
# 26: "Dividend Date"
# 27: "Regular Market Quote"
# 28: "Regular Market Trade"
# 29: "Regular Market Last Price"
# 30: "Regular Market Last Size"
# 31: "Regular Market Net Change"
# 32: "Security Status"
# 33: "Mark Price"
# 34: "Quote Time in Long"
# 35: "Trade Time in Long"
# 36: "Regular Market Trade Time in Long"
# 37: "Bid Time"
# 38: "Ask Time"
# 39: "Ask MIC ID"
# 40: "Bid MIC ID"
# 41: "Last MIC ID"
# 42: "Net Percent Change"
# 43: "Regular Market Percent Change"
# 44: "Mark Price Net Change"
# 45: "Mark Price Percent Change"
# 46: "Hard to Borrow Quantity"
# 47: "Hard To Borrow Rate"
# 48: "Hard to Borrow"
# 49: "shortable"
# 50: "Post-Market Net Change"
# 51: "Post-Market Percent Change"

WebSocket streaming
streamer = schwabdev.Stream(client) - create objects that know how to authenticate and establish the streaming connection.
streamer.start(receiver=print) - the streaming class manager.
Conceptually, schwabdev eventually does something equivalent to: websocket.connect("wss://....") where wss means WebSocket Secure. 

streamer.send(streamer.level_one_equities("AAPL", "0,1,2,3")) - subscription message

start_stream() only connects and subscribes. The useful work happens in the receiver callbacks, which update in-memory state that the rest of the pipeline reads.

start()
  └─ start_stream()
        ├─ create schwabdev.Stream(client)
        ├─ streamer.start(receiver=self.unified_receiver)   # callback
        ├─ subscribe LEVELONE_EQUITIES (prices)
        ├─ subscribe account_activity (fills / account events)
        ├─ update_holdings_from_api()
        └─ ensure_orders() for each symbol

_handle_price() maps the Symbol and Last Price or "3", using the following assignment, 
sym = content.get("key")
price = float(content.get("3") or 0)  # field 3 = Last Price

# Payload Example
streamer.send(streamer.level_one_equities("AMD,INTC", "0,1,2,3,4,5,6,7,8"))
{
  "data": [
    {
      "service": "LEVELONE_EQUITIES",
      "timestamp": 1765081984668,
      "command": "SUBS",
      "content": [
        {
          "1": 217.86,
          "2": 217.95,
          "3": 217.93,
          "4": 200,
          "5": 100,
          "6": "P",
          "7": "P",
          "8": 33292396,
          "key": "AMD",
          "delayed": false,
          "assetMainType": "EQUITY",
          "assetSubType": "COE",
          "cusip": "007903107"
        },
        {
          "1": 41.43,
          "2": 41.44,
          "3": 41.44,
          "4": 200,
          "5": 400,
          "6": "P",
          "7": "U",
          "8": 103042015,
          "key": "INTC",
          "delayed": false,
          "assetMainType": "EQUITY",
          "assetSubType": "COE",
          "cusip": "458140100"
        }
      ]
    }
  ]
}

streamer.send(streamer.account_activity("Account Activity", "0,1,2,3"))
{
    "response":[
        {
            "service":"ACCT_ACTIVITY",
            "command":"ADD",
            "requestid":"15","SchwabClientCorrelId":"98f4a74a-aead-f4aa-a6a6-f5adde0d1c8f",
            "timestamp":1786461735291,
            "content":{
                "code":0,
                "msg":"ADD command succeeded"
                }
        }
    ]
}

So "key" is Schwab's always-present symbol identifier on the message. Field "0" is the Symbol data field you can also subscribe to. They both mean the ticker, but they are not the same JSON slot.
"""

