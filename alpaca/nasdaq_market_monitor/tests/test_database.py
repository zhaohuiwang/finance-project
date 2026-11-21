"""Unit tests for BarDatabase (uses a temporary SQLite file)."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from market_monitor.database import BarDatabase


@pytest.fixture
def tmp_db(tmp_path: Path) -> BarDatabase:
    db_path = tmp_path / "test_bars.db"
    db = BarDatabase(db_path, retention_days=7)
    db.initialize()
    return db


def _fake_bar(
    symbol: str = "AAPL",
    minutes_ago: int = 0,
    close: float = 150.0,
) -> SimpleNamespace:
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return SimpleNamespace(
        symbol=symbol,
        timestamp=ts,
        open=close - 0.5,
        high=close + 0.5,
        low=close - 1.0,
        close=close,
        volume=1000.0,
        trade_count=50,
        vwap=close,
    )


class TestBarDatabase:
    def test_initialize_creates_table(self, tmp_db: BarDatabase):
        # Should not raise
        tmp_db.initialize()

    def test_save_and_get_bar(self, tmp_db: BarDatabase):
        bar = _fake_bar(symbol="AAPL", close=175.25)
        tmp_db.save_bar(bar)

        df = tmp_db.get_bars("AAPL", limit=10)
        assert len(df) == 1
        assert df.iloc[0]["close"] == pytest.approx(175.25)
        assert df.iloc[0]["symbol"] == "AAPL"

    def test_upsert_on_conflict(self, tmp_db: BarDatabase):
        bar1 = _fake_bar(close=100.0)
        tmp_db.save_bar(bar1)

        # Same timestamp, different close
        bar2 = _fake_bar(close=105.0)
        # Force same timestamp
        bar2.timestamp = bar1.timestamp
        tmp_db.save_bar(bar2)

        df = tmp_db.get_bars("AAPL")
        assert len(df) == 1
        assert df.iloc[0]["close"] == pytest.approx(105.0)

    def test_get_bars_empty(self, tmp_db: BarDatabase):
        df = tmp_db.get_bars("NONEXISTENT")
        assert df.empty

    def test_cleanup_old_bars(self, tmp_db: BarDatabase):
        # Insert an old bar (10 days ago)
        old_bar = _fake_bar(minutes_ago=10 * 24 * 60)
        tmp_db.save_bar(old_bar)

        # Insert a recent bar
        new_bar = _fake_bar(minutes_ago=5)
        # Different timestamp so both are stored
        new_bar.timestamp = datetime.now(timezone.utc)
        tmp_db.save_bar(new_bar)

        deleted = tmp_db.cleanup_old_bars()
        assert deleted >= 1

        df = tmp_db.get_bars("AAPL")
        # Only the recent bar should remain
        assert len(df) == 1
        assert df.iloc[0]["close"] == pytest.approx(150.0)

    def test_get_daily_closes(self, tmp_db: BarDatabase):
        # Insert a few bars on the same day
        for i in range(5):
            bar = _fake_bar(minutes_ago=i * 10, close=100.0 + i)
            tmp_db.save_bar(bar)

        daily = tmp_db.get_daily_closes("AAPL", days=5)
        assert not daily.empty
        assert "date" in daily.columns
        assert "close" in daily.columns
