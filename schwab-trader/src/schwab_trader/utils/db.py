# schwab-trader/src/schwab_trader/utils/db.py

import sqlite3
import datetime
import json
from pathlib import Path

# Use absolute path relative to the project root
X_level = 3
PROJECT_ROOT = Path(__file__).resolve().parents[X_level]  # X+1 levels up
DB_PATH = PROJECT_ROOT / "logs" / "trading.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

print(f"[DB] Using database at: {DB_PATH}")


def get_connection():
    """Get a database connection with timeout for thread safety."""
    return sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)

def init_db():
    """Initialize database tables (includes high_price from the start)."""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Transactions log
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                action       TEXT NOT NULL,
                symbol       TEXT,
                qty          REAL,
                price        REAL,
                order_id     TEXT,
                note         TEXT,
                ts           TEXT NOT NULL
            )
        """)

        # Per-symbol state (now includes high_price)
        c.execute("""
            CREATE TABLE IF NOT EXISTS state (
                symbol          TEXT PRIMARY KEY,
                last_buy_price  REAL,
                last_buy_qty    REAL,
                last_buy_time   TEXT,
                last_sell_price REAL,
                last_sell_qty   REAL,
                last_sell_time  TEXT,
                high_price      REAL,
                ts              TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

        print(f"[DB] ✅ Database initialized successfully at {DB_PATH}")
    except Exception as e:
        print(f"[DB ERROR] Failed to initialize database: {e}")
        import traceback
        traceback.print_exc()


def log_transaction(
    action: str,
    symbol: str,
    qty: float,
    price: float,
    order_id: str = None,
    note: str = None,
    ts: str = None
):
    """Log a transaction with optional fields."""
    try:
        conn = get_connection()
        ts = datetime.datetime.now().isoformat()

        conn.execute(
            """
            INSERT INTO transactions
            (action, symbol, qty, price, order_id, note, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (action, symbol, qty, price, order_id, note, ts),
        )
        conn.commit()
        conn.close()
        print(f"[DB] ✓ Logged {action} for {symbol} @ ${price:.2f} x {qty}")
    except sqlite3.Error as e:
        print(f"[DB ERROR] SQLite error while logging {action} {symbol}: {e}")
        import traceback

        traceback.print_exc()
    except Exception as e:
        print(f"[DB ERROR] Unexpected error while logging {action} {symbol}: {e}")
        import traceback

        traceback.print_exc()

def save_state(
    symbol: str,
    *,
    last_buy_price: float | None = None,
    last_buy_qty: float | None = None,
    last_sell_price: float | None = None,
    last_sell_qty: float | None = None,
    high_price: float | None = None,
    ts: str | None = None
):

    try:
        conn = get_connection()
        if ts is None:
            ts = datetime.datetime.now().isoformat()

        existing = conn.execute(
            """
            SELECT last_buy_price, last_buy_qty, last_buy_time,
                   last_sell_price, last_sell_qty, last_sell_time,
                   high_price
            FROM state WHERE symbol=?
            """,
            (symbol,),
        ).fetchone()

        if existing:
            buy_price, buy_qty, buy_time, sell_price, sell_qty, sell_time, high = existing
        else:
            buy_price = buy_qty = buy_time = None
            sell_price = sell_qty = sell_time = None
            high = None

        if last_buy_price is not None:
            buy_price = last_buy_price
            buy_qty = last_buy_qty
            buy_time = ts
            # On a new buy, seed the high-water mark
            if high_price is None:
                high = last_buy_price
        if last_sell_price is not None:
            sell_price = last_sell_price
            sell_qty = last_sell_qty
            sell_time = ts
            high = None                     # clear on exit
        if high_price is not None:
            high = high_price

        conn.execute(
            """
            REPLACE INTO state (
                symbol, last_buy_price, last_buy_qty, last_buy_time,
                last_sell_price, last_sell_qty, last_sell_time,
                high_price, ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol, buy_price, buy_qty, buy_time, sell_price, sell_qty, sell_time, high, ts),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] Failed to save state for {symbol}: {e}")
        import traceback
        traceback.print_exc()


# ==================== GETTERS ====================
def get_last_buy_price(symbol: str) -> float | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT last_buy_price FROM state WHERE symbol=?", (symbol,)
        ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        print(f"[DB] Error getting last buy price for {symbol}: {e}")
        return None


def get_last_buy_qty(symbol: str) -> float | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT last_buy_qty FROM state WHERE symbol=?", (symbol,)
        ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        print(f"[DB] Error getting last buy qty for {symbol}: {e}")
        return None


def get_last_sell_price(symbol: str) -> float | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT last_sell_price FROM state WHERE symbol=?", (symbol,)
        ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        print(f"[DB] Error getting last sell price for {symbol}: {e}")
        return None


def get_high_price(symbol: str) -> float | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT high_price FROM state WHERE symbol=?", (symbol,)
        ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        print(f"[DB] Error getting high_price for {symbol}: {e}")
        return None

    
def get_last_sell_qty(symbol: str) -> float | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT last_sell_qty FROM state WHERE symbol=?", (symbol,)
        ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        print(f"[DB] Error getting last sell qty for {symbol}: {e}")
        return None


def load_state() -> dict:
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT symbol, last_buy_price, last_buy_qty,
                   last_sell_price, last_sell_qty
            FROM state
            """).fetchall()
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
    except Exception as e:
        print(f"[DB] Error loading state: {e}")
        return {}


def get_transaction_history() -> list:
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY ts DESC LIMIT 100"
        ).fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"[DB] Error getting transaction history: {e}")
        return []


""""
# Common commands. 

sqlite3 logs/trading.db
.tables
sqlite> select * from state;
sqlite> select * from transactions;
.schema transactions;
.schema state;
.headers on
.mode column
SELECT * FROM transactions;
SELECT * FROM state;
"""
