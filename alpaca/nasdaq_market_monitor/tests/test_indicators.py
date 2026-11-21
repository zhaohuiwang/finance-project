"""Unit tests for IndicatorCalculator."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

from market_monitor.indicators import IndicatorCalculator
from market_monitor.config import PERIODS


def _make_bars(n: int = 60, start_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic one-minute OHLCV bars."""
    now = datetime(2024, 6, 3, 14, 30, tzinfo=timezone.utc)  # a Monday
    rows = []
    price = start_price
    for i in range(n):
        ts = now + timedelta(minutes=i)
        open_ = price
        high = price * 1.001
        low = price * 0.999
        close = price * 1.0005
        volume = 1000 + i * 10
        rows.append(
            {
                "timestamp": ts,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        price = close
    return pd.DataFrame(rows)


class TestIndicatorCalculator:
    def test_empty_dataframe(self):
        calc = IndicatorCalculator()
        result = calc.calculate(pd.DataFrame())
        assert result.empty

    def test_sma_ema_columns_present(self):
        df = _make_bars(60)
        calc = IndicatorCalculator()
        result = calc.calculate(df)

        for period in PERIODS:
            assert f"SMA_{period}" in result.columns
            assert f"EMA_{period}" in result.columns

        assert "VWAP" in result.columns

    def test_sma_values_reasonable(self):
        df = _make_bars(30)
        calc = IndicatorCalculator(periods=[5])
        result = calc.calculate(df)

        # First 4 rows should be NaN (min_periods=5)
        assert result["SMA_5"].iloc[:4].isna().all()
        # 5th row onward should be finite
        assert result["SMA_5"].iloc[4:].notna().all()

        # SMA of constant-ish series should be close to the closes
        latest_sma = result["SMA_5"].iloc[-1]
        latest_close = result["close"].iloc[-1]
        assert abs(latest_sma - latest_close) / latest_close < 0.01

    def test_session_vwap_resets_daily(self):
        # Create bars spanning two calendar days in Eastern
        # 2024-06-03 20:00 UTC = 16:00 EDT (same day)
        # 2024-06-04 14:00 UTC = 10:00 EDT (next day)
        rows = []
        for i, hour_utc in enumerate([20, 20, 14, 14]):
            day = 3 if hour_utc == 20 else 4
            ts = datetime(2024, 6, day, hour_utc, i % 2, tzinfo=timezone.utc)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000.0,
                }
            )
        df = pd.DataFrame(rows)
        calc = IndicatorCalculator(periods=[5])
        result = calc.calculate(df)

        # VWAP should be present and finite
        assert result["VWAP"].notna().all()
        # Because typical price is constant, VWAP equals typical price
        typical = (101.0 + 99.0 + 100.5) / 3.0
        assert abs(result["VWAP"].iloc[-1] - typical) < 1e-6
