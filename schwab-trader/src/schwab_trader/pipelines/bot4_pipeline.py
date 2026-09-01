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
import time
import threading
import json
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
)

load_dotenv()
console = Console()


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
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        self.last_order_placement = {}
        self._open_orders_cache = None
        self._open_orders_cache_time = 0
        self.open_orders_cache_ttl = 30

        self.daily_start_equity = self.get_account_snapshot()["equity"]
        self.today = date.today()

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
                if long_qty > 0 and sym in self.symbols_config:
                    avg = float(p.get("averagePrice") or 0)
                    new_holdings[sym] = {"shares": long_qty, "buy_price": avg}
            with self.lock:
                self.holdings = new_holdings
                for sym in self.symbols:
                    if sym not in new_holdings:
                        self.auto_buy_allowed[sym] = True
            self._sync_high_prices()
        except Exception as e:
            console.print(f"[red]Holdings update failed: {e}[/red]")

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
            results.append(
                {
                    "orderId": order.get("orderId"),
                    "symbol": leg["instrument"]["symbol"],
                    "instruction": leg["instruction"],
                    "quantity": leg.get("quantity"),
                    "type": order.get("orderType"),
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
        now = time.time()
        if now - self.last_order_placement.get(symbol, 0) < 25:
            return False
        self.last_order_placement[symbol] = now
        return True

    def cancel_all_orders_for_symbol(self, symbol: str):
        try:
            for o in self.get_open_orders():
                if o.get("symbol") == symbol:
                    oid = o.get("orderId")
                    if oid:
                        self.client.cancel_order(self.account_hash, oid)
                        console.print(f"[yellow]Cancelled {oid} for {symbol}[/yellow]")
            self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]Cancel error: {e}[/red]")

    # ====================== ORDER PLACEMENT (Bot4 original) ======================
    def place_trailing_stop_sell(self, symbol: str, qty: int, trail_pct: float):
        if not self.can_place_order(symbol):
            return False
        order = {
            "orderType": "TRAILING_STOP",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "stopPriceOffset": str(trail_pct),
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
        if not self.can_place_order(symbol):
            return False
        order = {
            "orderType": "TRAILING_STOP",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "stopPriceOffset": str(trail_pct),
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

    # ====================== Bot3-style HWM / price helpers ======================
    def _sync_high_prices(self):
        """Same as Bot3 – seed / refresh HWM from DB or average cost."""
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
        """Fallback loader – also writes into day_prices['close']."""
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
        if not price:
            return

        prev_close = self.day_prices.get(symbol, {}).get("close")
        if not prev_close:
            return

        pct_up = ((price - prev_close) / prev_close) * 100
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
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except Exception:
                return
        if not isinstance(message, dict):
            return

        for item in message.get("data", []):
            service = item.get("service")
            if service == "LEVELONE_EQUITIES":
                self._handle_price(item)
            elif service in ("ACCT_ACTIVITY", "USER_ACTIVITY"):
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
        """Exactly the same detailed ACCT_ACTIVITY handling as Bot3."""
        for content in item.get("content", []):
            msg_type = content.get("2", "")
            msg_data = content.get("3", "")

            # --- logging (same as Bot3) ---
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
        time.sleep(2)
        for sym in self.symbols:
            self.ensure_trailing_strategy(sym)

    def monitor_logic(self):
        while self.running:
            time.sleep(30)
            if date.today() != self.today:
                self.daily_start_equity = self.get_account_snapshot()["equity"]
                self.today = date.today()
                self.last_sell_prices.clear()
                self.load_previous_closes()
                self._sync_high_prices()
            self.update_holdings_from_api()
            for sym in self.symbols:
                self.ensure_trailing_strategy(sym)

    def reload_config(self):
        try:
            new_cfg = TradingConfig.load_from_file(self.config_path)
            with self.lock:
                self.risk_config = new_cfg.risk
                self.symbols_config = new_cfg.symbols

                # keep day_prices in sync with new symbol list
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

            self._sync_high_prices()
            console.print("[bold cyan]Config reloaded successfully[/bold cyan]")

            for sym in self.symbols:
                self.cancel_all_orders_for_symbol(sym)
            self.start_stream()
        except Exception as e:
            console.print(f"[red]Config reload failed: {e}[/red]")

    def invalidate_open_orders_cache(self):
        self._open_orders_cache = None
        self._open_orders_cache_time = 0

    def start(self):
        self.start_stream()
        threading.Thread(
            target=self.monitor_logic, daemon=True, name="Monitor"
        ).start()
        console.print("[bold green]✅ Trailing Momentum Bot started[/bold green]")

    def stop(self):
        self.running = False
        if self.streamer:
            self.streamer.stop()