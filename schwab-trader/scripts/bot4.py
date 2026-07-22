

# simple_bot_config.yaml
risk:
  min_account_equity: 5000
  max_positions: 4

auto_shutdown_after_close: true
shutdown_buffer_minutes: 2

symbols:
  AAPL:
    fixed_shares: 50
    momentum_up_pct: 5.0
    trailing_sell_pct: 2.0
    pullback_buy_pct: 3.0
    trailing_buy_pct: 1.5
  NVDA:
    fixed_shares: 30
    momentum_up_pct: 6.0
    trailing_sell_pct: 2.5
    pullback_buy_pct: 3.5
    trailing_buy_pct: 2.0


"""
Schwab Trading Bot Configuration Module
=======================================

Pydantic-based configuration system with full support for the trailing momentum strategy.
"""

from pydantic import BaseModel, Field
from pathlib import Path
import yaml
from typing import Dict


class SymbolConfig(BaseModel):
    """
    Configuration for individual trading symbols in the trailing momentum strategy.
    """
    # Core trading parameters
    fixed_shares: int = Field(
        default=100, 
        ge=1, 
        description="Number of shares to trade per order"
    )
    
    # Momentum Sell Parameters
    momentum_up_pct: float = Field(
        default=5.0, 
        ge=0.0, 
        description="x% gain from previous day's close to trigger trailing sell"
    )
    trailing_sell_pct: float = Field(
        default=2.0, 
        ge=0.1, 
        description="a% trailing stop percentage for sell orders"
    )
    
    # Pullback Buy Parameters
    pullback_buy_pct: float = Field(
        default=3.0, 
        ge=0.0, 
        description="y% drop from last sell price to trigger trailing buy"
    )
    trailing_buy_pct: float = Field(
        default=1.5, 
        ge=0.1, 
        description="b% trailing stop percentage for buy orders"
    )
    
    # Additional risk controls
    max_position_value: float = Field(
        default=10000.0, 
        ge=0.0, 
        description="Maximum dollar value per position"
    )


class RiskConfig(BaseModel):
    """
    Global risk management settings for the trading bot.
    """
    min_account_equity: float = Field(
        default=5000.0, 
        ge=1000.0, 
        description="Minimum account equity before pausing trading"
    )
    max_positions: int = Field(
        default=4, 
        ge=1, 
        description="Maximum number of concurrent positions"
    )


class TradingConfig(BaseModel):
    """
    Main configuration container for the entire trading bot.
    """
    risk: RiskConfig = Field(default_factory=RiskConfig)
    symbols: Dict[str, SymbolConfig] = Field(default_factory=dict)
    
    # Bot behavior settings
    auto_shutdown_after_close: bool = Field(
        default=True, 
        description="Automatically shutdown after market close"
    )
    shutdown_buffer_minutes: int = Field(
        default=2, 
        ge=0, 
        description="Minutes to wait after market close before shutdown"
    )
    shutdown_on_weekends: bool = Field(
        default=True, 
        description="Shutdown on weekends"
    )

    @classmethod
    def load_from_file(cls, config_path: Path) -> "TradingConfig":
        """
        Load configuration from a YAML file.
        
        Args:
            config_path: Path to the YAML configuration file
            
        Returns:
            TradingConfig instance
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # Convert symbol dictionaries to SymbolConfig objects
        if "symbols" in data and isinstance(data["symbols"], dict):
            symbols_dict = {}
            for symbol, config_data in data["symbols"].items():
                symbols_dict[symbol] = SymbolConfig(**config_data)
            data["symbols"] = symbols_dict
        
        # Convert risk config
        if "risk" in data and isinstance(data["risk"], dict):
            data["risk"] = RiskConfig(**data["risk"])
        
        return cls(**data)

    def save_to_file(self, config_path: Path):
        """
        Save current configuration to a YAML file.
        
        Args:
            config_path: Path where to save the config
        """
        data = self.model_dump(mode='python')
        
        # Convert Pydantic objects to dicts for YAML serialization
        if isinstance(data.get("symbols"), dict):
            for sym, cfg in data["symbols"].items():
                if hasattr(cfg, "model_dump"):
                    data["symbols"][sym] = cfg.model_dump()
        
        if hasattr(data.get("risk"), "model_dump"):
            data["risk"] = data["risk"].model_dump()
        
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data, 
                f, 
                default_flow_style=False, 
                sort_keys=False,
                indent=2
            )

    def get_symbol_config(self, symbol: str) -> SymbolConfig | None:
        """Get configuration for a specific symbol."""
        return self.symbols.get(symbol)


# Example default configuration (for reference)
DEFAULT_CONFIG = {
    "risk": {
        "min_account_equity": 5000,
        "max_positions": 4
    },
    "symbols": {
        "AAPL": {
            "fixed_shares": 50,
            "momentum_up_pct": 5.0,
            "trailing_sell_pct": 2.0,
            "pullback_buy_pct": 3.0,
            "trailing_buy_pct": 1.5
        },
        "NVDA": {
            "fixed_shares": 30,
            "momentum_up_pct": 6.0,
            "trailing_sell_pct": 2.5,
            "pullback_buy_pct": 3.5,
            "trailing_buy_pct": 2.0
        }
    },
    "auto_shutdown_after_close": True,
    "shutdown_buffer_minutes": 2
}



# onfig_path = Path("conf/simple_bot_config.yaml")
# cfg = TradingConfig.load_from_file(config_path)




"""
Database Utilities for Trading Bot
==================================
Simple SQLite-based persistence for transaction logging and state tracking.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from rich.console import Console

console = Console()

DB_PATH = Path("trading_bot.db")


def init_db():
    """Initialize SQLite database and tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            action TEXT,
            symbol TEXT,
            quantity REAL,
            price REAL,
            order_id TEXT,
            note TEXT
        )
    """)
    
    # State table for last buy/sell prices
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS state (
            symbol TEXT PRIMARY KEY,
            last_buy_price REAL,
            last_buy_qty REAL,
            last_sell_price REAL,
            last_sell_qty REAL,
            updated_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    console.print("[green]Database initialized[/green]")


def log_transaction(action: str, symbol: str, qty: float, price: float, 
                   order_id: str = None, note: str = ""):
    """Log a transaction to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions 
            (timestamp, action, symbol, quantity, price, order_id, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            action,
            symbol,
            qty,
            price,
            order_id,
            note
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        console.print(f"[red]Failed to log transaction: {e}[/red]")


def save_state(symbol: str, last_buy_price=None, last_buy_qty=None,
               last_sell_price=None, last_sell_qty=None):
    """Save persistent state for a symbol."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO state 
            (symbol, last_buy_price, last_buy_qty, last_sell_price, last_sell_qty, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            last_buy_price,
            last_buy_qty,
            last_sell_price,
            last_sell_qty,
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        console.print(f"[red]Failed to save state: {e}[/red]")


def get_last_buy_price(symbol: str) -> float | None:
    """Retrieve last buy price for a symbol."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT last_buy_price FROM state WHERE symbol = ?", (symbol,))
        result = cursor.fetchone()
        conn.close()
        return float(result[0]) if result and result[0] is not None else None
    except:
        return None


def get_last_sell_price(symbol: str) -> float | None:
    """Retrieve last sell price for a symbol."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT last_sell_price FROM state WHERE symbol = ?", (symbol,))
        result = cursor.fetchone()
        conn.close()
        return float(result[0]) if result and result[0] is not None else None
    except:
        return None
    


"""
Schwab Trailing Momentum Bot - Launcher
=======================================
Main entry point for the trading bot with CLI and Dashboard support.
"""

import argparse
import sys
import threading
import time
from pathlib import Path
from rich.console import Console
from schwab_trader.config.bot.config import TradingConfig
from schwab_trader.pipelines.bot3_pipeline import TradingBot
from dashboard import run_dashboard

console = Console()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schwab Trailing Momentum Trading Bot")
    parser.add_argument("--mode", choices=["full", "cli", "headless"], default="full")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()

    config_path = Path(__file__).parent / "../conf/simple_bot_config.yaml"
    
    if not config_path.exists():
        console.print(f"[red]Config not found: {config_path}[/red]")
        sys.exit(1)

    cfg = TradingConfig.load_from_file(config_path)
    bot = TradingBot(cfg, mode=args.mode, config_path=config_path)

    console.print(f"[bold green]Starting Trailing Momentum Bot in {args.mode} mode[/bold green]")

    bot.start()

    # CLI
    if args.mode in ("full", "cli") and sys.stdin.isatty():
        def cli_loop():
            console.print("[cyan]Commands: stop | reload | status | positions[/cyan]")
            while bot.running:
                try:
                    cmd = input("> ").strip().lower()
                    if cmd == "stop":
                        bot.stop()
                        break
                    elif cmd == "reload":
                        bot.reload_config()
                    elif cmd == "status":
                        snap = bot.get_account_snapshot()
                        print(f"Equity: ${snap['equity']:,.2f} | Positions: {len(bot.holdings)}")
                    elif cmd == "positions":
                        bot.update_holdings_from_api()
                        for sym, h in bot.holdings.items():
                            print(f"{sym}: {h['shares']} shares")
                except:
                    break
        threading.Thread(target=cli_loop, daemon=True).start()

    # Dashboard
    if args.mode == "full":
        try:
            run_dashboard(bot, port=args.port)
        except Exception as e:
            console.print(f"[yellow]Dashboard error: {e}[/yellow]")

    # Keep alive
    try:
        while bot.running:
            time.sleep(10)
    except KeyboardInterrupt:
        bot.stop()



"""
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
from schwab_trader.config.bot.config import TradingConfig, SymbolConfig
from schwab_trader.utils.db import (
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




# schwab-trader/dashboard.py
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from datetime import datetime
import threading
import time

def run_dashboard(bot, port=8050):
    """Launch interactive Dash dashboard for the trading bot."""
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
    
    app.layout = dbc.Container([
        dbc.Row([
            dbc.Col(html.H1("Schwab Trailing Momentum Bot", className="text-center mb-4"), width=12)
        ]),
        dbc.Row([
            dbc.Col([
                html.Div(id="status", className="mb-3"),
                dbc.Button("Refresh", id="refresh-btn", color="primary", className="mb-3"),
                dbc.Button("Reload Config", id="reload-btn", color="info", className="mb-3 mx-2"),
                dbc.Button("Stop Bot", id="stop-btn", color="danger")
            ], width=12)
        ]),
        dbc.Row([
            dbc.Col([
                dcc.Graph(id="price-chart"),
                dcc.Interval(id="interval", interval=5000, n_intervals=0)  # 5s refresh
            ], width=8),
            dbc.Col([
                html.H4("Holdings"),
                html.Div(id="holdings-table"),
                html.H4("Prices & Momentum", className="mt-4"),
                html.Div(id="prices-table")
            ], width=4)
        ])
    ], fluid=True)

    @app.callback(
        [Output("status", "children"),
         Output("price-chart", "figure"),
         Output("holdings-table", "children"),
         Output("prices-table", "children")],
        [Input("interval", "n_intervals"),
         Input("refresh-btn", "n_clicks")]
    )
    def update_dashboard(n, refresh_clicks):
        snap = bot.get_account_snapshot()
        status = dbc.Alert(
            f"Equity: ${snap['equity']:,.2f} | Cash: ${snap['cashBalance']:,.2f} | "
            f"Positions: {len(bot.holdings)} | Paused: {bot.trading_paused}",
            color="success" if snap["equity"] > bot.daily_start_equity else "warning"
        )

        # Price & Momentum Table
        price_rows = []
        for sym in bot.symbols:
            price = bot.current_market_prices.get(sym)
            prev = bot.previous_closes.get(sym)
            if price and prev:
                pct = ((price - prev) / prev) * 100
                color = "green" if pct > 0 else "red"
                price_rows.append(html.Tr([
                    html.Td(sym),
                    html.Td(f"${price:.2f}"),
                    html.Td(html.Span(f"{pct:+.1f}%", style={"color": color}))
                ]))

        prices_table = dbc.Table([
            html.Thead(html.Tr([html.Th("Symbol"), html.Th("Price"), html.Th("Momentum")]))
        ] + [html.Tbody(price_rows)], bordered=True, dark=True)

        # Holdings
        holdings_rows = []
        for sym, h in bot.holdings.items():
            holdings_rows.append(html.Tr([
                html.Td(sym),
                html.Td(h["shares"]),
                html.Td(f"${h.get('buy_price', 0):.2f}")
            ]))
        holdings_table = dbc.Table([
            html.Thead(html.Tr([html.Th("Symbol"), html.Th("Shares"), html.Th("Avg Price")]))
        ] + [html.Tbody(holdings_rows)], bordered=True, dark=True) if holdings_rows else html.P("No positions")

        # Simple price line chart (last few updates - basic)
        fig = go.Figure()
        for sym in list(bot.symbols)[:3]:  # Limit to 3 for clarity
            price = bot.current_market_prices.get(sym)
            if price:
                fig.add_trace(go.Scatter(
                    x=[datetime.now().strftime("%H:%M:%S")],
                    y=[price],
                    mode="lines+markers",
                    name=sym
                ))
        fig.update_layout(title="Live Prices", template="plotly_dark", height=400)

        return status, fig, holdings_table, prices_table

    @app.callback(
        Output("status", "children"),
        Input("reload-btn", "n_clicks")
    )
    def reload_config_callback(n):
        if n:
            bot.reload_config()
            return dbc.Alert("Config reloaded successfully!", color="info")
        return dash.no_update

    @app.callback(
        Output("status", "children"),
        Input("stop-btn", "n_clicks")
    )
    def stop_bot_callback(n):
        if n:
            bot.stop()
            return dbc.Alert("Bot stopped. Restart the script to run again.", color="danger")
        return dash.no_update

    print(f"🚀 Dashboard running at http://127.0.0.1:{port}")
    app.run_server(debug=False, port=port, use_reloader=False)