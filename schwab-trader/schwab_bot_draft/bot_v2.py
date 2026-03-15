# bot.py
import argparse
import os
import time
import hashlib
import json
import datetime
import schwabdev
import threading

import dash_bootstrap_components as dbc
import pandas as pd

from dotenv import load_dotenv
from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.prompt import Confirm

from schwab_bot.config import CONFIG, RISK_CONFIG
from schwab_bot.db import init_db, log_transaction, save_state, get_last_buy_price, load_state

from dash import Dash, dcc, html, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate

# import sys
# from pathlib import Path
# sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# print(sys.path)
from src.schwab_trader.orders.utils import extract_final_executions



load_dotenv()
console = Console()
CACHE_TTL_SECONDS = 60


class TradingBot:
    def __init__(self, mode: str = "cli"):
        """Initialize client, caches, state flags, and start DB."""
        init_db()
        self.client = schwabdev.Client(
            os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
        )
        self.mode = mode
        self.streamer = schwabdev.Stream(self.client)

        self._symbols = CONFIG.keys()

        self.current_prices = {sym: None for sym in self._symbols}
        self.holdings = {}

        # ── Duplicate-buy protection + manual approval ─────────────────────
        self.auto_buy_allowed = {
            sym: True for sym in self._symbols
        }  # True = next trigger is AUTO
        self.pending_buy_orders = (
            set()
        )  # prevents double-submit while order is in flight

        self.last_holdings_sync = time.time()
        self.first_api_pull = True
        self.HOLDINGS_SYNC_INTERVAL = (
            60  # 1 minutes, first start has to wait to get values populated
        )

        self.lock = (
            threading.Lock()
        )  # ensures only one thread can execute a critical section at a time
        self.running = True
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        # live for CACHE_TTL_SECONDS, less frequency to all API
        self._account_snapshot_cache_time = None
        self._equity_cache = None
        self._buying_power_cache = None
        self._cash_balance = None
        self._day_trading_bp = None
        self._non_marginable_bp = None

        # Open orders cache
        self._open_orders_cache = None
        self._open_orders_cache_time = None
        self.OPEN_ORDERS_CACHE_TTL = 45  # seconds, 30–90 is a good range

        # Daily risk tracking
        self.daily_start_equity = self.get_account_snapshot()["equity"]
        self.today = datetime.date.today()

        # console.print(
        #     f"[bold cyan]Account Equity at start: ${self.daily_start_equity:,.2f}[/bold cyan]"
        # )

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
        # If self._equity_cache has been assinged with a value (other than initial None), the API will only be called every CACHE_TTL_SECONDS, less frequently.
        if (
            self._equity_cache is not None
            and now - self._account_snapshot_cache_time < CACHE_TTL_SECONDS
        ):
            return {
                "equity": self._equity_cache,
                "buyingPower": self._buying_power_cache,
                "cashBalance": self._cash_balance,
                "dayTradingBP": self._day_trading_bp,
                "nonMarginableBP": self._non_marginable_bp,
            }

        try:
            acc = self.client.account_details(self.account_hash).json()
            bal = acc.get("securitiesAccount", {}).get("currentBalances", {})

            snapshot = {
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

            self._equity_cache = snapshot["equity"]
            self._buying_power_cache = snapshot["buyingPower"]
            self._cash_balance = snapshot["cashBalance"]
            self._day_trading_bp = snapshot["dayTradingBP"]
            self._non_marginable_bp = snapshot["nonMarginableBP"]

            return snapshot

        except Exception as e:
            console.print(f"[dim red]Account snapshot failed: {e}[/dim red]")
            return {
                "equity": 0.0,
                "cashBalance": 0.0,
                "buyingPower": 0.0,
                "dayTradingBP": 0.0,
                "nonMarginableBP": 0.0,
            }

    # SUGGESTION: Consider calling load_state() once here (or in monitor_logic)
    # to cache last_buy_price/qty in memory instead of 4 separate DB hits per loop.
    def update_holdings_from_api(self):
        """Sync current positions from Schwab API (called on startup + every 60 s)."""
        try:
            pos = self.client.account_details(
                self.account_hash, fields="positions"
            ).json()
            positions = pos.get("securitiesAccount", {}).get("positions", [])
            new_h = {}
            for p in positions:
                sym = p["instrument"]["symbol"]
                if sym in self._symbols and float(p.get("longQuantity", 0)) > 0:
                    new_h[sym] = {
                        "shares": float(p["longQuantity"]),
                        "buy_price": p.get("averagePrice", 0),
                    }
            with self.lock:
                self.holdings = new_h
                # If we somehow have no position but flag is locked, unlock it
                for sym in list(self.auto_buy_allowed.keys()):
                    if sym not in new_h:
                        self.auto_buy_allowed[sym] = True
        except:
            pass

    def force_sync_holdings(self):
        """Call after any trade fill for instant accuracy."""
        self.update_holdings_from_api()
        self.last_holdings_sync = time.time()

    # =============================================================
    # ORDER QUERYING (open orders + safety checks)
    # =============================================================
    def iter_orders(self, order, cancelable_only=False):
        """
        Yield flattened order records from a Schwab/TD Ameritrade order tree.
        """
        # Skip non-cancelable orders if requested
        if cancelable_only and not order.get("cancelable", False):
            return

        if "orderLegCollection" in order:
            # find price (price, stopPrice, etc.)
            price_value = order.get("price")
            if price_value is None:
                for k, v in order.items():
                    if "price" in k.lower():
                        price_value = v
                        break

            # merge all legs
            legs = []
            for leg in order["orderLegCollection"]:
                legs.append(
                    {
                        "instruction": leg["instruction"],
                        "symbol": leg["instrument"]["symbol"],
                        "quantity": leg["quantity"],
                    }
                )

            extracted = {
                "orderId": order.get("orderId"),
                "orderType": order.get("orderType"),
                "duration": order.get("duration"),
                "price": price_value,
                "legs": legs,
            }

            yield extracted

        # recurse into child orders
        for child in order.get("childOrderStrategies", []):
            yield from self.iter_orders(child, cancelable_only=cancelable_only)

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
            and now - self._open_orders_cache_time < self.OPEN_ORDERS_CACHE_TTL
        ):
            return self._open_orders_cache

        from_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=30, hours=0, minutes=0
        )
        to_time = datetime.datetime.now(datetime.timezone.utc)

        try:
            # Use your confirmed method name
            response = self.client.account_orders(
                self.account_hash,
                fromEnteredTime=from_time,
                toEnteredTime=to_time,
                # status='WORKING',
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

    # =============================================================
    # RISK MANAGEMENT
    # =============================================================
    def calculate_shares(self, symbol, buy_price):
        """Determine buy quantity: fixed_shares (preferred) or risk-based (currently commented)."""
        cfg = CONFIG.get(symbol, {})
        fixed = cfg.get("fixed_shares", 0)

        if fixed > 0:
            # Manual / fixed mode takes priority
            shares = fixed
            console.print(
                f"[cyan]Using fixed quantity for {symbol}: {shares} shares[/cyan]"
            )
        # else:
        #     # Fall back to risk-based sizing
        #     if buy_price <= 0:
        #         shares = RISK_CONFIG["default_shares"]
        #     else:
        #         equity = self.get_account_snapshot()["equity"]
        #         risk_dollars = equity * (RISK_CONFIG["risk_per_trade_pct"] / 100)
        #         stop_pct = cfg.get("stop_loss_pct", 5.0) / 100
        #         stop_distance = buy_price * stop_pct

        #         if stop_distance <= 0:
        #             shares = RISK_CONFIG["default_shares"]
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
        if daily_pnl_pct <= -RISK_CONFIG["max_daily_loss_pct"]:
            console.print(
                f"[bold red]🚨 DAILY LOSS LIMIT HIT ({daily_pnl_pct:.1f}%) — TRADING PAUSED[/bold red]"
            )
            self.trading_paused = True
            return False

        # Minimum equity guard
        if current_equity < RISK_CONFIG["min_account_equity"]:
            console.print(
                f"[bold red]🚨 ACCOUNT BELOW MIN EQUITY (${current_equity:,.0f}) — TRADING PAUSED[/bold red]"
            )
            self.trading_paused = True
            return False

        # Max positions
        if len(self.holdings) >= RISK_CONFIG["max_positions"]:
            console.print("[yellow]Max positions reached — skipping new buys[/yellow]")
            return False

        # Buying power check - Use real calculated qty instead
        qty = self.calculate_shares(symbol, self.current_prices.get(symbol, 0))
        estimated_cost = self.current_prices.get(symbol, 0) * qty

        if bp < estimated_cost * 1.1:
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
        """Update self.current_prices from LEVELONE_EQUITIES stream (field 3 = last)."""
        content_list = item.get("content", [])
        if not content_list:
            return

        for content in content_list:
            symbol = content.get("key")
            if symbol not in self.current_prices:
                continue

            prev_close = content.get("16")  # previous close
            last_str = content.get("3")  # last price
            if last_str is not None:
                try:
                    last_price = float(last_str)
                    if last_price > 0:
                        with self.lock:
                            self.current_prices[symbol] = last_price
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
            #                     self.current_prices[symbol] = mid
            #         except:
            #             pass

    def handle_account_activity(self, item):
        """Process EXECUTION / FILL messages, update holdings, place bracket, reset flags."""
        content_list = item.get("content", [])
        for content in content_list:
            # We only care about real executions / fills (ignore heartbeats, subscriptions, etc.)
            msg_type = content.get("messageType", "").upper()

            if msg_type not in ("EXECUTION", "FILL", "ORDER_FILL"):
                continue
            # Extract symbol from different possible locations in the message
            symbol = content.get("symbol") or content.get("instrument", {}).get(
                "symbol"
            )
            if not symbol or symbol not in self._symbols:
                continue  # ignore if not one of our watched stocks

            qty_str = content.get("quantity") or content.get("filledQuantity", "0")
            price_str = content.get("price") or content.get("executionPrice", "0")

            try:
                qty = float(qty_str)
                price = float(price_str)
            except (ValueError, TypeError):
                continue

            instruction = content.get("instruction", "").upper()

            with self.lock:
                if instruction in ("SELL", "SELL_SHORT"):
                    if symbol in self.holdings:
                        del self.holdings[symbol]
                        # Removes the symbol from the internal holdings dictionary, the bot now considers the position flat/closed
                        log_transaction(
                            action="SELL_FILLED",
                            symbol=symbol,
                            qty=qty,
                            price=price,
                            note="OCO fill via ACCT_ACTIVITY",
                            order_id=None,
                            order_status="FILLED",
                        )
                        # Reset for next sycle
                        self.auto_buy_allowed[symbol] = True
                        console.print(
                            f"[green]→ Cycle reset: AUTO BUY re-enabled for {symbol}[/green]"
                        )

                elif instruction in ("BUY", "BUY_TO_COVER"):
                    with self.lock:  # SUGGESTION: everything under one lock for consistency
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
                            note="Initial buy fill via ACCT_ACTIVITY",
                            order_id=None,  # ← rarely present in fill message
                            order_status="FILLED",
                        )
                        self.place_bracket_orders(symbol, price)
                        self.save_state(symbol, price, qty)
                        self.force_sync_holdings()
                        self.invalidate_open_orders_cache()
                        # # Clear pending
                        # if symbol in self.pending_buy_orders:
                        #     self.pending_buy_orders.remove(symbol)

    def start_stream(self):
        """Start the streamer and subscribe to price + account activity feeds."""
        self.streamer.start(receiver=self.unified_receiver)

        # Quotes
        self.streamer.send(
            self.streamer.level_one_equities(
                ",".join(self._symbols),
                "0,1,2,3,4,5,6,7,8,9,10,12,13,14,15,16,17,18",  # 3 = last price, 16 = previous close price
            )
        )  # https://schwab-py.readthedocs.io/en/latest/streaming.html#schwab.streaming.StreamClient.LevelOneEquityFields
        console.print(
            f"[green]→ Subscribed to LEVELONE_EQUITIES for {self._symbols}[/green]"
        )

        # Account activity (convenience method handles subkey automatically)
        self.streamer.send(
            self.streamer.account_activity("Account Activity", "0,1,2,3")
        )
        console.print(
            "[green]→ Subscribed to ACCT_ACTIVITY (fills, executions)[/green]"
        )

        console.print(
            "[bold green]Streaming active — quotes + account activity[/bold green]"
        )

    # =============================================================
    # ORDER PLACEMENT
    # =============================================================
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
                price=self.current_prices.get(symbol, 0),
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

    def place_bracket_orders(self, symbol, buy_price):
        """Place GTC OCO bracket (LIMIT SELL + STOP LOSS) right after a buy fill."""
        # (unchanged from previous version — GTC OCO)
        cfg = CONFIG[symbol]
        qty = self.holdings[symbol]["shares"]
        limit_price = round(buy_price * (1 + cfg["limit_sell_pct"] / 100), 2)
        stop_price = round(buy_price * (1 - cfg["stop_loss_pct"] / 100), 2)

        oco = {
            "orderType": "OCO",
            "session": "NORMAL",
            "duration": "GTC",
            "orderStrategyType": "OCO",
            "childOrderStrategies": [
                {  # LIMIT SELL
                    "orderType": "LIMIT",
                    "session": "NORMAL",
                    "duration": "GTC",
                    "price": str(limit_price),
                    "orderLegCollection": [
                        {
                            "instruction": "SELL",
                            "quantity": qty,
                            "instrument": {"symbol": symbol, "assetType": "EQUITY"},
                        }
                    ],
                },
                {  # STOP LOSS
                    "orderType": "STOP",
                    "session": "NORMAL",
                    "duration": "GTC",
                    "stopPrice": str(stop_price),
                    "orderLegCollection": [
                        {
                            "instruction": "SELL",
                            "quantity": qty,
                            "instrument": {"symbol": symbol, "assetType": "EQUITY"},
                        }
                    ],
                },
            ],
        }

        try:
            resp = self.client.place_order(self.account_hash, oco)
            location = resp.headers.get("Location")
            order_id = location.split("/")[-1] if location else None
            console.print("[green]OCO placed[/green]")
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

        table = Table(
            title=f"Schwab Bot ─ {datetime.datetime.now().strftime('%H:%M:%S')}"
        )
        table.add_column("Symbol", style="cyan")
        table.add_column("Price", justify="right")
        table.add_column("Position", justify="right")
        table.add_column("Avg Buy", justify="right")
        table.add_column("P/L %", justify="right")
        table.add_column("Status")

        with self.lock:
            for sym in self._symbols:
                price = self.current_prices.get(sym)
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

        risk_used = len(self.holdings) / RISK_CONFIG["max_positions"] * 100
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

        return Panel(
            Columns([table, ord_table, acc_panel], equal=True, expand=True),
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
                if datetime.date.today() != self.today:
                    self.daily_start_equity = self.get_account_snapshot()["equity"]
                    self.today = datetime.date.today()
                    self.trading_paused = False
                if self.first_api_pull:
                    self.update_holdings_from_api()
                    self.first_api_pull = False
                now = time.time()
                if now - self.last_holdings_sync > self.HOLDINGS_SYNC_INTERVAL:
                    self.update_holdings_from_api()
                    self.last_holdings_sync = now

                with self.lock:
                    holdings_copy = dict(self.holdings)
                    prices_copy = dict(self.current_prices)
                    view = {}
                    for sym in self._symbols:
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

            if datetime.date.today() != self.today:
                self.daily_start_equity = self.get_account_snapshot()["equity"]
                self.today = datetime.date.today()
                self.trading_paused = False

            if self.first_api_pull:
                self.update_holdings_from_api()
                self.first_api_pull = False
            now = time.time()
            if now - self.last_holdings_sync > self.HOLDINGS_SYNC_INTERVAL:
                self.update_holdings_from_api()
                self.last_holdings_sync = now

            with self.lock:
                holdings_copy = dict(self.holdings)
                pending_copy = set(self.pending_buy_orders)
                auto_copy = dict(self.auto_buy_allowed)
                prices_copy = dict(self.current_prices)

            # ── Buy trigger logic (exactly the same as before) ──
            for sym in self._symbols:
                if sym in holdings_copy and holdings_copy[sym].get("shares", 0) > 0:
                    continue
                price = prices_copy.get(sym)
                if not price:
                    continue
                cfg = CONFIG[sym]
                last_buy = get_last_buy_price(sym)
                trigger = (price <= cfg.get("buy_target_price", float("inf"))) or (
                    last_buy and price <= last_buy * (1 - cfg["buy_drop_pct"] / 100)
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

                if datetime.date.today() != self.today:  # in case of overnight runs
                    self.daily_start_equity = self.get_account_snapshot()["equity"]
                    self.today = datetime.date.today()
                    self.trading_paused = False

                # only sync after HOLDINGS_SYNC_INTERVAL
                if self.first_api_pull:  # No waiting when first start
                    self.update_holdings_from_api()
                    self.first_api_pull = False
                now = time.time()
                if now - self.last_holdings_sync > self.HOLDINGS_SYNC_INTERVAL:
                    self.update_holdings_from_api()
                    self.last_holdings_sync = now

                with self.lock:
                    # # Copy all mutable state UNDER LOCK so streamer thread can't change it while we decide
                    holdings_copy = dict(self.holdings)
                    pending_copy = set(self.pending_buy_orders)
                    auto_copy = dict(self.auto_buy_allowed)
                    prices_copy = dict(self.current_prices)

                    view = {}
                    for sym in self._symbols:
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
                    for sym in self._symbols:
                        if (
                            sym in holdings_copy
                            and holdings_copy[sym].get("shares", 0) > 0
                        ):
                            continue

                        price = prices_copy.get(sym)
                        if not price:
                            continue

                        cfg = CONFIG[sym]
                        last_buy = get_last_buy_price(sym)
                        trigger = (
                            price <= cfg.get("buy_target_price", float("inf"))
                        ) or (
                            last_buy
                            and price <= last_buy * (1 - cfg["buy_drop_pct"] / 100)
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
                        if (sym, qty) in self.pending_copy:
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
        """CLI command loop (add/remove/pause/stop/etc.) — runs in its own thread."""
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
                    console.print("""Commands:
                    add SYMBOL {"buy_target_price": 8.0, ...}
                    remove SYMBOL
                    list | add | remove | pause | resume | stop | restart
                    """)
                    continue
                elif command == "list":
                    with self.lock:
                        active = ", ".join(sorted(self._symbols)) or "(none)"
                    console.print(f"[cyan]Currently monitoring: {active}[/cyan]")
                    continue
                elif command == "remove":
                    if len(parts) < 2:
                        console.print("[yellow]Usage: remove SYMBOL[/yellow]")
                        continue
                    sym = parts[1].strip().upper()
                    self.remove_symbol(sym)
                    continue
                elif command == "pause":
                    self.trading_paused = True
                    console.print("[yellow]Trading paused[/yellow]")
                    continue
                elif command == "resume":
                    self.trading_paused = False
                    console.print("[green]Trading resumed[/green]")
                    continue
                elif command == "stop":
                    self.stop()
                    break
                elif command == "add":
                    if len(parts) < 3:
                        console.print(
                            "[yellow]Usage: add SYMBOL {json config}[/yellow]"
                        )
                        continue
                    try:
                        _, rest = cmd_line.split(" ", 1)
                        sym_part, json_part = rest.split(" ", 1)
                        sym = sym_part.upper()
                        cfg = json.loads(json_part)
                        self.add_new_symbol(sym, cfg)
                    except Exception as e:
                        console.print(f"[red]Add error: {e}[/red]")
                    continue
                elif command == "restart":
                    self.restart()
                    continue
                else:
                    console.print(
                        "[dim yellow]Unknown command — type 'help'[/dim yellow]"
                    )

            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                console.print(f"[dim red]CLI error: {e}[/dim red]")

    # =============================================================
    # DYNAMIC SYMBOL MANAGEMENT
    # =============================================================
    def add_new_symbol(self, symbol: str, cfg: dict):
        """Dynamically add a symbol (updates CONFIG + stream subscription)."""
        if symbol in CONFIG:
            console.print(f"[yellow]{symbol} already exists[/yellow]")
            return

        CONFIG[symbol] = cfg
        with self.lock:
            self._symbols = list(CONFIG.keys())
            self.current_prices[symbol] = None
            self.auto_buy_allowed[symbol] = True
            self.holdings.pop(symbol, None)

        try:
            self.streamer.send(
                self.streamer.level_one_equities(symbol, "0,1,2,3,4,5,6,7,8")
            )
            console.print(f"[green]✅ Added {symbol} and subscribed[/green]")
        except Exception as e:
            console.print(f"[red]Stream subscribe failed: {e}[/red]")

    def remove_symbol(self, symbol: str):
        """Dynamically remove a symbol from monitoring (unsubscribes + cleans up state)"""
        symbol = symbol.upper()

        if symbol not in CONFIG:
            console.print(f"[yellow]Symbol {symbol} not found in CONFIG[/yellow]")
            return

        # Stop monitoring this symbol
        with self.lock:
            if symbol in self.current_prices:
                del self.current_prices[symbol]
            if symbol in self.auto_buy_allowed:
                del self.auto_buy_allowed[symbol]
            if symbol in self.holdings:
                console.print(
                    f"[yellow]Warning: {symbol} has an open position — removal won't close it[/yellow]"
                )
                # We intentionally do NOT force-close positions here — safety first
            if symbol in self.pending_buy_orders:  # rare, but cleanup
                self.pending_buy_orders = {
                    (s, q) for s, q in self.pending_buy_orders if s != symbol
                }

            # Remove from _symbols list
            if symbol in self._symbols:
                self._symbols.remove(symbol)

        # Remove from global CONFIG (careful — this affects future runs too)
        del CONFIG[symbol]

        # Note: schwabdev streamer does NOT have an explicit unsubscribe method in most wrappers.
        # In practice many streamers just ignore data for keys they don't care about anymore.
        # If heavy traffic becomes an issue, you would need to restart the whole stream subscription.

        console.print(f"[green]→ Removed {symbol} from monitoring[/green]")
        log_transaction(
            action="SYMBOL_REMOVED",
            symbol=symbol,
            qty=0,
            price=0,
            note="Manually removed via CLI",
            order_id=None,
            order_status=None,
        )

    # =============================================================
    # SHUTDOWN & RESTART
    # =============================================================
    def stop(self):
        """Stop the bot and streamer."""
        self.running = False
        self.streamer.stop()
        console.print("[red]Bot stopped.[/red]")

    def graceful_shutdown(self):
        """Helper to cleanly stop streaming and threads without killing the process"""
        self.running = False
        try:
            self.streamer.stop()
            console.print("[yellow]Streamer stopped[/yellow]")
        except Exception as e:
            console.print(f"[dim red]Error stopping streamer: {e}[/dim red]")
        # Give threads a moment to notice running=False
        time.sleep(1.5)

    def restart(self):
        """Restart streaming and monitoring without exiting the process"""
        console.print("[bold yellow]Restarting bot...[/bold yellow]")

        self.graceful_shutdown()

        # Reset state
        self.running = True
        self.trading_paused = False
        self.first_api_pull = True
        self.last_holdings_sync = time.time()
        self.invalidate_open_orders_cache()
        self._account_snapshot_cache_time = None
        # ... you can reset other caches if needed

        # Re-fetch account hash in case something weird happened
        try:
            self.account_hash = self._get_account_hash()
        except Exception as e:
            console.print(f"[red]Failed to refresh account hash: {e}[/red]")
            return

        # Re-start the stream
        try:
            self.start_stream()  # ← this is your existing method that calls streamer.start() + sends subscriptions
            console.print("[green]Streamer restarted and re-subscribed[/green]")
        except Exception as e:
            console.print(f"[red]Failed to restart stream: {e}[/red]")
            return

        # Re-start the logic thread (it will see running=True again)
        logic_thread = threading.Thread(target=self.monitor_logic, daemon=True)
        logic_thread.start()

        if self.mode == "full":  # assuming you store self.mode = args.mode in __init__
            display_thread = threading.Thread(target=self.monitor_display, daemon=True)
            display_thread.start()
        else:
            cli_thread = threading.Thread(target=self.cli_loop, daemon=True)
            cli_thread.start()

        console.print("[bold green]Bot restarted successfully[/bold green]")


bot = TradingBot()  # your class instance

# ── Dash app ────────────────────────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],  # SLATE, CYBORG or FLATLY, etc
    assets_folder="assets",
)

app.layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(html.H2("Schwab Trading Bot Dashboard"), width=12),
            ],
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(
                dbc.Button(
                    "Refresh Now",
                    id="refresh-button",
                    color="primary",
                    className="mb-3",
                ),
                width={"size": 3, "offset": 0},
            ),
            className="mb-3",
        ),
        # Positions - full width (unchanged)
        html.H4("Positions", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="positions-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Price", "id": "Price"},
                {"name": "Shares", "id": "Shares"},
                {"name": "Avg Buy", "id": "Avg Buy"},
                {"name": "P/L %", "id": "P/L %"},
                {"name": "Status", "id": "Status"},
            ],
            style_table={
                "overflowX": "auto",
                "maxWidth": "100%",
                "width": "100%",
            },
            style_cell={
                "textAlign": "left",
                "minWidth": "80px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_data={"color": "white", "backgroundColor": "#212529"},
            style_header={"backgroundColor": "#2c3e50", "color": "white"},
        ),
        # Open Orders - full width (unchanged)
        html.H4("Open Orders", className="mt-5 mb-2"),
        dash_table.DataTable(
            id="orders-table",
            columns=[
                {"name": "ID", "id": "ID"},
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Qty", "id": "Qty"},
                {"name": "Price", "id": "Price"},
                {"name": "Side", "id": "Side"},
                {"name": "Type", "id": "Type"},
                {"name": "Duration", "id": "Duration"},
            ],
            style_table={
                "overflowX": "auto",
                "maxWidth": "100%",
                "width": "100%",
            },
            style_cell={
                "textAlign": "left",
                "minWidth": "80px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_data={"color": "white", "backgroundColor": "#212529"},
            style_header={"backgroundColor": "#2c3e50", "color": "white"},
        ),
        # ── Account Summary - now half width ────────────────────────────────
        dbc.Row(
            dbc.Col(
                [
                    html.H4("Account Summary", className="mt-5 mb-2"),
                    dash_table.DataTable(
                        id="account-summary-table",
                        columns=[
                            {"name": "Metric", "id": "Metric"},
                            {"name": "Value", "id": "Value"},
                        ],
                        style_table={
                            "overflowX": "auto",
                            "maxWidth": "100%",
                            "width": "100%",  # ← fills the column
                        },
                        style_cell={"textAlign": "left"},
                        style_header={
                            "backgroundColor": "#2c3e50",
                            "color": "white",
                            "fontWeight": "bold",
                        },
                        style_data={
                            "color": "white",
                            "backgroundColor": "#212529",
                        },
                    ),
                ],
                width=6,  # ← this is the key change: half width
                lg=6,
                md=12,  # full width on smaller screens
                xs=12,
            ),
            className="mb-4",  # adds some bottom margin
        ),
        # Footer
        html.Div(id="status-footer", className="mt-5 text-center"),
        dcc.Interval(id="interval-component", interval=8 * 1000, n_intervals=0),
    ],
    fluid=True,
    className="p-4",
)


# ── FIXED CALLBACK ────────────────────────────────────────────────────────────
@app.callback(
    [
        Output("positions-table", "data"),
        Output("orders-table", "data"),
        Output("account-summary-table", "data"),
        Output("status-footer", "children"),
    ],
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-button", "n_clicks"),
    ],
    prevent_initial_call=True,  # optional: skip first empty call
)
def update_dashboard(n_interval, n_clicks):
    try:
        # Positions
        positions_data = []
        with bot.lock:
            for sym in bot._symbols:
                price = bot.current_prices.get(sym)
                h = bot.holdings.get(sym, {})
                shares = h.get("shares", 0)
                buy_p = h.get("buy_price")
                pl = (
                    round((price - buy_p) / buy_p * 100, 1)
                    if price and buy_p and buy_p > 0
                    else 0.0
                )
                positions_data.append(
                    {
                        "Symbol": sym,
                        "Price": f"${price:,.2f}" if price else "—",
                        "Shares": shares,
                        "Avg Buy": f"${buy_p:,.2f}" if buy_p else "—",
                        "P/L %": f"{pl:+.1f}%",
                        "Status": "HOLDING" if shares > 0 else "WATCHING",
                    }
                )

        # Open Orders
        orders_list = bot.get_open_orders()
        orders_data = []
        for o in orders_list:
            orders_data.append(
                {
                    "ID": str(o.get("orderId", "N/A")),
                    "Symbol": o.get("symbol", "—"),
                    "Qty": o.get("quantity", 0),
                    "Price": (
                        f"${float(o.get('price') or 0):,.2f}" if o.get("price") else "—"
                    ),
                    "Side": o.get("instruction", "—"),
                    "Type": o.get("type", "—"),
                    "Duration": o.get("duration", "—"),
                }
            )

        # Account Summary
        snapshot = bot.get_account_snapshot()

        account_data = [
            {"Metric": "Equity(Net Liq)", "Value": f"${snapshot['equity']:,.2f}"},
            {
                "Metric": "Cash & Sweep Vehicle",
                "Value": f"${snapshot['cashBalance']:,.2f}",
            },
            {"Metric": "Buying Power", "Value": f"${snapshot['buyingPower']:,.2f}"},
            {
                "Metric": "Day Trading Buying Power",
                "Value": f"${snapshot['dayTradingBP']:,.2f}",
            },
            {
                "Metric": "Non-Marginable Buying Power",
                "Value": f"${snapshot['nonMarginableBP']:,.2f}",
            },
        ]

        daily_pnl = (
            (snapshot["equity"] - bot.daily_start_equity) / bot.daily_start_equity * 100
            if bot.daily_start_equity > 0
            else 0
        )
        risk_used = len(bot.holdings) / RISK_CONFIG["max_positions"] * 100
        status_text = (
            f"Equity(Net Liq): ${snapshot['equity']:,.0f} | Daily P/L: {daily_pnl:+.1f}% | "
            f"Risk Used: {risk_used:.0f}% | {'PAUSED' if bot.trading_paused else 'ACTIVE'}"
        )

        return positions_data, orders_data, account_data, status_text

    except Exception as e:
        console.print(f"[red]Dashboard callback error: {e}[/red]")
        return [], [], [], "Dashboard error — check console"


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schwab Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["full", "cli"],
        default="cli",
        help="full = rich terminal dashboard + web dashboard | cli = web dashboard only + terminal commands",
    )
    args = parser.parse_args()

    bot = TradingBot(mode=args.mode)
    bot.start_stream()

    # Always run the logic thread
    logic_thread = threading.Thread(target=bot.monitor_logic, daemon=True)
    logic_thread.start()

    if args.mode == "full":
        display_thread = threading.Thread(target=bot.monitor_display, daemon=True)
        display_thread.start()
        console.print(
            "[bold green]FULL MODE - Terminal + Web dashboard active[/bold green]"
        )
    else:
        cli_thread = threading.Thread(target=bot.cli_loop, daemon=True)
        cli_thread.start()
        console.print(
            "[bold green]CLI MODE - Web dashboard only + terminal commands active[/bold green]"
        )

    # print("Dashboard starting → open http://127.0.0.1:8050/")
    # Fix: remove duplicate app = dash.Dash line (was in your original)
    app.run(debug=True, use_reloader=False)
