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
    save_state,
)

load_dotenv()
console = Console()


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
        self.current_market_prices = {sym: None for sym in self.symbols}
        self.holdings = {}
        self.all_holdings = {}
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
        self.open_orders_cache_ttl = 30

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
        from_time = to_time - timedelta(days=30)
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
                    "type": order.get("orderType", "N/A"),
                    "duration": order.get("duration", "N/A"),
                }
            )
        for child in order.get("childOrderStrategies", []):
            results.extend(self._flatten_order(child))
        return results

    def has_open_sell_order(self, symbol: str) -> bool:
        return any(
            o["symbol"] == symbol and o["instruction"] in ("SELL", "SELL_SHORT")
            for o in self.get_open_orders()
        )

    def has_open_buy_order(self, symbol: str) -> bool:
        return any(
            o["symbol"] == symbol and o["instruction"] == "BUY"
            for o in self.get_open_orders()
        )

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
    def place_buy_order(self, symbol: str, qty: int) -> bool:
        """Submit a market buy order."""
        if not self.risk_checks_pass(symbol) or not self.can_place_order(symbol):
            return False
        order = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
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
            self.client.place_order(self.account_hash, order)
            console.print(f"[green]✓ BUY submitted for {symbol} x {qty}[/green]")
            self.invalidate_open_orders_cache()
            return True
        except Exception as e:
            console.print(f"[red]Buy failed: {e}[/red]")
            return False

    def submit_sell_bracket_oco(self, symbol: str):
        """
        Exit strategy:
         < trail_activation_price < limit_sell_price
        - If Price > limit_sell_price * 1.01, market sell
        - If price >= trail_activation_price  → place Trailing Stop + Limit OCO
        - Otherwise place classic Stop + Limit OCO (protective)
        - If the price starts to climbing before touching the Stop value and reaches the trail activation price, then the ensure_orders() cancels the existing protective orders and replaces with a Trailing Stop _ Limit OCO order
        """
        if not self.can_place_order(symbol) or symbol not in self.holdings:
            return

        holding = self.holdings[symbol]
        cfg = self.symbols_config[symbol]
        qty = int(holding["shares"])
        price = self.current_market_prices.get(symbol) or holding.get("buy_price", 0)

        # Scenario 1 -- Immediate market sell if already past take-profit hard limit
        if price >= cfg.limit_sell_price * 1.01:
            self.place_immediate_sell(symbol)
            return

        # Scenario 2 -- Trailing + Limit when above the trail_activation_price  and below the take-profit hard limit
        if price >= cfg.trail_activation_price:
            oco = sell_trailing_sell_limit_oco_dict(
                symbol=symbol,
                quantity=qty,
                sell_limit_price=str(cfg.limit_sell_price),
                stop_price_offset=cfg.trail_offset_pct,
                session="NORMAL",
                duration="DAY",
            )
            try:
                self.client.place_order(self.account_hash, oco)
                console.print(
                    f"[green]✓ Trailing+Limit OCO placed for {symbol} "
                    f"(Trail {cfg.trail_offset_pct}% | Limit ${cfg.limit_sell_price})[/green]"
                )
                self.invalidate_open_orders_cache()
            except Exception as e:
                console.print(f"[red]Trailing OCO failed for {symbol}: {e}[/red]")
            return

        # Scenario 3 -- Classic protective OCO when below the trail_activation_price
        actual_buy_price = float(holding.get("buy_price") or 0)
        # Note: the bot uses the Schwab API's average cost (averagePrice), not from the SQLite log.
        reference_price = (
            actual_buy_price if actual_buy_price > 0 else cfg.buy_target_price
        )

        # Prefer fixed $ stop when configured; otherwise use %
        if cfg.stop_loss_dollar and cfg.stop_loss_dollar > 0:
            stop_price = round(reference_price - cfg.stop_loss_dollar, 2)
            stop_source = f"${cfg.stop_loss_dollar} below entry"
        else:
            stop_price = round(reference_price * (1 - cfg.stop_loss_pct / 100), 2)
            stop_source = f"{cfg.stop_loss_pct}% below entry"

        # Safety: stop must stay below current price
        if stop_price >= price:
            stop_price = round(price * 0.99, 2)

        oco = sell_limit_sell_stoplimit_oco_dict(
            symbol=symbol,
            quantity=qty,
            sell_limit_price=str(cfg.limit_sell_price),
            sell_stop_price=str(stop_price),
            sell_stoplimit_price=str(round(stop_price * 0.99, 2)),
            session_sell_limit="NORMAL",
            session_sell_stoplimit="NORMAL",
            duration="DAY",
        )
        try:
            self.client.place_order(self.account_hash, oco)
            console.print(
                f"[green]✓ Classic OCO placed for {symbol} "
                f"(Stop ${stop_price} [{stop_source}] | Limit ${cfg.limit_sell_price})[/green]"
            )
            self.invalidate_open_orders_cache()
        except Exception as e:
            console.print(f"[red]OCO failed for {symbol}: {e}[/red]")

    def place_immediate_sell(self, symbol: str):
        """Immediately liquidate position."""
        if not self.can_place_order(symbol) or symbol not in self.holdings:
            return
        holding = self.holdings[symbol]
        order = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
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
            self.client.place_order(self.account_hash, order)
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
        """Ensure correct order state for a symbol."""
        if not getattr(self, "trading_enabled", False):
            return
        cfg = self.symbols_config.get(symbol)
        if not cfg:
            return
        price = self.current_market_prices.get(symbol)
        if not price:
            return

        has_position = (
            symbol in self.holdings and self.holdings[symbol].get("shares", 0) > 0
        )
        has_buy = self.has_open_buy_order(symbol)
        has_sell = self.has_open_sell_order(symbol)

        if not has_position and not has_buy:
            last_buy = get_last_buy_price(symbol)
            trigger = price <= cfg.buy_target_price or (
                last_buy and price <= last_buy * (1 - cfg.buy_drop_pct / 100)
            )
            if trigger and self.risk_checks_pass(symbol):
                console.print(f"[yellow]Ensuring BUY order for {symbol}[/yellow]")
                self.place_buy_order(symbol, cfg.fixed_shares)
        elif has_position and not has_sell:
            console.print(f"[yellow]Ensuring SELL bracket for {symbol}[/yellow]")
            self.submit_sell_bracket_oco(symbol)

        elif has_position and has_sell and price >= cfg.trail_activation_price:
            # Check if we already have a trailing order; if not, replace
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

    def reload_config(self):
        """Hot-reload configuration."""
        try:
            new_cfg = TradingConfig.load_from_file(self.config_path)
            with self.lock:
                self.risk_config = new_cfg.risk
                self.symbols_config = new_cfg.symbols
                for sym in self.symbols:
                    if sym not in self.current_market_prices:
                        self.current_market_prices[sym] = None
                        self.auto_buy_allowed[sym] = True
                for sym in list(self.current_market_prices.keys()):
                    if sym not in self.symbols_config:
                        self.current_market_prices.pop(sym, None)
                        self.auto_buy_allowed.pop(sym, None)

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
    def unified_receiver(self, message):
        """Dispatch streaming messages."""
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
        """Process price updates."""
        for content in item.get("content", []):
            sym = content.get("key")
            if sym in self.current_market_prices:
                try:
                    price = float(content.get("3") or 0) # 3 - Last Price (Last trade)
                    if price > 0:
                        with self.lock:
                            self.current_market_prices[sym] = price
                except:
                    pass

    def _handle_fill(self, item):
        """
        Process order execution events.
        Updates holdings, transaction history, and order state after buy or
        sell executions before re-evaluating the trading strategy.
        """
        for content in item.get("content", []):
            if content.get("messageType", "").upper() not in (
                "FILL",
                "EXECUTION",
                "ORDER_FILL",
            ):
                continue

            symbol = content.get("symbol")
            if not symbol or symbol not in self.symbols_config:
                continue

            side = content.get("instruction", "").upper()

            try:
                qty = float(content.get("quantity") or 0)
                price = float(content.get("price") or 0)
                order_id = content.get("orderId") or content.get("order_id")
            except:
                continue

            console.print(f"[bold]{side} FILL: {symbol} @ ${price:.2f} x {qty}[/bold]")

            with self.lock:
                if side in ("SELL", "SELL_SHORT"):
                    self.holdings.pop(symbol, None)
                    self.auto_buy_allowed[symbol] = True

                    # Log the transaction
                    log_transaction(
                        action="SELL_FILLED",
                        symbol=symbol,
                        qty=qty,
                        price=price,
                        order_id=order_id,
                        order_status="FILLED",
                        note="OCO or manual sell",
                    )

                    # Update state: record sell + reset buy fields
                    save_state(
                        symbol=symbol,
                        last_sell_price=price,
                        last_sell_qty=qty,
                        last_buy_price=None,  # Position closed
                        last_buy_qty=None,
                    )

                    time.sleep(2)
                    self.ensure_orders(symbol)

                elif side in ("BUY", "BUY_TO_COVER"):
                    self.holdings[symbol] = {"shares": qty, "buy_price": price}

                    # Log the transaction
                    log_transaction(
                        action="BUY_FILLED",
                        symbol=symbol,
                        qty=qty,
                        price=price,
                        order_id=order_id,
                        order_status="FILLED",
                        note="Auto buy",
                    )

                    # Update state: record buy
                    save_state(
                        symbol=symbol,
                        last_buy_price=price,
                        last_buy_qty=qty,
                    )

                    time.sleep(1.5)
                    self.ensure_orders(symbol)

            # Refresh data after any fill
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

        symbols_str = ",".join(self.symbols)
        if symbols_str:
            self.streamer.send(self.streamer.level_one_equities(symbols_str, "0,1,2,3"))
            # Schwabdev translation map for fields.
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

            self.streamer.send(
                self.streamer.account_activity("Account Activity", "0,1,2,3")
            )
            
            # https://tylerebowers.github.io/Schwabdev/?source=pages%2Fstream.html

        self.update_holdings_from_api()
        time.sleep(2)
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
        """Evaluate risk constraints."""
        if not getattr(self, "trading_enabled", False):
            return False
        if self.trading_paused:
            return False
        snap = self.get_account_snapshot()
        if snap["equity"] < getattr(self.risk_config, "min_account_equity", 5000):
            self.trading_paused = True
            return False
        if len(self.holdings) >= getattr(self.risk_config, "max_positions", 4):
            return False
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
        """Stop the trading bot."""
        self.running = False
        if self.streamer:
            self.streamer.stop()


"""
WebSocket streaming
streamer = schwabdev.Stream(client) - create objects that know how to authenticate and establish the streaming connection.
streamer.start(receiver=print) - the streaming class manager.
Conceptually, schwabdev eventually does something equivalent to: websocket.connect("wss://....") where wss means WebSocket Secure. 

streamer.send(streamer.level_one_equities("AAPL", 0,1,2,3")) - subscription message

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
self.current_market_prices[sym] = price

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

streamer.send(streamer.level_one_equities("AMD,INTC", "0,1,2,3,4,5,6,7"))
{
    "data":[
        {
            "service":"LEVELONE_EQUITIES", 
            "timestamp":1786461735280,
            "command":"SUBS",
            "content":[
                {
                    "key":"AMD",
                    "delayed":false,
                    "assetMainType":"EQUITY",
                    "assetSubType":"COE",
                    "cusip":"007903107",
                    "1":470.77,
                    "2":470.99,
                    "3":470.925,
                    "4":100,
                    "5":600,
                    "6":"Z",
                    "7":"Q",
                    },
                    {
                        "key":"INTC",
                        "delayed":false,
                        "assetMainType":"EQUITY",
                        "assetSubType":"COE",
                        "cusip":"458140100",
                        "1":97.47,
                        "2":97.5,
                        "3":97.485,
                        "4":200,
                        "5":800,
                        "6":"Q",
                        "7":"Q",
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

