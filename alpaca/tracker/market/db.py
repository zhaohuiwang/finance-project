"""SQLite persistence layer for market bars (class-based)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import DATABASE, RETENTION_DAYS

logger = logging.getLogger(__name__)


class MarketDatabase:
    """
    Manages the SQLite database for one-minute market bars.

    - Uses WAL mode for concurrent read/write
    - Handles schema creation, retention, insert/update, and queries
    """

    def __init__(self, db_path: Path | str = DATABASE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    def get_connection(self) -> sqlite3.Connection:
        """Return a connection with WAL mode enabled."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=15,
            check_same_thread=False,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    trade_count INTEGER,
                    vwap REAL,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_market_symbol_time
                ON market_bars(symbol, timestamp)
            """)
        self._initialized = True
        logger.info("Database initialized at %s", self.db_path)

    def cleanup_old_bars(self, days: int = RETENTION_DAYS) -> int:
        """Delete bars older than `days` calendar days (UTC)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM market_bars WHERE timestamp < ?",
                (cutoff,),
            )
            deleted = cur.rowcount
        if deleted:
            logger.info(
                "Retention cleanup: removed %s old bars (older than %s days)",
                deleted,
                days,
            )
        return deleted

    def save_bar(self, bar) -> None:
        """Insert or update a one-minute bar (ON CONFLICT DO UPDATE)."""
        timestamp = bar.timestamp.astimezone(timezone.utc).isoformat()

        trade_count = int(bar.trade_count) if bar.trade_count is not None else None
        vwap = float(bar.vwap) if bar.vwap is not None else None

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO market_bars (
                    symbol, timestamp, open, high, low,
                    close, volume, trade_count, vwap
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp)
                DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    trade_count = excluded.trade_count,
                    vwap = excluded.vwap
                """,
                (
                    bar.symbol,
                    timestamp,
                    float(bar.open),
                    float(bar.high),
                    float(bar.low),
                    float(bar.close),
                    float(bar.volume),
                    trade_count,
                    vwap,
                ),
            )

    def get_bars(self, symbol: str, limit: int = 500) -> pd.DataFrame:
        """Return the most recent bars for a symbol, ordered by timestamp ascending."""
        with self.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT *
                FROM market_bars
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                conn,
                params=(symbol, limit),
            )

        if df.empty:
            return df

        df = df.sort_values("timestamp").reset_index(drop=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df


# ------------------------------------------------------------------
# Convenience singleton (optional)
# ------------------------------------------------------------------
_db_instance: Optional[MarketDatabase] = None


def get_db() -> MarketDatabase:
    """Return a process-wide MarketDatabase instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = MarketDatabase()
        _db_instance.initialize()
    return _db_instance
