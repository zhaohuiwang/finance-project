# db.py
import sqlite3
import os
from datetime import datetime
import json

DB_FILE = "trading_bot.db"


def init_db():
    if not os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                action TEXT,
                symbol TEXT,
                shares REAL,
                price REAL,
                order_type TEXT,
                note TEXT
            )
        """)
        c.execute("""
            CREATE TABLE state (
                symbol TEXT PRIMARY KEY,
                last_buy_price REAL,
                last_buy_time TEXT
            )
        """)
        conn.commit()
        conn.close()


def log_transaction(action, symbol, shares, price, order_type="MARKET", note=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    ts = datetime.now().isoformat()
    c.execute(
        """
        INSERT INTO transactions (timestamp, action, symbol, shares, price, order_type, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (ts, action, symbol, shares, price, order_type, note),
    )
    conn.commit()
    conn.close()
    print(f"LOGGED [{ts}] {action} {shares} {symbol} @ ${price:.2f}  ({note})")


def save_state(symbol, last_buy_price):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO state (symbol, last_buy_price, last_buy_time)
        VALUES (?, ?, ?)
    """,
        (symbol, last_buy_price, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_state():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT symbol, last_buy_price FROM state")
    rows = c.fetchall()
    conn.close()
    return {row[0]: {"last_buy_price": row[1]} for row in rows}


def get_last_buy_price(symbol):
    state = load_state()
    return state.get(symbol, {}).get("last_buy_price")
