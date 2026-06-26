import os
import time
import threading
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

import schwabdev
from dotenv import load_dotenv
from rich.console import Console

from schwab_trader.config.bot.config import TradingConfig, SymbolConfig
from schwab_trader.utils.db import init_db, log_transaction, get_last_buy_price
from schwab_trader.orders.equity import sell_limit_sell_stoplimit_oco_dict


load_dotenv()
console = Console()


class TradingBot:
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

        self.current_market_prices = {sym: None for sym in self.symbols} # get assigned by _handle_price() which streams the market prices
        self.holdings = {}
        self.all_holdings = {}
        self.pending_buy_orders = set()
        self.auto_buy_allowed = {sym: True for sym in self.symbols}

        self.lock = threading.RLock()
        self.running = True
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        # Anti-duplicate protection
        self.last_order_placement = {}  # symbol -> timestamp

        # Caches
        self._open_orders_cache = None
        self._open_orders_cache_time = 0
        self.open_orders_cache_ttl = 30

        self.daily_start_equity = self.get_account_snapshot()["equity"]
        self.today = date.today()

        # Shutdown config
        self.auto_shutdown_after_close = getattr(cfg, 'auto_shutdown_after_close', True)
        self.shutdown_buffer_minutes = getattr(cfg, 'shutdown_buffer_minutes', 2)
        self.shutdown_on_weekends = getattr(cfg, 'shutdown_on_weekends', True)

        console.print("[bold green]TradingBot initialized[/bold green]")

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
                "equity": float(bal.get("liquidationValue") or bal.get("equity") or 0.0),
                "cashBalance": float(bal.get("cashBalance") or 0.0),
                "buyingPower": float(bal.get("buyingPower") or 0.0),
                "dayTradingBP": float(bal.get("dayTradingBuyingPower") or 0.0),
                "nonMarginableBP": float(bal.get("buyingPowerNonMarginableTrade") or 0.0),
            }
        except Exception as e:
            console.print(f"[red]Snapshot error: {e}[/red]")
            return {"equity": 0.0, "cashBalance": 0.0, "buyingPower": 0.0}

    def update_holdings_from_api(self):
        try:
            pos = self.client.account_details(self.account_hash, fields="positions").json()
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
                    entry = {"shares": long_qty, "buy_price": avg, "current_price": price, "day_pct": day_pct}
                    new_all[sym] = entry
                    if sym in self.symbols_config:
                        new_holdings[sym] = entry

            with self.lock:
                self.holdings = new_holdings
                self.all_holdings = new_all
                for sym in self.symbols:
                    if sym not in new_holdings:
                        self.auto_buy_allowed[sym] = True
        except Exception as e:
            console.print(f"[red]Holdings update failed: {e}[/red]")

    def get_open_orders(self):
        now = time.time()
        if self._open_orders_cache and now - self._open_orders_cache_time < self.open_orders_cache_ttl:
            return self._open_orders_cache

        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(days=30)

        try:
            resp = self.client.account_orders(
                self.account_hash,
                fromEnteredTime=from_time,
                toEnteredTime=to_time,
                status="WORKING"
            )
            orders = resp.json() or []
            flat = []
            for root in orders:
                for order in self._flatten_order(root):
                    flat.append(order)

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
            price = order.get("price") or order.get("stopPrice") or order.get("stopLimitPrice") or order.get("limitPrice")
            results.append({
                "orderId": order.get("orderId"),
                "symbol": leg["instrument"]["symbol"],
                "instruction": leg["instruction"],
                "quantity": leg.get("quantity"),
                "price": price,
                "orderStrategyType": order.get("orderStrategyType"),
                "type": order.get("orderType", "N/A"),
                "duration": order.get("duration", "N/A"),
            })
        for child in order.get("childOrderStrategies", []):
            results.extend(self._flatten_order(child))
        return results

    def has_open_sell_order(self, symbol: str) -> bool:
        return any(o["symbol"] == symbol and o["instruction"] in ("SELL", "SELL_SHORT")
                   for o in self.get_open_orders())

    def has_open_buy_order(self, symbol: str) -> bool:
        return any(o["symbol"] == symbol and o["instruction"] == "BUY"
                   for o in self.get_open_orders())

    def can_place_order(self, symbol: str) -> bool:
        now = time.time()
        last = self.last_order_placement.get(symbol, 0)
        if now - last < 25:
            return False
        self.last_order_placement[symbol] = now
        return True

    def cancel_all_orders_for_symbol(self, symbol: str):
        """Cancel all working orders for a symbol (important on config change)"""
        try:
            orders = self.get_open_orders()
            for o in orders:
                if o.get("symbol") == symbol:
                    order_id = o.get("orderId")
                    if order_id:
                        try:
                            self.client.cancel_order(self.account_hash, order_id)
                            console.print(f"[yellow]Cancelled order {order_id} for {symbol}[/yellow]")
                        except Exception as e:
                            console.print(f"[red]Failed to cancel order {order_id}: {e}[/red]")
            self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]Error cancelling orders for {symbol}: {e}[/red]")

    # ====================== ORDER PLACEMENT ======================
    def place_buy_order(self, symbol: str, qty: int) -> bool:
        if not self.risk_checks_pass(symbol) or not self.can_place_order(symbol):
            return False

        order = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {"instruction": "BUY", "quantity": qty, "instrument": {"symbol": symbol, "assetType": "EQUITY"}}
            ]
        }
        try:
            self.client.place_order(self.account_hash, order)
            console.print(f"[green]✓ BUY submitted for {symbol} x {qty}[/green]")
            self.invalidate_open_orders_cache()
            return True
        except Exception as e:
            console.print(f"[red]Buy failed: {e}[/red]")
            return False

    def submit_sell_bracket_oco(self, symbol: str):
        if not self.can_place_order(symbol):
            return
        if symbol not in self.holdings:
            return

        holding = self.holdings[symbol]
        cfg = self.symbols_config[symbol]
        qty = int(holding["shares"])
        price = self.current_market_prices.get(symbol) or holding.get("buy_price", 0)

        if price >= cfg.limit_sell_price * 1.01:
            self.place_immediate_sell(symbol)
            return

        stop_price = round(cfg.buy_target_price * (1 - cfg.stop_loss_pct / 100), 2)

        oco = sell_limit_sell_stoplimit_oco_dict(
            symbol=symbol,
            quantity=qty,
            sell_limit_price=str(cfg.limit_sell_price),
            sell_stop_price=str(stop_price),
            sell_stoplimit_price=str(round(stop_price * 0.99, 2)),
            session_sell_limit="NORMAL",
            session_sell_stoplimit="NORMAL",
            duration="DAY"
        )

        try:
            self.client.place_order(self.account_hash, oco)
            console.print(f"[green]✓ OCO Bracket placed for {symbol} (Limit ${cfg.limit_sell_price})[/green]")
            self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]OCO failed for {symbol}: {e}[/red]")

    def place_immediate_sell(self, symbol: str):
        if not self.can_place_order(symbol):
            return
        holding = self.holdings.get(symbol)
        if not holding:
            return

        order = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {"instruction": "SELL", "quantity": int(holding["shares"]), "instrument": {"symbol": symbol, "assetType": "EQUITY"}}
            ]
        }
        try:
            self.client.place_order(self.account_hash, order)
            console.print(f"[bold green]Immediate SELL executed for {symbol}[/bold green]")
            self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]Immediate sell failed: {e}[/red]")

    def invalidate_open_orders_cache(self):
        """This forces get_open_orders() to fetch fresh data from Schwab the next time it's called."""
        self._open_orders_cache = None
        self._open_orders_cache_time = 0

    # ====================== CORE ENSURE LOGIC ======================
    def ensure_orders(self, symbol: str):
        cfg = self.symbols_config.get(symbol)
        if not cfg:
            return

        price = self.current_market_prices.get(symbol)
        if not price:
            return

        has_position = symbol in self.holdings and self.holdings[symbol].get("shares", 0) > 0
        has_buy = self.has_open_buy_order(symbol)
        has_sell = self.has_open_sell_order(symbol)

        if not has_position and not has_buy:
            last_buy = get_last_buy_price(symbol)
            trigger = price <= cfg.buy_target_price or (
                last_buy and price <= last_buy * (1 - cfg.buy_drop_pct / 100)
            )
            if trigger and self.risk_checks_pass(symbol):
                console.print(f"[yellow]Ensuring BUY order for {symbol}[/yellow]")
                qty = cfg.fixed_shares
                self.place_buy_order(symbol, qty)

        elif has_position and not has_sell:
            console.print(f"[yellow]Ensuring SELL bracket for {symbol}[/yellow]")
            self.submit_sell_bracket_oco(symbol)

    # ====================== CONFIG RELOAD (ENHANCED) ======================
    def reload_config(self):
        """Hot-reload config and update live trade logic + orders"""
        try:
            new_cfg = TradingConfig.load_from_file(self.config_path)
            
            with self.lock:
                self.risk_config = new_cfg.risk
                self.symbols_config = new_cfg.symbols

                # Update price dict for new symbols
                for sym in self.symbols:
                    if sym not in self.current_market_prices:
                        self.current_market_prices[sym] = None
                        self.auto_buy_allowed[sym] = True

                # Remove old symbols that no longer exist in config
                for sym in list(self.current_market_prices.keys()):
                    if sym not in self.symbols_config:
                        self.current_market_prices.pop(sym, None)
                        self.auto_buy_allowed.pop(sym, None)

            console.print("[bold cyan]Config reloaded successfully[/bold cyan]")

            # Handle symbol changes
            old_symbols = set(self.symbols)
            new_symbols = set(self.symbols)
            removed = old_symbols - new_symbols
            added = new_symbols - old_symbols

            if removed or added:
                console.print(f"[yellow]Symbols changed → Removed: {removed} | Added: {added}[/yellow]")
                if self.streamer:
                    console.print("[yellow]Restarting streamer due to symbol change...[/yellow]")
                    self.start_stream()  # restarts with new symbols

            # Cancel stale orders and re-apply new logic
            for sym in self.symbols:
                self.cancel_all_orders_for_symbol(sym)
                time.sleep(0.5)  # small delay between cancels
                self.ensure_orders(sym)

            # Also run for removed symbols (cleanup)
            for sym in removed:
                self.cancel_all_orders_for_symbol(sym)

            console.print("[green]Trade logic and orders updated per new config[/green]")

        except Exception as e:
            console.print(f"[red]Config reload failed: {e}[/red]")

    # ====================== STREAM & FILL HANDLING ======================
    def unified_receiver(self, message):
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except:
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
        for content in item.get("content", []):
            sym = content.get("key")
            if sym in self.current_market_prices:
                try:
                    price = float(content.get("3") or 0) # "3" = last price
                    if price > 0:
                        with self.lock:
                            self.current_market_prices[sym] = price
                except:
                    pass

    def _handle_fill(self, item):
        for content in item.get("content", []):
            if content.get("messageType", "").upper() not in ("FILL", "EXECUTION", "ORDER_FILL"):
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

            console.print(f"[bold]{side} FILL: {symbol} @ ${price:.2f} x {qty}[/bold]")

            with self.lock:
                if side in ("SELL", "SELL_SHORT"):
                    self.holdings.pop(symbol, None)
                    self.auto_buy_allowed[symbol] = True
                    log_transaction("SELL_FILLED", symbol, qty, price)
                    time.sleep(2)
                    self.ensure_orders(symbol)

                elif side in ("BUY", "BUY_TO_COVER"):
                    self.holdings[symbol] = {"shares": qty, "buy_price": price}
                    log_transaction("BUY_FILLED", symbol, qty, price)
                    time.sleep(1.5)
                    self.ensure_orders(symbol)

            self.update_holdings_from_api()
            self.invalidate_open_orders_cache()

    def start_stream(self):
        if self.streamer:
            try:
                self.streamer.stop()
            except:
                pass

        self.streamer = schwabdev.Stream(self.client)
        self.streamer.start(receiver=self.unified_receiver)

        symbols_str = ",".join(self.symbols)
        if symbols_str:
            self.streamer.send(self.streamer.level_one_equities(symbols_str, "0,1,2,3"))
        self.streamer.send(self.streamer.account_activity("Account Activity", "0,1,2,3"))

        self.update_holdings_from_api()
        time.sleep(2)
        for sym in self.symbols:
            self.ensure_orders(sym)

    def monitor_logic(self):
        while self.running:
            time.sleep(15)
            if date.today() != self.today:
                self.daily_start_equity = self.get_account_snapshot()["equity"]
                self.today = date.today()
                self.trading_paused = False

            self.update_holdings_from_api()

            for sym in self.symbols:
                self.ensure_orders(sym)

    def risk_checks_pass(self, symbol: str) -> bool:
        if self.trading_paused:
            return False
        snap = self.get_account_snapshot()
        if snap["equity"] < getattr(self.risk_config, 'min_account_equity', 5000):
            self.trading_paused = True
            return False
        if len(self.holdings) >= getattr(self.risk_config, 'max_positions', 4):
            return False
        return True

    def start(self):
        self.start_stream()
        threading.Thread(target=self.monitor_logic, daemon=True, name="MonitorLogic").start()
        console.print("[bold green]✅ Bot started[/bold green]")

    def stop(self):
        self.running = False
        if self.streamer:
            self.streamer.stop()