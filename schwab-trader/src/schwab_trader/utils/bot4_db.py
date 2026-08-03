

"""
schwab-trader/src/schwab_trader/utils/bot4_db.py

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

DB_PATH = Path("trading_bot4.db")


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
    

