# bot.py
import json
import time
import threading
import datetime
import schwabdev
from dotenv import load_dotenv
import os
import hashlib
from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns

from config import SYMBOLS, CONFIG, RISK_CONFIG
from db import init_db, log_transaction, save_state, get_last_buy_price, load_state
import dash
from dash import dcc, html, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

import threading
import time
import pandas as pd

load_dotenv()
console = Console()
CACHE_TTL_SECONDS = 60


class TradingBot:
    def __init__(self):
        init_db()
        self.client = schwabdev.Client(
            os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
        )
        self.streamer = schwabdev.Stream(self.client)

        self.current_prices = {sym: None for sym in SYMBOLS}
        self.holdings = {}
        self.state = load_state()
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

        # Daily risk tracking
        self.daily_start_equity = self.get_account_snapshot()["equity"]
        self.today = datetime.date.today()

        console.print(
            f"[bold cyan]Account Equity at start: ${self.daily_start_equity:,.2f}[/bold cyan]"
        )

    def _get_account_hash(self):
        accounts = self.client.linked_accounts().json()
        if not accounts:
            raise RuntimeError("No linked accounts found")
        return accounts[0]["hashValue"]

    # ── ACCOUNT METRICS (for risk checks) ─────────────────────────────────────

    def get_account_snapshot(self):

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
                "settledFunds": float(bal.get("settledFunds") or 0.0),
                "unsettledFunds": float(bal.get("unsettledFunds") or 0.0),
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
                "settledFunds": 0.0,
                "unsettledFunds": 0.0,
            }

    def iter_orders_filtered(self, order, cancelable_only=False):
        """
        Yield flattened order records from a Schwab/TD Ameritrade order tree.

        Parameters
        ----------
        order : dict
            Single order dictionary (can contain childOrderStrategies)
        cancelable_only : bool, default False
            If True, yields only orders with cancelable=True.
            If False, yields all orders.

        Yields
        ------
        dict
            Flattened order info with:
                - orderId
                - orderType
                - duration
                - price
                - legs: list of dicts with instruction, symbol, quantity
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
            yield from self.iter_orders_filtered(child, cancelable_only=cancelable_only)

    def get_open_orders(self):
        """
        Fetch open orders using client.account_orders() and handle both:
        - Simple SINGLE orders
        - orders with childOrderStrategies (brackets)
        Returns flattened list of dicts suitable for table display.
        """

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
                for o in self.iter_orders_filtered(root, cancelable_only=True)
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

            return displayed

        except Exception as e:
            console.print(f"[red]Failed to fetch open orders: {str(e)}[/red]")
            return []

    # ── RISK CALCULATIONS ─────────────────────────────────────────────────────
    def calculate_shares(self, symbol, buy_price):
        cfg = CONFIG.get(symbol, {})
        fixed = cfg.get("fixed_shares", 0)

        if fixed > 0:
            # Manual / fixed mode takes priority
            shares = fixed
            console.print(
                f"[cyan]Using fixed quantity for {symbol}: {shares} shares[/cyan]"
            )
        else:
            # Fall back to risk-based sizing
            if buy_price <= 0:
                shares = RISK_CONFIG["default_shares"]
            else:
                equity = self.get_account_snapshot()["equity"]
                risk_dollars = equity * (RISK_CONFIG["risk_per_trade_pct"] / 100)
                stop_pct = cfg.get("stop_loss_pct", 5.0) / 100
                stop_distance = buy_price * stop_pct

                if stop_distance <= 0:
                    shares = RISK_CONFIG["default_shares"]
                else:
                    shares = int(risk_dollars / stop_distance)
                    shares = max(1, min(shares, 1000))  # safety bounds

        return shares

    def risk_checks_pass(self, symbol):
        """All pre-trade risk validations"""
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

        # Buying power check
        estimated_cost = (
            self.current_prices.get(symbol, 0) * RISK_CONFIG["default_shares"]
        )
        if bp < estimated_cost * 1.1:  # 10% buffer
            console.print(
                f"[yellow]Insufficient buying power (${bp:,.0f}) — skipping[/yellow]"
            )
            return False

        return True

    # ── STREAM HANDLERS (unchanged from last version) ─────────────────────────
    def unified_receiver(self, message):
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
        content_list = item.get("content", [])
        if not content_list:
            return

        for content in content_list:
            symbol = content.get("key")
            if symbol not in self.current_prices:
                continue

            last_str = content.get("3")
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
            if not symbol or symbol not in SYMBOLS:
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
                            "SELL (detected via stream)",
                            symbol,
                            qty,
                            price,
                            note="OCO fill via ACCT_ACTIVITY",
                        )

                elif instruction in ("BUY", "BUY_TO_COVER"):
                    self.holdings[symbol] = {
                        "shares": qty,
                        "buy_price": price,
                        "limit_price": None,
                        "stop_price": None,
                    }
                    log_transaction(
                        "BUY (detected via stream)",
                        symbol,
                        qty,
                        price,
                        note="Initial buy fill via ACCT_ACTIVITY",
                    )
                    self.place_bracket_orders(symbol, price)
                    save_state(symbol, price)

    def start_stream(self):
        """
        Subscribes to live quotes for your sumbols, listens to both price updates and order execution events
        """

        # Starts the WebSocket connection in the background
        self.streamer.start(receiver=self.unified_receiver)

        # Prepares and sends the subscription request for stock quotes
        quote_request = {
            "service": "LEVELONE_EQUITIES",
            "command": "SUBS",  # SUBS = subscribe
            "requestid": "1001",  # any unique string/int per request
            "SchwabClientCustomerId": "",  # usually left empty or from user principals
            "SchwabClientCorrelId": "corr123",  # can be any string
            "parameters": {
                "keys": ",".join(SYMBOLS),  # ← symbols here
                "fields": "0,1,2,3,4,5,6,7,8,9",  # symbol, bid, ask, last, etc.
            },
        }

        self.streamer.send(quote_request)
        console.print(
            f"[green]→ Subscribed to LEVELONE_EQUITIES for {', '.join(SYMBOLS)}[/green]"
        )

        # ── Account Activity Subscription ─────────────────────────────────────────
        # First try the convenience method if it exists
        try:
            acct_req = self.streamer.account_activity(fields="0,1,2,3", command="SUBS")
            self.streamer.send(acct_req)
            console.print(
                "[green]→ Subscribed to account activity (via convenience)[/green]"
            )
        except (AttributeError, TypeError):
            console.print(
                "[yellow]Falling back to manual ACCT_ACTIVITY subscription[/yellow]"
            )

            # Manual version - you may need to fetch subscription keys from user principals
            try:
                principals = self.client.user_principals().json()
                # Typically one key for your linked account
                sub_key = principals.get("streamerSubscriptionKeys", [{}])[0].get(
                    "key", ""
                )
                if not sub_key:
                    sub_key = (
                        self.account_hash
                    )  # fallback to account hash sometimes works
            except Exception:
                sub_key = self.account_hash  # safest fallback

            acct_manual = {
                "service": "ACCT_ACTIVITY",
                "command": "SUBS",
                "requestid": "1002",
                "SchwabClientCustomerId": "",
                "SchwabClientCorrelId": "corr456",
                "parameters": {
                    "keys": sub_key,
                    "fields": "0,1,2,3",  # subscription key, account, message type, data
                },
            }

            self.streamer.send(acct_manual)
            console.print("[green]→ Manual ACCT_ACTIVITY subscription sent[/green]")

        console.print(
            "[bold green]Streaming active — quotes + account activity[/bold green]"
        )

    # ── ORDER PLACEMENT (now with dynamic shares) ─────────────────────────────
    def place_buy_order(self, symbol):
        if not self.risk_checks_pass(symbol):
            return False

        buy_price = self.current_prices.get(symbol, 0)
        qty = self.calculate_shares(symbol, buy_price)

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
            resp = self.client.place_order(self.account_hash, order)
            log_transaction(
                "BUY_SUBMITTED",
                symbol,
                qty,
                buy_price,
                note=f"Risk-sized: {qty} shares",
            )
            console.print(
                f"[green]BUY SUBMITTED → {qty} shares of {symbol} (risk-controlled)[/green]"
            )
            return True
        except Exception as e:
            console.print(f"[red]Buy failed: {e}[/red]")
            return False

    def place_bracket_orders(self, symbol, buy_price):
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
            self.client.place_order(self.account_hash, oco)
            log_transaction(
                "OCO_PLACED",
                symbol,
                qty,
                buy_price,
                "OCO",
                f"Limit ${limit_price:.2f} | Stop ${stop_price:.2f}",
            )
            with self.lock:
                self.holdings[symbol].update(
                    {"limit_price": limit_price, "stop_price": stop_price}
                )
        except Exception as e:
            console.print(f"[red]OCO failed: {e}[/red]")

    def update_holdings_from_api(self):
        # (same as previous version)
        try:
            pos = self.client.account_details(
                self.account_hash, fields="positions"
            ).json()
            positions = pos.get("securitiesAccount", {}).get("positions", [])
            new_h = {}
            for p in positions:
                sym = p["instrument"]["symbol"]
                if sym in SYMBOLS and float(p.get("longQuantity", 0)) > 0:
                    new_h[sym] = {
                        "shares": float(p["longQuantity"]),
                        "buy_price": p.get("averagePrice", 0),
                    }
            with self.lock:
                self.holdings = new_h
        except:
            pass

    def stop(self):
        self.running = False
        self.streamer.stop()
        console.print("[red]Bot stopped.[/red]")

    def make_dashboard(self):
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
            for sym in SYMBOLS:
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

    def monitor_loop(self):
        last_hash = None

        with Live(console=console, refresh_per_second=4, screen=True) as live:
            while self.running:
                time.sleep(6)

                if datetime.date.today() != self.today:
                    self.daily_start_equity = self.get_account_snapshot()["equity"]
                    self.today = datetime.date.today()
                    self.trading_paused = False

                self.update_holdings_from_api()

                with self.lock:
                    view = {}
                    for sym in SYMBOLS:
                        p = self.current_prices.get(sym)
                        h = self.holdings.get(sym, {})
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
                    for sym in SYMBOLS:
                        if (
                            sym in self.holdings
                            and self.holdings[sym].get("shares", 0) > 0
                        ):
                            continue
                        price = self.current_prices.get(sym)
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
                        if (
                            trigger
                            and not self.trading_paused
                            and self.risk_checks_pass(sym)
                        ):
                            console.print(
                                f"[bold red]BUY TRIGGER {sym} @ ${price:.2f}[/bold red]"
                            )
                            self.place_buy_order(sym)


bot = TradingBot()  # your class instance

# ── Dash app ────────────────────────────────────────────────────────────────
app = dash.Dash(
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
        # Positions - full width
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
        # Open Orders - full width
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
        # Account Summary - full width
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
                "width": "100%",
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
        # Footer
        html.Div(id="status-footer", className="mt-5 text-center"),
        dcc.Interval(id="interval-component", interval=8 * 1000, n_intervals=0),
    ],
    fluid=True,
    className="p-4",
)  # or fluid=False if you prefer fixed width


# ── FIXED CALLBACK (this is what was breaking your account-summary table) ─────
@app.callback(
    [
        Output("positions-table", "data"),
        Output("orders-table", "data"),
        Output("account-summary-table", "data"),
        Output("status-footer", "children"),
    ],
    Input("interval-component", "n_intervals"),
)
def update_dashboard(n):
    try:
        snapshot = bot.get_account_snapshot()

        # Positions
        positions_data = []
        with bot.lock:
            for sym in SYMBOLS:
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
    # Start your streaming + background logic in daemon threads
    bot.start_stream()

    monitor_thread = threading.Thread(target=bot.monitor_loop, daemon=True)
    monitor_thread.start()

    # Optional: keep some console logging
    print("Dashboard starting → open http://127.0.0.1:8050/")
    print("Streaming + bot logic running in background...")

    # Start Dash server (blocks main thread)
    app.run(
        debug=True, use_reloader=False
    )  # use_reloader=False → avoids double thread start
