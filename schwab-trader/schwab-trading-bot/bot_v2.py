# bot.py
import json
import time

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import threading
from datetime import datetime, date
import schwabdev
from dotenv import load_dotenv
import os
from rich.console import Console
from rich.table import Table

from config import SYMBOLS, CONFIG, RISK_CONFIG
from db import init_db, log_transaction, save_state, get_last_buy_price, load_state

load_dotenv()
console = Console()

CACHE_TTL_SECONDS = 45  # refresh every ~45 seconds or 60, 90


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
        self.lock = threading.Lock()
        self.running = True
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        self._equity_cache = None
        self._equity_cache_time = 0
        self._buying_power_cache = None
        self._buying_power_cache_time = 0

        # Daily risk tracking
        self.daily_start_equity, _ = self.get_account_snapshot()
        self.today = date.today()

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
        if (
            self._equity_cache is not None
            and self._buying_power_cache is not None
            and (now - self._equity_cache_time) < CACHE_TTL_SECONDS
        ):
            return self._equity_cache, self._buying_power_cache

        try:
            acc = self.client.account_details(self.account_hash).json()
            balances = acc.get("securitiesAccount", {}).get("currentBalances", {})

            cb = float(balances.get("cashBalance", 0) or 0.0)
            equity = float(
                balances.get("liquidationValue") or balances.get("equity") or 0.0
            )
            bp = float(balances.get("buyingPower", 0) or 0.0)
            bp_non_mt = float(balances.get("buyingPowerNonMarginableTrade", 0) or 0.0)
            bp_dt = float(balances.get("dayTradingBuyingPower", 0) or 0.0)

            self._equity_cache = equity
            self._equity_cache_time = now
            self._buying_power_cache = bp
            self._buying_power_cache_time = now

            return equity, bp
        except Exception as e:
            console.print(f"[dim red]Account snapshot failed: {e}[/dim red]")
            return (
                self._equity_cache if self._equity_cache is not None else 10000.0,
                (
                    self._buying_power_cache
                    if self._buying_power_cache is not None
                    else 0.0
                ),
            )

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
                equity, _ = self.get_account_snapshot()
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
        equity, bp = self.get_account_snapshot()
        if self.trading_paused:
            return False

        # Daily loss limit
        current_equity, _ = self.get_account_snapshot()
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
        bp = self.get_buying_power()
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

    # ── MONITOR LOOP + ENHANCED DASHBOARD ─────────────────────────────────────
    def get_dashboard_content(self):
        """
        Build dashboard components.
        Returns: (table object, footer_markup_str, equity, daily_pnl_pct)
        """
        equity, _ = self.get_account_snapshot()
        daily_pnl_pct = (
            (equity - self.daily_start_equity) / self.daily_start_equity * 100
            if self.daily_start_equity > 0
            else 0.0
        )

        table = Table(expand=True, show_header=True, header_style="bold magenta")
        table.add_column("Symbol", style="cyan", justify="left")
        table.add_column("Price", justify="right")
        table.add_column("Position", justify="right")
        table.add_column("Avg Buy", justify="right")
        table.add_column("P/L %", justify="right")
        table.add_column("Status", justify="left")

        with self.lock:
            for sym in SYMBOLS:
                price = self.current_prices.get(sym)
                h = self.holdings.get(sym, {})
                shares = h.get("shares", 0)
                buy_p = h.get("buy_price", None)
                pl_pct = (
                    ((price - buy_p) / buy_p * 100)
                    if price and buy_p and buy_p > 0
                    else 0.0
                )

                price_str = f"${price:,.2f}" if price is not None else "—"
                buy_str = f"${buy_p:,.2f}" if buy_p is not None else "—"
                pl_str = f"{pl_pct:+.1f}%" if abs(pl_pct) > 0.01 else "+0.0%"

                status_style = "green" if shares > 0 else "grey70"
                table.add_row(
                    sym,
                    price_str,
                    f"{shares:.1f}",
                    buy_str,
                    pl_str,
                    f"[{status_style}]{'HOLDING' if shares > 0 else 'WATCHING'}[/{status_style}]",
                )

        risk_used_pct = (len(self.holdings) / RISK_CONFIG.get("max_positions", 1)) * 100

        footer = (
            f"Equity: [bold]${equity:,.0f}[/bold]   |   "
            f"Daily P/L: [{'green' if daily_pnl_pct >= 0 else 'red'}]{daily_pnl_pct:+.1f}%[/{'green' if daily_pnl_pct >= 0 else 'red'}]   |   "
            f"Risk used: {risk_used_pct:.0f}%   |   "
            f"{'[bold red]PAUSED[/bold red]' if self.trading_paused else '[bold green]ACTIVE[/bold green]'}"
        )

        return table, footer, equity, daily_pnl_pct

    def monitor_loop(self):
        last_state_key = None

        with Live(
            Panel(
                "Initializing dashboard...",
                title="Schwab Trading Bot",
                border_style="blue",
            ),
            console=console,
            refresh_per_second=0.4,
            screen=True,
        ) as live:
            while self.running:
                time.sleep(5)

                # Daily reset
                if date.today() != self.today:
                    self.daily_start_equity, _ = self.get_account_snapshot()
                    self.today = date.today()
                    self.trading_paused = False

                self.update_holdings_from_api()

                # ─────────────── BUY TRIGGER LOGIC ───────────────
                with self.lock:
                    for sym in SYMBOLS:
                        if (
                            sym in self.holdings
                            and self.holdings[sym].get("shares", 0) > 0
                        ):
                            continue

                        current_price = self.current_prices.get(sym)
                        if current_price is None or current_price <= 0:
                            continue

                        cfg = CONFIG.get(sym, {})
                        target = cfg.get("buy_target_price", float("inf"))
                        drop_pct = cfg.get("buy_drop_pct", 5.0)
                        last_buy = get_last_buy_price(sym)

                        trigger = False
                        reason = ""

                        if current_price <= target:
                            trigger = True
                            reason = f"hit absolute target ${target:.2f}"

                        if last_buy and current_price <= last_buy * (
                            1 - drop_pct / 100
                        ):
                            trigger = True
                            reason += " & " if reason else ""
                            reason += (
                                f"dropped ≥{drop_pct}% from last buy (${last_buy:.2f})"
                            )

                        if trigger and self.risk_checks_pass(sym):
                            console.print(
                                f"[bold red]BUY TRIGGER {sym}: {reason} @ ${current_price:.2f}[/bold red]"
                            )
                            self.place_buy_order(sym)
                            self.holdings[sym] = {
                                "shares": self.calculate_shares(sym, current_price),
                                "buy_price": current_price,
                                "limit_price": None,
                                "stop_price": None,
                            }

                # ─────────────── Dashboard update ───────────────
                table, footer, equity, daily_pnl = self.get_dashboard_content()

                state_key = (
                    tuple(
                        (
                            sym,
                            self.current_prices.get(sym),
                            self.holdings.get(sym, {}).get("shares", 0),
                        )
                        for sym in SYMBOLS
                    ),
                    round(equity, 2),
                    round(daily_pnl, 2),
                    self.trading_paused,
                    len(self.holdings),
                )

                if state_key != last_state_key:
                    title = f"Schwab Trading Bot — {datetime.now():%Y-%m-%d %H:%M:%S}"
                    if self.trading_paused:
                        title += "   [bold red](PAUSED)[/bold red]"

                    live.update(
                        Panel(
                            table,  # ← Table object directly → renders as table
                            subtitle=footer,  # ← markup string as subtitle
                            title=title,
                            border_style="red" if self.trading_paused else "blue",
                            padding=(1, 2),
                        )
                    )
                    last_state_key = state_key

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


# ────────────────────────────────────────────────
if __name__ == "__main__":

    bot = TradingBot()
    bot.start_stream()

    threading.Thread(target=bot.monitor_loop, daemon=True).start()

    console.print(
        "\n[bold green]Bot running with FULL RISK MANAGEMENT. Press Ctrl+C to stop.[/bold green]\n"
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()


"""
handle_account_activity() and monitor_loop() — work closely together to implement the full order lifecycle (submit → fill detection → place protective orders → detect close → repeat).

monitor_loop() slow, periodic decision maker (every 5-10 seconds, looks at prices, decides whether to act)
handle_account_activity() fast, event-driven reactor (runs as soon as Schwab sends a message, usually within <1 second of fill)

monitor_loop() responsibility is to watch prices continuous and decide when to buy once trigger conditions are met.

handle_account_activity() responsibility is to listen real-time execution reports (ACCT_ACTIVITY message, async in background thread) from Schwab and react after an order is filled (OCO bracket after buy filled)

"""
