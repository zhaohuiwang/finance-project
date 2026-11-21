"""
SQLite persistence layer for one-minute OHLCV bars.

Two independent databases are used:
  - equity bars  (short retention)
  - VIX bars     (longer retention for regime analysis)

WAL mode is particularly useful here because the dashboard is continuously
reading while the WebSocket is writing.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .config import EASTERN

logger = logging.getLogger("market_monitor.database")


class BarDatabase:
    """
    Thin repository around a single SQLite file that stores minute bars.

    The schema is intentionally simple so that both the equity and VIX
    databases can share the same class.
    """

    def __init__(self, db_path: Path, retention_days: int) -> None:
        self.db_path = db_path
        self.retention_days = retention_days
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """
        Return a connection configured for concurrent read/write.

        WAL mode is particularly useful here because the dashboard is
        continuously reading while the WebSocket is writing.
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=15,
            check_same_thread=False,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the market_bars table and its index if they do not exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol      TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    open        REAL,
                    high        REAL,
                    low         REAL,
                    close       REAL,
                    volume      REAL,
                    trade_count INTEGER,
                    vwap        REAL,
                    PRIMARY KEY (symbol, timestamp)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_symbol_time
                ON market_bars(symbol, timestamp)
                """
            )

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def cleanup_old_bars(self) -> int:
        """
        Delete bars older than `retention_days` calendar days (UTC).

        Returns the number of rows deleted.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        ).isoformat()

        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM market_bars WHERE timestamp < ?",
                (cutoff,),
            )
            deleted = cur.rowcount

        if deleted:
            logger.info(
                "Retention cleanup (%s): removed %s old bars (>%s days)",
                self.db_path.name,
                deleted,
                self.retention_days,
            )
        return deleted

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_bar(self, bar: Any) -> None:
        """
        Insert or update a one-minute bar.

        Uses INSERT ... ON CONFLICT so that late-arriving "updatedBars"
        messages from Alpaca correctly overwrite the previous values.
        """
        timestamp = bar.timestamp.astimezone(timezone.utc).isoformat()
        trade_count = (
            int(bar.trade_count) if bar.trade_count is not None else None
        )
        vwap = float(bar.vwap) if bar.vwap is not None else None

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO market_bars (
                    symbol, timestamp, open, high, low,
                    close, volume, trade_count, vwap
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp)
                DO UPDATE SET
                    open        = excluded.open,
                    high        = excluded.high,
                    low         = excluded.low,
                    close       = excluded.close,
                    volume      = excluded.volume,
                    trade_count = excluded.trade_count,
                    vwap        = excluded.vwap
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

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_bars(self, symbol: str, limit: int = 500) -> pd.DataFrame:
        """
        Return the most recent `limit` bars for `symbol`, ordered
        chronologically (oldest first).
        """
        with self._get_connection() as conn:
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

    def get_daily_closes(self, symbol: str, days: int) -> pd.DataFrame:
        """
        Last close of each calendar day (US/Eastern).

        Used primarily for the VIX regime calculation.
        """
        # Rough upper bound: ~390 trading minutes per day
        df = self.get_bars(symbol, limit=days * 450)
        if df.empty:
            return pd.DataFrame(columns=["date", "close"])

        eastern = df["timestamp"].dt.tz_convert(EASTERN)
        df = df.copy()
        df["date"] = eastern.dt.date

        daily = (
            df.sort_values("timestamp")
            .groupby("date", as_index=False)
            .last()[["date", "close"]]
        )
        return daily.tail(days).reset_index(drop=True)
