# bot.py
import json
import time
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

class TradingBot:
    def __init__(self):
        init_db()
        self.client = schwabdev.Client(
            os.getenv('app_key'), os.getenv('app_secret'), os.getenv('callback_url')
        )
        self.streamer = schwabdev.Stream(self.client)

        self.current_prices = {sym: None for sym in SYMBOLS}
        self.holdings = {}
        self.state = load_state()
        self.lock = threading.Lock()
        self.running = True
        self.trading_paused = False
        self.account_hash = self._get_account_hash()

        # Daily risk tracking
        self.daily_start_equity = self.get_account_equity()
        self.today = date.today()

        console.print(f"[bold cyan]Account Equity at start: ${self.daily_start_equity:,.2f}[/bold cyan]")

    def _get_account_hash(self):
        accounts = self.client.linked_accounts().json()
        if not accounts:
            raise RuntimeError("No linked accounts found")
        return accounts[0]['hashValue']

    # ── ACCOUNT METRICS (for risk checks) ─────────────────────────────────────
    def get_account_equity(self):
        try:
            acc = self.client.account_details(self.account_hash).json()
            balances = acc.get('securitiesAccount', {}).get('currentBalances', {})
            equity = balances.get('liquidationValue') or balances.get('equity') or 0.0
            cash_balance = balances.get('cashBalance') # 
            return float(equity)
        except Exception as e:
            console.print(f"[dim red]Equity fetch failed: {e}[/dim red]")
            return 10000.0  # safe fallback

    def get_buying_power(self):
        try:
            acc = self.client.account_details(self.account_hash).json()
            return float(acc.get('securitiesAccount', {}).get('currentBalances', {}).get('buyingPower', 0))
        except:
            return 0.0

    # ── RISK CALCULATIONS ─────────────────────────────────────────────────────
    def calculate_shares(self, symbol, buy_price):
        if buy_price <= 0:
            return RISK_CONFIG['default_shares']

        equity = self.get_account_equity()
        risk_dollars = equity * (RISK_CONFIG['risk_per_trade_pct'] / 100)
        stop_pct = CONFIG[symbol]['stop_loss_pct'] / 100
        stop_distance = buy_price * stop_pct

        if stop_distance <= 0:
            return RISK_CONFIG['default_shares']

        shares = int(risk_dollars / stop_distance)
        return max(1, min(shares, 1000))  # safety cap

    def risk_checks_pass(self, symbol):
        """All pre-trade risk validations"""
        if self.trading_paused:
            return False

        # Daily loss limit
        current_equity = self.get_account_equity()
        daily_pnl_pct = (current_equity - self.daily_start_equity) / self.daily_start_equity * 100
        if daily_pnl_pct <= -RISK_CONFIG['max_daily_loss_pct']:
            console.print(f"[bold red]🚨 DAILY LOSS LIMIT HIT ({daily_pnl_pct:.1f}%) — TRADING PAUSED[/bold red]")
            self.trading_paused = True
            return False

        # Minimum equity guard
        if current_equity < RISK_CONFIG['min_account_equity']:
            console.print(f"[bold red]🚨 ACCOUNT BELOW MIN EQUITY (${current_equity:,.0f}) — TRADING PAUSED[/bold red]")
            self.trading_paused = True
            return False

        # Max positions
        if len(self.holdings) >= RISK_CONFIG['max_positions']:
            console.print("[yellow]Max positions reached — skipping new buys[/yellow]")
            return False

        # Buying power check
        bp = self.get_buying_power()
        estimated_cost = self.current_prices.get(symbol, 0) * RISK_CONFIG['default_shares']
        if bp < estimated_cost * 1.1:  # 10% buffer
            console.print(f"[yellow]Insufficient buying power (${bp:,.0f}) — skipping[/yellow]")
            return False

        return True

    # ── STREAM HANDLERS (unchanged from last version) ─────────────────────────
    def unified_receiver(self, message):
        if not isinstance(message, dict):
            return
        for item in message.get('data', []):
            service = item.get('service')
            if service == 'LEVELONE_EQUITIES':
                self.handle_price_message(item)
            elif service in ('ACCT_ACTIVITY', 'USER_ACTIVITY'):
                self.handle_account_activity(item)

    def handle_price_message(self, item):
        for content in item.get('content', []):
            symbol = content.get('key')
            if symbol in self.current_prices:
                try:
                    price = float(content.get('3', 0))
                    if price > 0:
                        with self.lock:
                            self.current_prices[symbol] = price
                except:
                    pass

    def handle_account_activity(self, item):
        for content in item.get('content', []):
            if content.get('messageType', '').upper() not in ('EXECUTION', 'FILL', 'ORDER_FILL'):
                continue
            symbol = content.get('symbol') or content.get('instrument', {}).get('symbol')
            if not symbol or symbol not in SYMBOLS:
                continue

            qty = float(content.get('quantity') or content.get('filledQuantity', 0))
            price = float(content.get('price') or content.get('executionPrice', 0))
            instr = content.get('instruction', '').upper()

            with self.lock:
                if instr in ('SELL', 'SELL_SHORT') and symbol in self.holdings:
                    del self.holdings[symbol]
                    # Removes the symbol from the internal holdings dictionary, the bot now considers the position flat/closed
                    log_transaction("SELL (stream)", symbol, qty, price, note="OCO filled")
                    console.print(f"[yellow bold]Position CLOSED: {symbol} @ ${price:.2f}[/yellow bold]")

                elif instr in ('BUY', 'BUY_TO_COVER'):
                    self.holdings[symbol] = {
                        'shares': qty,
                        'buy_price': price,
                        'limit_price': None,
                        'stop_price': None
                        }
                    log_transaction("BUY (stream)", symbol, qty, price, note="Fill detected")
                    console.print(f"[green bold]BUY FILLED: {symbol} @ ${price:.2f}[/green bold]")
                    self.place_bracket_orders(symbol, price)
                    save_state(symbol, price)

    # def start_stream(self):
    #     self.streamer.start(receiver=self.unified_receiver)

    #     # Quotes
    #     self.streamer.send(
    #         self.streamer.level_one_equities(
    #             symbols=",".join(SYMBOLS),
    #             fields="0,1,2,3,4,5,6,7,8,9",
    #             command="SUBS"
    #         )
    #     )

    #     # Account activity
    #     try:
    #         self.streamer.send(
    #             self.streamer.account_activity(fields="0,1,2,3", command="SUBS")
    #         )
    #         console.print("[green]→ Subscribed to account activity[/green]")
    #     except AttributeError:
    #         console.print("[yellow]Warning: falling back to manual ACCT_ACTIVITY subscription[/yellow]")
    #         # Fetch keys first (add this)
    #         principals = self.client.user_principals().json()
    #         sub_keys = principals.get('streamerSubscriptionKeys', {}).get('keys', [{}])[0].get('key', '')
    #         self.streamer.send({
    #             "service": "ACCT_ACTIVITY",
    #             "command": "SUBS",
    #             "parameters": {"keys": sub_keys, "fields": "0,1,2,3"}
    #         })

    #     console.print("[bold green]Streaming active — quotes + account activity[/bold green]")
    
    def start_stream(self):
        """
        Subscribes to live quotes for your sumbols, listens to both price updates and order execution events
        """
        
        # Starts the WebSocket connection in the background
        self.streamer.start(receiver=self.unified_receiver)

        # Prepares and sends the subscription request for stock quotes
        quote_request = {
            "service": "LEVELONE_EQUITIES",
            "command": "SUBS",                  # SUBS = subscribe
            "requestid": "1001",                # any unique string/int per request
            "SchwabClientCustomerId": "",       # usually left empty or from user principals
            "SchwabClientCorrelId": "corr123",  # can be any string
            "parameters": {
                "keys": ",".join(SYMBOLS),      # ← symbols here
                "fields": "0,1,2,3,4,5,6,7,8,9" # symbol, bid, ask, last, etc.
            }
        }

        self.streamer.send(quote_request)
        console.print(f"[green]→ Subscribed to LEVELONE_EQUITIES for {', '.join(SYMBOLS)}[/green]")

        # ── Account Activity Subscription ─────────────────────────────────────────
        # First try the convenience method if it exists
        try:
            acct_req = self.streamer.account_activity(fields="0,1,2,3", command="SUBS")
            self.streamer.send(acct_req)
            console.print("[green]→ Subscribed to account activity (via convenience)[/green]")
        except (AttributeError, TypeError):
            console.print("[yellow]Falling back to manual ACCT_ACTIVITY subscription[/yellow]")

            # Manual version - you may need to fetch subscription keys from user principals
            try:
                principals = self.client.user_principals().json()
                # Typically one key for your linked account
                sub_key = principals.get("streamerSubscriptionKeys", [{}])[0].get("key", "")
                if not sub_key:
                    sub_key = self.account_hash  # fallback to account hash sometimes works
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
                    "fields": "0,1,2,3"   # subscription key, account, message type, data
                }
            }

            self.streamer.send(acct_manual)
            console.print("[green]→ Manual ACCT_ACTIVITY subscription sent[/green]")

        console.print("[bold green]Streaming active — quotes + account activity[/bold green]")


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
            "orderLegCollection": [{
                "instruction": "BUY",
                "quantity": qty,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
            }]
        }

        try:
            resp = self.client.place_order(self.account_hash, order)
            log_transaction("BUY_SUBMITTED", symbol, qty, buy_price, note=f"Risk-sized: {qty} shares")
            console.print(f"[green]BUY SUBMITTED → {qty} shares of {symbol} (risk-controlled)[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Buy failed: {e}[/red]")
            return False

    def place_bracket_orders(self, symbol, buy_price):
        # (unchanged from previous version — GTC OCO)
        cfg = CONFIG[symbol]
        qty = self.holdings[symbol]['shares']
        limit_price = round(buy_price * (1 + cfg['limit_sell_pct']/100), 2)
        stop_price  = round(buy_price * (1 - cfg['stop_loss_pct']/100), 2)

        oco = {
            "orderType": "OCO",
            "session": "NORMAL",
            "duration": "GTC",
            "orderStrategyType": "OCO",
            "childOrderStrategies": [
                {   # LIMIT SELL
                    "orderType": "LIMIT",
                    "session": "NORMAL",
                    "duration": "GTC",
                    "price": str(limit_price),
                    "orderLegCollection": [{
                        "instruction": "SELL",
                        "quantity": qty,
                        "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                    }]
                },
                {   # STOP LOSS
                    "orderType": "STOP",
                    "session": "NORMAL",
                    "duration": "GTC",
                    "stopPrice": str(stop_price),
                    "orderLegCollection": [{
                        "instruction": "SELL",
                        "quantity": qty,
                        "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                    }]
                }
            ]
        }

        try:
            self.client.place_order(self.account_hash, oco)
            log_transaction("OCO_PLACED", symbol, qty, buy_price, "OCO",
                            f"Limit ${limit_price:.2f} | Stop ${stop_price:.2f}")
            with self.lock:
                self.holdings[symbol].update({'limit_price': limit_price, 'stop_price': stop_price})
        except Exception as e:
            console.print(f"[red]OCO failed: {e}[/red]")

    # ── MONITOR LOOP + ENHANCED DASHBOARD ─────────────────────────────────────
    # Approach I - new table every 10 second specified by time.sleep(10)
# ── MONITOR LOOP + ENHANCED DASHBOARD ─────────────────────────────────────
    def monitor_loop(self):
        while self.running:
            time.sleep(10)

            # Daily reset
            if date.today() != self.today:
                self.daily_start_equity = self.get_account_equity()
                self.today = date.today()
                self.trading_paused = False
                console.print("[cyan]New trading day — daily loss counter reset[/cyan]")

            self.update_holdings_from_api()

            with self.lock:
                equity = self.get_account_equity()
                daily_pnl = (equity - self.daily_start_equity) / self.daily_start_equity * 100

                table = Table(title=f"🚀 Schwab Bot + Risk Management ─ {datetime.now().strftime('%H:%M:%S')}")
                table.add_column("Symbol")
                table.add_column("Price")
                table.add_column("Position")
                table.add_column("Avg Buy")
                table.add_column("P/L %")
                table.add_column("Status")

                for sym in SYMBOLS:
                    price = self.current_prices.get(sym)
                    h = self.holdings.get(sym, {})
                    shares = h.get('shares', 0)
                    buy_p = h.get('buy_price')
                    pl = ((price - buy_p) / buy_p * 100) if price and buy_p else 0

                    if shares <= 0 and price and not self.trading_paused:
                        cfg = CONFIG[sym]
                        last_buy = get_last_buy_price(sym)
                        trigger = (price <= cfg.get('buy_target_price')) or \
                                  (last_buy and price <= last_buy * (1 - cfg['buy_drop_pct']/100))
                        if trigger:
                            console.print(f"[bold red]BUY TRIGGER: {sym} @ ${price:.2f}[/bold red]")
                            self.place_buy_order(sym)

                    status = "HOLDING" if shares > 0 else "WATCHING"
                    table.add_row(sym, f"${price:.2f}" if price else "—", str(shares),
                                  f"${buy_p:.2f}" if buy_p else "—", f"{pl:+.1f}%", status)

                # Risk footer
                risk_used = len(self.holdings) / RISK_CONFIG['max_positions'] * 100
                console.print(table)
                console.print(f"[bold]Account: ${equity:,.0f} | Daily P/L: {daily_pnl:+.1f}% | "
                              f"Risk Used: {risk_used:.0f}% | Status: {'PAUSED' if self.trading_paused else 'ACTIVE'}[/bold]")
    # # Approach II - Track a simple "state hash" or version number. This is lightweight, reliable and doesn't require deep comparison of all data.
    # def monitor_loop(self):
    #     last_state_hash = None          # or use a counter / timestamp

    #     while self.running:
    #         time.sleep(10)              # still check every ~10s

    #         # Daily reset (keep as-is)
    #         if date.today() != self.today:
    #             self.daily_start_equity = self.get_account_equity()
    #             self.today = date.today()
    #             self.trading_paused = False
    #             console.print("[cyan]New trading day — reset[/cyan]")

    #         self.update_holdings_from_api()


    #         # ── BUY TRIGGER LOGIC ───────────────────────────────────────────────
    #         with self.lock:
    #             for sym in SYMBOLS:
    #                 if sym in self.holdings and self.holdings[sym].get('shares', 0) > 0:
    #                     continue

    #                 current_price = self.current_prices.get(sym)
    #                 if current_price is None or current_price <= 0:
    #                     continue

    #                 cfg = CONFIG.get(sym, {})
    #                 target = cfg.get('buy_target_price', float('inf'))
    #                 drop_pct = cfg.get('buy_drop_pct', 50.0)
    #                 last_buy_price = get_last_buy_price(sym) # from db/state

    #                 trigger = False
    #                 reason = ""
    #                 # 1. Absolute price target hit
    #                 if current_price <= target:
    #                     trigger = True
    #                     reason = f"hit absolute target ${target:.2f}"
                        
    #                 # 2. Percentage drop from last buy
    #                 if last_buy_price and current_price <= last_buy_price * (1 - drop_pct / 100):
    #                     trigger = True
    #                     reason = f"dropped ≥{drop_pct}% from last buy"

    #                 if trigger and self.risk_checks_pass(sym):
    #                     console.print(f"[bold red]BUY TRIGGER {sym}: {reason} @ ${current_price:.2f}[/bold red]")
    #                     self.place_buy_order(sym)
    #                     self.holdings[sym] = {
    #                         'shares': self.calculate_shares(sym, current_price),
    #                         'buy_price': current_price,
    #                         'limit_price': None,
    #                         'stop_price': None
    #                     }

    #         # Build current view data
    #         current_view = {}
    #         equity = self.get_account_equity()
    #         daily_pnl = (equity - self.daily_start_equity) / self.daily_start_equity * 100 if self.daily_start_equity > 0 else 0

    #         with self.lock:
    #             for sym in SYMBOLS:
    #                 price = self.current_prices.get(sym)
    #                 h = self.holdings.get(sym, {})
    #                 shares = h.get('shares', 0)
    #                 buy_p = h.get('buy_price')
    #                 pl_pct = ((price - buy_p) / buy_p * 100) if price and buy_p and buy_p > 0 else 0.0

    #                 current_view[sym] = {
    #                     'price': price,
    #                     'shares': shares,
    #                     'buy_price': buy_p,
    #                     'pl_pct': pl_pct,
    #                     'status': "HOLDING" if shares > 0 else "WATCHING"
    #                 }

    #         # Compute a simple hash / fingerprint of the view
    #         view_str = str(sorted(current_view.items())) + f"|{equity:.2f}|{daily_pnl:.2f}"
    #         current_hash = hash(view_str)   # or use hashlib.md5(view_str.encode()).hexdigest()

    #         # Only redraw if something changed
    #         if current_hash != last_state_hash:
    #             last_state_hash = current_hash

    #             # Build and print table
    #             table = Table(title=f"Bot Dashboard ─ {datetime.now().strftime('%H:%M:%S')}")
    #             table.add_column("Symbol", style="cyan")
    #             table.add_column("Price", justify="right")
    #             table.add_column("Position", justify="right")
    #             table.add_column("Avg Buy", justify="right")
    #             table.add_column("P/L %", justify="right")
    #             table.add_column("Status")

    #             with self.lock:
    #                 for sym in SYMBOLS:
    #                     v = current_view[sym]
    #                     price_str = f"${v['price']:.2f}" if v['price'] is not None else "—"
    #                     buy_str   = f"${v['buy_price']:.2f}" if v['buy_price'] else "—"
    #                     pl_str    = f"{v['pl_pct']:+.1f}%" if v['pl_pct'] != 0 else "+0.0%"

    #                     table.add_row(
    #                         sym,
    #                         price_str,
    #                         f"{v['shares']:.1f}",
    #                         buy_str,
    #                         pl_str,
    #                         v['status']
    #                     )

    #             # Risk footer
    #             risk_used_pct = (len(self.holdings) / RISK_CONFIG['max_positions']) * 100
    #             footer = (f"Equity: ${equity:,.0f} | Daily: {daily_pnl:+.1f}% | "
    #                       f"Risk: {risk_used_pct:.0f}% | {'PAUSED' if self.trading_paused else 'ACTIVE'}")

    #             console.clear()                     # ← optional: cleaner look
    #             console.print(table)
    #             console.print(f"[bold]{footer}[/bold]")

    #             # Optional: also log change reason in debug mode
    #             # console.print("[dim](table updated)[/dim]")    

    def update_holdings_from_api(self):
        # (same as previous version)
        try:
            pos = self.client.account_details(self.account_hash, fields="positions").json()
            positions = pos.get('securitiesAccount', {}).get('positions', [])
            new_h = {}
            for p in positions:
                sym = p['instrument']['symbol']
                if sym in SYMBOLS and float(p.get('longQuantity', 0)) > 0:
                    new_h[sym] = {'shares': float(p['longQuantity']), 'buy_price': p.get('averagePrice', 0)}
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

    console.print("\n[bold green]Bot running with FULL RISK MANAGEMENT. Press Ctrl+C to stop.[/bold green]\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()