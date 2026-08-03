
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
from datetime import datetime, timedelta, timezone, date
import schwabdev
from dotenv import load_dotenv
from rich.console import Console
from schwab_trader.config.bot.bot4_config import TradingConfig, SymbolConfig
from schwab_trader.utils.bot4_db import (
    init_db,
    log_transaction,
    save_state,
)

load_dotenv()
console = Console()


class TradingBot:
    """
    Main trading bot class implementing trailing momentum strategy.
    """

    def __init__(self, cfg: TradingConfig, mode: str = "cli", config_path=None):
        """
        Initialize the trading bot.
        
        Args:
            cfg: Trading configuration
            mode: Operating mode (cli/full/headless)
            config_path: Path to YAML config file
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
        
        self.current_market_prices = {sym: None for sym in self.symbols}
        self.previous_closes = {}
        self.holdings = {}
        self.last_sell_prices = {}
        
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
        
        console.print("[bold green]TradingBot (Trailing Momentum Strategy) initialized[/bold green]")

    @property
    def symbols(self):
        """Return list of configured trading symbols."""
        return list(self.symbols_config.keys())

    def _get_account_hash(self):
        """Retrieve Schwab account hash."""
        accounts = self.client.linked_accounts().json()
        return accounts[0]["hashValue"]

    def get_account_snapshot(self):
        """Get current account balances."""
        try:
            acc = self.client.account_details(self.account_hash).json()
            bal = acc.get("securitiesAccount", {}).get("currentBalances", {})
            return {
                "equity": float(bal.get("liquidationValue") or bal.get("equity") or 0.0),
                "cashBalance": float(bal.get("cashBalance") or 0.0),
                "buyingPower": float(bal.get("buyingPower") or 0.0),
            }
        except Exception as e:
            console.print(f"[red]Snapshot error: {e}[/red]")
            return {"equity": 0.0, "cashBalance": 0.0, "buyingPower": 0.0}

    def update_holdings_from_api(self):
        """Synchronize holdings from Schwab API."""
        try:
            pos = self.client.account_details(self.account_hash, fields="positions").json()
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
        except Exception as e:
            console.print(f"[red]Holdings update failed: {e}[/red]")

    def get_open_orders(self):
        """Get working orders with caching."""
        now = time.time()
        if self._open_orders_cache and now - self._open_orders_cache_time < self.open_orders_cache_ttl:
            return self._open_orders_cache
        try:
            to_time = datetime.now(timezone.utc)
            from_time = to_time - timedelta(days=30)
            resp = self.client.account_orders(
                self.account_hash, fromEnteredTime=from_time, toEnteredTime=to_time, status="WORKING"
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
        """Flatten nested order structure."""
        results = []
        if "orderLegCollection" in order:
            leg = order["orderLegCollection"][0]
            results.append({
                "orderId": order.get("orderId"),
                "symbol": leg["instrument"]["symbol"],
                "instruction": leg["instruction"],
                "quantity": leg.get("quantity"),
                "type": order.get("orderType"),
            })
        for child in order.get("childOrderStrategies", []):
            results.extend(self._flatten_order(child))
        return results

    def has_open_order_for_symbol(self, symbol: str, instruction=None) -> bool:
        """Check for open orders."""
        for o in self.get_open_orders():
            if o["symbol"] == symbol and (not instruction or o["instruction"] == instruction):
                return True
        return False

    def can_place_order(self, symbol: str) -> bool:
        """Anti-duplicate protection."""
        now = time.time()
        if now - self.last_order_placement.get(symbol, 0) < 25:
            return False
        self.last_order_placement[symbol] = now
        return True

    def cancel_all_orders_for_symbol(self, symbol: str):
        """Cancel all working orders for a symbol."""
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

    # ====================== ORDER PLACEMENT ======================
    def place_trailing_stop_sell(self, symbol: str, qty: int, trail_pct: float):
        """Place trailing stop sell order."""
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
            "orderLegCollection": [{
                "instruction": "SELL",
                "quantity": qty,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
            }]
        }
        try:
            self.client.place_order(self.account_hash, order)
            console.print(f"[green]Trailing SELL placed for {symbol} ({trail_pct}% trail)[/green]")
            self.invalidate_open_orders_cache()
            return True
        except Exception as e:
            console.print(f"[red]Trailing sell failed: {e}[/red]")
            return False

    def place_trailing_buy(self, symbol: str, qty: int, trail_pct: float):
        """Place trailing buy order on pullback."""
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
            "orderLegCollection": [{
                "instruction": "BUY",
                "quantity": qty,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
            }]
        }
        try:
            self.client.place_order(self.account_hash, order)
            console.print(f"[green]Trailing BUY placed for {symbol} ({trail_pct}% trail)[/green]")
            self.invalidate_open_orders_cache()
            return True
        except Exception as e:
            console.print(f"[red]Trailing buy failed: {e}[/red]")
            return False

    def load_previous_closes(self):
        """Load previous day close prices."""
        try:
            for sym in self.symbols:
                quote = self.client.quote(sym).json()
                if sym in quote:
                    prev = quote[sym].get("closePrice") or quote[sym].get("lastPrice")
                    if prev:
                        self.previous_closes[sym] = float(prev)
        except Exception as e:
            console.print(f"[red]Failed to load previous closes: {e}[/red]")

    def ensure_trailing_strategy(self, symbol: str):
        """Core strategy logic."""
        cfg = self.symbols_config.get(symbol)
        if not cfg:
            return
        price = self.current_market_prices.get(symbol)
        if not price or symbol not in self.previous_closes:
            return

        prev_close = self.previous_closes[symbol]
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

    def unified_receiver(self, message):
        """Handle streaming messages."""
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except:
                return
        if not isinstance(message, dict):
            return
        for item in message.get("data", []):
            if item.get("service") == "LEVELONE_EQUITIES":
                self._handle_price(item)
            elif item.get("service") in ("ACCT_ACTIVITY", "USER_ACTIVITY"):
                self._handle_fill(item)

    def _handle_price(self, item):
        """Process price updates and run strategy."""
        for content in item.get("content", []):
            sym = content.get("key")
            if sym in self.current_market_prices:
                try:
                    price = float(content.get("3") or 0)
                    if price > 0:
                        with self.lock:
                            self.current_market_prices[sym] = price
                        self.ensure_trailing_strategy(sym)
                except:
                    pass

    def _handle_fill(self, item):
        """Process order fills."""
        for content in item.get("content", []):
            if content.get("messageType", "").upper() not in ("FILL", "EXECUTION"):
                continue
            symbol = content.get("symbol")
            if not symbol or symbol not in self.symbols_config:
                continue
            side = content.get("instruction", "").upper()
            try:
                qty = float(content.get("quantity") or 0)
                price = float(content.get("price") or 0)
            except:
                continue

            console.print(f"[bold]{side} FILL: {symbol} @ ${price:.2f}[/bold]")
            with self.lock:
                if side == "SELL":
                    self.holdings.pop(symbol, None)
                    self.last_sell_prices[symbol] = price
                    log_transaction("SELL_FILLED", symbol, qty, price)
                    save_state(symbol, last_sell_price=price)
                elif side == "BUY":
                    self.holdings[symbol] = {"shares": qty, "buy_price": price}
                    log_transaction("BUY_FILLED", symbol, qty, price)
                    save_state(symbol, last_buy_price=price)

            self.update_holdings_from_api()
            self.invalidate_open_orders_cache()
            time.sleep(1)
            self.ensure_trailing_strategy(symbol)

    def start_stream(self):
        """Start real-time streaming."""
        if self.streamer:
            self.streamer.stop()
        self.streamer = schwabdev.Stream(self.client)
        self.streamer.start(receiver=self.unified_receiver)
        symbols_str = ",".join(self.symbols)
        if symbols_str:
            self.streamer.send(self.streamer.level_one_equities(symbols_str, "0,1,2,3"))
            self.streamer.send(self.streamer.account_activity("Account Activity", "0,1,2,3"))
        self.update_holdings_from_api()
        self.load_previous_closes()
        time.sleep(2)
        for sym in self.symbols:
            self.ensure_trailing_strategy(sym)

    def monitor_logic(self):
        """Background monitoring thread."""
        while self.running:
            time.sleep(30)
            if date.today() != self.today:
                self.daily_start_equity = self.get_account_snapshot()["equity"]
                self.today = date.today()
                self.last_sell_prices.clear()
                self.load_previous_closes()
            self.update_holdings_from_api()
            for sym in self.symbols:
                self.ensure_trailing_strategy(sym)

    def reload_config(self):
        """Hot reload configuration."""
        try:
            new_cfg = TradingConfig.load_from_file(self.config_path)
            with self.lock:
                self.risk_config = new_cfg.risk
                self.symbols_config = new_cfg.symbols
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
        """Start the bot."""
        self.start_stream()
        threading.Thread(target=self.monitor_logic, daemon=True, name="Monitor").start()
        console.print("[bold green]✅ Trailing Momentum Bot started[/bold green]")

    def stop(self):
        """Stop the bot."""
        self.running = False
        if self.streamer:
            self.streamer.stop()
