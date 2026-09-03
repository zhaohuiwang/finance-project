"""
schwab-trader/src/schwab_trader/pipelines/bot4_pipeline.py

Schwab Trailing Momentum Trading Bot - Core Pipeline
====================================================
Automated trading engine focused on momentum-based trailing strategies.

Features:
1. Real-time price streaming for configured symbols
2. Detects upside momentum from previous close (x%)
3. Places trailing stop sell orders (a%)
4. After sell, monitors pullbacks and places trailing buy orders (b%)
5. Full daily cycle with risk management and state persistence


"""

import os
import decimal
import time
import threading
import json
import signal

from pathlib import Path
from datetime import datetime, timedelta, timezone, date, time as dt_time
from zoneinfo import ZoneInfo
from decimal import Decimal


import schwabdev
from dotenv import load_dotenv
from rich.console import Console

from schwab_trader.config.bot.bot4_config import TradingConfig, SymbolConfig
from schwab_trader.utils.db import (
    init_db,
    log_transaction,
    save_state,
    get_high_price,
    get_last_sell_price,
)

load_dotenv()
console = Console()
# Set the global context strategy to strictly round down
decimal.getcontext().rounding = decimal.ROUND_DOWN

class TradingBot:
    """
    Main trading bot class implementing trailing momentum strategy.
    Now uses Bot3-style price book + HWM and robust fill handling.
    """

    ET = ZoneInfo("America/New_York")

    def __init__(self, cfg: TradingConfig, mode: str = "cli", config_path=None):
        init_db()
        self.client = schwabdev.Client(
            os.getenv("APP_KEY"), os.getenv("APP_SECRET"), os.getenv("CALLBACK_URL")
        )
        self.config_path = config_path
        self.mode = mode
        self.streamer = None
        self.risk_config = cfg.risk
        self.symbols_config: dict[str, SymbolConfig] = cfg.symbols

        # ========== Bot3-style price tracking & state ==========
        self.day_prices: dict[str, dict[str, float | None]] = {
            sym: {p: None for p in ["market", "low", "high", "close", "hwm"]}
            for sym in self.symbols
        }
        self.holdings = {}
        self.last_sell_prices = {}          # still needed for Bot4 pullback logic
        self.auto_buy_allowed = {sym: True for sym in self.symbols}

        self.lock = threading.RLock()
        self.running = True
        # Allow config reload via SIGHUP (used by systemd reload)
        signal.signal(signal.SIGHUP, self._on_sighup)
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        self.last_order_placement = {}
        self._open_orders_cache = None
        self._open_orders_cache_time = 0
        self.open_orders_cache_ttl = 30

        self.daily_start_equity = self.get_account_snapshot()["equity"]
        self.today = date.today()

        self.trading_enabled = False
        self.trading_paused = False

        self.auto_shutdown_after_close = getattr(cfg, "auto_shutdown_after_close", True)
        self.shutdown_buffer_minutes = getattr(cfg, "shutdown_buffer_minutes", 2)

        console.print(
            "[bold green]TradingBot (Trailing Momentum Strategy) initialized "
            "(with Bot3 price tracking + fill handling)[/bold green]"
        )

    @property
    def symbols(self):
        return list(self.symbols_config.keys())

    def _get_account_hash(self):
        accounts = self.client.linked_accounts().json()
        return accounts[0]["hashValue"]

    def get_account_snapshot(self):
        try:
            acc = self.client.account_details(self.account_hash).json()
            bal = acc.get("securitiesAccount", {}).get("currentBalances", {})
            return {
                "equity": float(
                    bal.get("liquidationValue") or bal.get("equity") or 0.0
                ),
                "cashBalance": float(bal.get("cashBalance") or 0.0),
                "buyingPower": float(bal.get("buyingPower") or 0.0),
            }
        except Exception as e:
            console.print(f"[red]Snapshot error: {e}[/red]")
            return {"equity": 0.0, "cashBalance": 0.0, "buyingPower": 0.0}


    def _on_sighup(self, signum, frame):
        """Handle SIGHUP → hot-reload config without stopping the bot."""
        console.print("[bold cyan]SIGHUP received → reloading config...[/bold cyan]")
        try:
            self.reload_config()
            console.print("[bold green]Config reload complete[/bold green]")
        except Exception as e:
            console.print(f"[red]Config reload via SIGHUP failed: {e}[/red]")


    def update_holdings_from_api(self):
        try:
            pos = self.client.account_details(
                self.account_hash, fields="positions"
            ).json()
            positions = pos.get("securitiesAccount", {}).get("positions", [])
            new_holdings = {}
            for p in positions:
                sym = p["instrument"]["symbol"]
                long_qty = float(p.get("longQuantity", 0))
                day_pct = float(p.get("currentDayProfitLossPercentage", 0))
                if long_qty > 0 and sym in self.symbols_config:
                    avg = float(p.get("averagePrice") or 0)
                    new_holdings[sym] = {
                        "shares": long_qty,
                        "buy_price": avg,
                        "day_pct": day_pct,
                        }
            with self.lock:
                self.holdings = new_holdings
                for sym in self.symbols:
                    if sym not in new_holdings:
                        self.auto_buy_allowed[sym] = True
            self._sync_high_prices()
        except Exception as e:
            console.print(f"[red]Holdings update failed: {e}[/red]")


    def _load_last_sell_prices(self):
        """Restore last sell prices from DB so the dashboard and strategy work after restart."""
        try:
            for sym in self.symbols:
                last = get_last_sell_price(sym)
                if last is not None and last > 0:
                    self.last_sell_prices[sym] = float(last)
        except Exception as e:
            console.print(f"[yellow]Could not load last sell prices: {e}[/yellow]")

            
    def get_open_orders(self):
        now = time.time()
        if (
            self._open_orders_cache
            and now - self._open_orders_cache_time < self.open_orders_cache_ttl
        ):
            return self._open_orders_cache
        try:
            to_time = datetime.now(timezone.utc)
            from_time = to_time - timedelta(days=30)
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
            return []

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
    def place_trailing_stop_sell(self, symbol: str, qty: int, trail_pct: float):
        if not self.risk_checks_pass(symbol) or not self.can_place_order(symbol):
            return False

        if not self.can_place_order(symbol):
            return False
        symbol = symbol.upper()
        trail_pct = f"{trail_pct:.2f}"
        qty = int(qty)
        order = {
            "orderType": "TRAILING_STOP",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "stopPriceOffset": trail_pct,
            "stopPriceType": "PERCENT",
            "stopPriceBasis": "LAST",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": qty,
                    "instrument": {"symbol": symbol, "assetType": "EQUITY"},
                }
            ],
        }
        try:
            self.client.place_order(self.account_hash, order)
            console.print(
                f"[green]Trailing SELL placed for {symbol} ({trail_pct}% trail)[/green]"
            )
            self.invalidate_open_orders_cache()
            return True
        except Exception as e:
            console.print(f"[red]Trailing sell failed: {e}[/red]")
            return False

    def place_trailing_buy(self, symbol: str, qty: int, trail_pct: float):
        if not self.risk_checks_pass(symbol) or not self.can_place_order(symbol):
            return False
    
        if not self.can_place_order(symbol):
            return False
        symbol = symbol.upper()
        trail_pct = f"{trail_pct:.2f}"
        qty = int(qty)
        order = {
            "orderType": "TRAILING_STOP",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "stopPriceOffset": trail_pct,
            "stopPriceType": "PERCENT",
            "stopPriceBasis": "LAST",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": qty,
                    "instrument": {"symbol": symbol, "assetType": "EQUITY"},
                }
            ],
        }
        try:
            self.client.place_order(self.account_hash, order)
            console.print(
                f"[green]Trailing BUY placed for {symbol} ({trail_pct}% trail)[/green]"
            )
            self.invalidate_open_orders_cache()
            return True
        except Exception as e:
            console.print(f"[red]Trailing buy failed: {e}[/red]")
            return False

    # ====================== helpers ======================
    def _conditional_truncate(self, x: float) -> float:
        """Achwab API: Orders above $1 can be endtered in no more than two decimals; orders below $1, no more than four decimals"""
        import math
        decimals = 2 if x > 1 else 4
        factor = 10 ** decimals
        return math.trunc(x * factor) / factor
    
    def _sync_high_prices(self):
        """Same as Bot3 - seed / refresh HWM from DB or average cost."""
        with self.lock:
            for sym in list(self.symbols):
                hwm = get_high_price(sym)
                if hwm is not None and hwm > 0:
                    self.day_prices[sym]["hwm"] = hwm
                elif sym in self.holdings and self.holdings[sym].get("buy_price"):
                    bp = float(self.holdings[sym]["buy_price"])
                    if bp > 0:
                        self.day_prices[sym]["hwm"] = bp
                        save_state(symbol=sym, high_price=bp)

    def load_previous_closes(self):
        """Fallback loader - also writes into day_prices['close']."""
        try:
            for sym in self.symbols:
                quote = self.client.quote(sym).json()
                if sym in quote:
                    prev = quote[sym].get("closePrice") or quote[sym].get("lastPrice")
                    if prev:
                        with self.lock:
                            self.day_prices[sym]["close"] = float(prev)
        except Exception as e:
            console.print(f"[red]Failed to load previous closes: {e}[/red]")

    # ====================== CORE STRATEGY  ======================
    def ensure_trailing_strategy(self, symbol: str):
        cfg = self.symbols_config.get(symbol)
        if not cfg:
            return

        price = self.day_prices.get(symbol, {}).get("market")
        prev_close = self.day_prices.get(symbol, {}).get("close")
        day_low = self.day_prices.get(symbol, {}).get("low")
         
        # some of day_prices maybe None or 0.0, so this falsy check is valid, 
        # if price is None or prev_close is None or day_low is None: is not appropriate here
        if not price or not prev_close or not day_low:
            return

        base_low = min(prev_close, day_low)
        pct_up = ((price - base_low) / base_low) * 100
        has_position = symbol in self.holdings
        has_sell = self.has_open_order_for_symbol(symbol, "SELL")
        has_buy = self.has_open_order_for_symbol(symbol, "BUY")

        with self.lock:
            last_sell = self.last_sell_prices.get(symbol)

        # Momentum Sell
        if not has_position and not has_sell and pct_up >= cfg.momentum_up_pct:
            qty = cfg.fixed_shares
            self.place_trailing_stop_sell(symbol, qty, cfg.trailing_sell_pct)

        # Pullback Buy after sell
        elif last_sell and not has_position and not has_buy:
            pct_down = ((price - last_sell) / last_sell) * 100
            if pct_down <= -cfg.pullback_buy_pct:
                qty = cfg.fixed_shares
                self.place_trailing_buy(symbol, qty, cfg.trailing_buy_pct)

        # Maintain sell order on position
        elif has_position and not has_sell:
            qty = int(self.holdings[symbol]["shares"])
            self.place_trailing_stop_sell(symbol, qty, cfg.trailing_sell_pct)

    # ====================== STREAM HANDLING ======================
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
        """Exactly the same price + HWM logic as Bot3."""
        for content in item.get("content", []):
            sym = content.get("key")
            if sym not in self.day_prices:
                continue
            try:
                price = content.get("3")          # Last price
                day_low = content.get("11")
                day_high = content.get("10")
                previous_close = content.get("12")

                if price is None:
                    continue

                with self.lock:
                    self.day_prices[sym]["market"] = float(price)
                    if day_low is not None:
                        self.day_prices[sym]["low"] = float(day_low)
                    if day_high is not None:
                        self.day_prices[sym]["high"] = float(day_high)
                    if previous_close is not None:
                        self.day_prices[sym]["close"] = float(previous_close)

                    # Track HWM only while we hold the position
                    if sym in self.holdings and self.holdings[sym].get("shares", 0) > 0:
                        current_hwm = self.day_prices[sym].get("hwm")
                        if current_hwm is None or current_hwm < float(price):
                            self.day_prices[sym]["hwm"] = float(price)
                            save_state(symbol=sym, high_price=float(price))

                self.ensure_trailing_strategy(sym)

            except (TypeError, ValueError):
                pass


    def reload_config(self):
        """Hot-reload configuration from disk."""
        try:
            new_cfg = TradingConfig.load_from_file(self.config_path)

            with self.lock:
                self.risk_config = new_cfg.risk
                self.symbols_config = new_cfg.symbols

                # Keep day_prices & auto_buy_allowed in sync with new symbol list
                for sym in self.symbols:
                    if sym not in self.day_prices:
                        self.day_prices[sym] = {
                            p: None for p in ["market", "low", "high", "close", "hwm"]
                        }
                        self.auto_buy_allowed[sym] = True

                for sym in list(self.day_prices.keys()):
                    if sym not in self.symbols_config:
                        self.day_prices.pop(sym, None)
                        self.auto_buy_allowed.pop(sym, None)
                        self.last_sell_prices.pop(sym, None)

                # Update auto-shutdown settings if present
                self.auto_shutdown_after_close = getattr(new_cfg, "auto_shutdown_after_close", True)
                self.shutdown_buffer_minutes = getattr(new_cfg, "shutdown_buffer_minutes", 2)

            # Refresh derived state
            self._sync_high_prices()
            self._load_last_sell_prices()

            console.print("[bold cyan]Config reloaded successfully[/bold cyan]")

            # Cancel existing orders and re-evaluate strategy with new parameters
            for sym in list(self.symbols):
                self.cancel_all_orders_for_symbol(sym)
                time.sleep(0.4)

            # Optionally restart the stream if the symbol list changed significantly. (safe but not always necessary)
            self.start_stream()

        except Exception as e:
            console.print(f"[red]Config reload failed: {e}[/red]")
            raise   # re-raise so the SIGHUP handler can log it


    def _decode_schwab_decimal(self, obj) -> float:
        """Exactly the same decoder as Bot3."""
        if obj is None:
            return 0.0
        if isinstance(obj, (int, float)):
            return float(obj)
        if isinstance(obj, dict) and "lo" in obj:
            try:
                lo = Decimal(str(obj.get("lo"))) if obj.get("lo") is not None else Decimal("0.00")
                sign_scale = int(obj.get("signScale", 0))
                value = lo / (Decimal(10) ** (sign_scale // 2))
                if sign_scale % 2:
                    value = -value
                return float(value)
            except Exception:
                return 0.0
        return 0.0

    def _handle_fill(self, item):
        """
        Process order execution events.
        Updates holdings, transaction history, and order state after buy or
        sell executions before re-evaluating the trading strategy.
        """
        for content in item.get("content", []):
            msg_type = content.get("2", "")
            msg_data = content.get("3", "")

            # --- logging ---
            PROJECT_ROOT = Path(__file__).resolve().parents[3]
            STATE_DIR = PROJECT_ROOT / "logs"
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            LOG_FILE = STATE_DIR / "fill_updates.log"

            entry = {
                "timestamp": datetime.now().isoformat(),
                "streamed_content": content,
            }
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n\n")

            if not msg_data or msg_type not in ("OrderFillCompleted",):
                continue

            try:
                msg_data_parsed = (
                    json.loads(msg_data) if isinstance(msg_data, str) else msg_data
                )
            except (json.JSONDecodeError, TypeError):
                continue

            base_event = msg_data_parsed.get("BaseEvent", {})
            if base_event.get("EventType") != "OrderFillCompleted":
                continue

            fill_info = base_event.get(
                "OrderFillCompletedEventOrderLegQuantityInfo", {}
            )
            leg_status = fill_info.get("LegSubStatus", "")
            action_status = (
                "Filled"
                if leg_status == "LegSubStatusFilled"
                else "PartiallyFilled"
                if leg_status == "LegSubStatusPartiallyFilled"
                else None
            )

            execution_info = fill_info.get("ExecutionInfo", {})
            order_info = fill_info.get("OrderInfoForTransactionPosting", {})

            try:
                symbol = order_info.get("Symbol", "").upper()
                side = order_info.get("BuySellCode", "").upper()
                qty = self._decode_schwab_decimal(
                    execution_info.get("ExecutionQuantity", {})
                )
                price = self._decode_schwab_decimal(
                    execution_info.get("ExecutionPrice", {})
                )
                timestamp = execution_info.get("ExecutionTimeStamp", {}).get(
                    "DateTimeString"
                )
            except Exception:
                continue

            if not symbol or symbol not in self.symbols_config:
                continue

            console.print(
                f"[bold]{side} FILL: {symbol} @ ${price:.2f} x {qty}[/bold]"
            )

            with self.lock:
                if side in ("SELL", "SELL_SHORT"):
                    self.holdings.pop(symbol, None)
                    self.last_sell_prices[symbol] = price
                    self.auto_buy_allowed[symbol] = True
                    if symbol in self.day_prices:
                        self.day_prices[symbol]["hwm"] = None

                    log_transaction("SELL_FILLED", symbol, qty, price)
                    save_state(
                        symbol=symbol,
                        last_sell_price=price,
                        last_sell_qty=qty,
                        last_buy_price=None,
                        last_buy_qty=None,
                        high_price=None,
                        ts=timestamp,
                    )

                elif side in ("BUY", "BUY_TO_COVER"):
                    self.holdings[symbol] = {"shares": qty, "buy_price": price}
                    self.day_prices[symbol]["hwm"] = price

                    log_transaction("BUY_FILLED", symbol, qty, price)
                    save_state(
                        symbol=symbol,
                        last_buy_price=price,
                        last_buy_qty=qty,
                        high_price=price,
                        ts=timestamp,
                    )

            time.sleep(1.5)
            self.update_holdings_from_api()
            self.invalidate_open_orders_cache()
            self.ensure_trailing_strategy(symbol)

    def start_stream(self):
        if self.streamer:
            try:
                self.streamer.stop()
            except Exception:
                pass

        self.streamer = schwabdev.Stream(self.client)
        self.streamer.start(receiver=self.unified_receiver)

        symbols_str = ",".join(self.symbols)
        if symbols_str:
            # richer fields so we get high/low/close
            self.streamer.send(
                self.streamer.level_one_equities(
                    symbols_str, "0,1,2,3,8,10,11,12,19,20,21"
                )
            )
            self.streamer.send(
                self.streamer.account_activity("Account Activity", "0,1,2,3")
            )

        self.update_holdings_from_api()
        self.load_previous_closes()
        self._sync_high_prices()
        self._load_last_sell_prices()
        time.sleep(2)
        for sym in self.symbols:
            self.ensure_trailing_strategy(sym)

    def monitor_logic(self):
        """
        Background monitoring thread for Bot4.
        - Market hours gating
        - Strong day-change handling
        - Auto-shutdown after close
        - Efficient idle when market is closed
        """
        while self.running:
            try:
                # 1. Update session status
                self.refresh_trading_window()

                # 2. Handle new trading day (ET)
                today_et = self.now_et().date()
                if today_et != self.today:
                    self._handle_new_trading_day(today_et)

                # 3. Auto-shutdown check
                if self._should_auto_shutdown():
                    console.print(
                        "[bold yellow]Market closed + buffer reached → clean shutdown[/bold yellow]"
                    )
                    self.stop()
                    break

                # 4. Active trading vs idle
                if self.trading_enabled and not self.trading_paused:
                    self.update_holdings_from_api()
                    for sym in self.symbols:
                        self.ensure_trailing_strategy(sym)
                    time.sleep(15)
                else:
                    time.sleep(60)

            except Exception as e:
                console.print(f"[red]monitor_logic error: {e}[/red]")
                time.sleep(15)

    def _handle_new_trading_day(self, today_et: date):
        """Reset daily state when the ET date changes."""
        console.print(f"[bold cyan]New trading day ({today_et}) → resetting state[/bold cyan]")

        self.today = today_et
        self.trading_paused = False

        try:
            snap = self.get_account_snapshot()
            self.daily_start_equity = snap.get("equity", 0.0)
            console.print(f"[cyan]Daily start equity: ${self.daily_start_equity:,.2f}[/cyan]")
        except Exception as e:
            console.print(f"[red]Equity snapshot failed on day change: {e}[/red]")
            self.daily_start_equity = 0.0

        self.last_sell_prices.clear()
        self.load_previous_closes()
        self._sync_high_prices()
        self._load_last_sell_prices()


    def _should_auto_shutdown(self) -> bool:
        """Return True if auto-shutdown conditions are met."""
        if not getattr(self, "auto_shutdown_after_close", False):
            return False
        if self.trading_enabled:
            return False

        now = self.now_et()
        buffer = timedelta(minutes=getattr(self, "shutdown_buffer_minutes", 2))
        shutdown_after = datetime.combine(
            now.date(), dt_time(16, 0), tzinfo=self.ET
        ) + buffer

        return now >= shutdown_after

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

    def invalidate_open_orders_cache(self):
        self._open_orders_cache = None
        self._open_orders_cache_time = 0

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