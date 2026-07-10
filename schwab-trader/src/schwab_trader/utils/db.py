# schwab-trader/src/schwab_trader/utils/db.py

import sqlite3
import datetime
import json
from pathlib import Path

DB_PATH = Path("logs/trading.db")
DB_PATH.parent.mkdir(exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
                    action       TEXT NOT NULL,
                    symbol       TEXT,
                    qty          REAL,
                    price        REAL,
                    order_id     TEXT,
                    order_status TEXT,
                    note         TEXT,
                    ts           TEXT NOT NULL
                )""")
    c.execute("""
              CREATE TABLE IF NOT EXISTS state (
              symbol TEXT PRIMARY KEY,
              last_buy_price REAL,
              last_buy_qty REAL,
              last_buy_time TEXT,
              last_sell_price REAL,
              last_sell_qty REAL,
              last_sell_time TEXT
              )
              """)
    conn.commit()
    conn.close()


def log_transaction(
    action: str,
    symbol: str,
    qty: float,
    price: float,
    order_id: str,
    order_status: str,
    note: str,
):
    conn = sqlite3.connect(DB_PATH)
    ts = datetime.datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO transactions 
        (action, symbol, qty, price, order_id, order_status, note, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (action, symbol, qty, price, order_id, order_status, note, ts),
    )
    conn.commit()
    conn.close()


def save_state(
    symbol: str,
    *,
    last_buy_price: float | None = None,
    last_buy_qty: float | None = None,
    last_sell_price: float | None = None,
    last_sell_qty: float | None = None,
):
    conn = sqlite3.connect(DB_PATH)
    ts = datetime.datetime.now().isoformat()

    existing = conn.execute(
        """
        SELECT
            last_buy_price,
            last_buy_qty,
            last_buy_time,
            last_sell_price,
            last_sell_qty,
            last_sell_time
        FROM state
        WHERE symbol=?
        """,
        (symbol,),
    ).fetchone()

    if existing:
        (
            buy_price,
            buy_qty,
            buy_time,
            sell_price,
            sell_qty,
            sell_time,
        ) = existing
    else:
        buy_price = buy_qty = buy_time = None
        sell_price = sell_qty = sell_time = None

    if last_buy_price is not None:
        buy_price = last_buy_price
        buy_qty = last_buy_qty
        buy_time = ts

    if last_sell_price is not None:
        sell_price = last_sell_price
        sell_qty = last_sell_qty
        sell_time = ts

    conn.execute(
        """
        REPLACE INTO state (
            symbol,
            last_buy_price,
            last_buy_qty,
            last_buy_time,
            last_sell_price,
            last_sell_qty,
            last_sell_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            buy_price,
            buy_qty,
            buy_time,
            sell_price,
            sell_qty,
            sell_time,
        ),
    )

    conn.commit()
    conn.close()


def load_state() -> dict:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT
            symbol,
            last_buy_price,
            last_buy_qty,
            last_sell_price,
            last_sell_qty
        FROM state
        """
    ).fetchall()
    conn.close()

    return {
        sym: {
            "buy_price": buy_price,
            "buy_qty": buy_qty,
            "sell_price": sell_price,
            "sell_qty": sell_qty,
        }
        for sym, buy_price, buy_qty, sell_price, sell_qty in rows
    }


def get_last_buy_price(symbol: str) -> float | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT last_buy_price FROM state WHERE symbol=?", (symbol,)
    ).fetchone()
    conn.close()
    return float(row[0]) if row else None


def get_last_buy_qty(symbol: str) -> float | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT last_buy_qty FROM state WHERE symbol=?", (symbol,)
    ).fetchone()
    conn.close()
    return float(row[0]) if row and row[0] is not None else None


def get_last_sell_price(symbol: str) -> float | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT last_sell_price FROM state WHERE symbol=?", (symbol,),
    ).fetchone()
    conn.close()
    return float(row[0]) if row and row[0] is not None else None


def get_last_sell_qty(symbol: str) -> float | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT last_sell_qty FROM state WHERE symbol=?", (symbol,),
    ).fetchone()
    conn.close()
    return float(row[0]) if row and row[0] is not None else None


def get_transaction_history() -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT * FROM transactions ORDER BY ts DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return rows
