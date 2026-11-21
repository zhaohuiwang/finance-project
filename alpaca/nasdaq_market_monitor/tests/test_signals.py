"""Unit tests for EquitySignalCalculator and VixSignalCalculator."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

from market_monitor.signals import (
    EquitySignalCalculator,
    VixSignalCalculator,
    EquitySignal,
    VixSignal,
)
from market_monitor.indicators import IndicatorCalculator


def _make_indicator_df(n: int = 40, trend: str = "up") -> pd.DataFrame:
    """Generate bars + indicators with a controllable trend."""
    now = datetime(2024, 6, 3, 14, 30, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    for i in range(n):
        ts = now + timedelta(minutes=i)
        if trend == "up":
            price *= 1.001
        elif trend == "down":
            price *= 0.999
        # else flat
        rows.append(
            {
                "timestamp": ts,
                "open": price,
                "high": price * 1.001,
                "low": price * 0.999,
                "close": price,
                "volume": 1000.0,
            }
        )
    df = pd.DataFrame(rows)
    return IndicatorCalculator().calculate(df)


class TestEquitySignalCalculator:
    def test_empty(self):
        calc = EquitySignalCalculator()
        result = calc.calculate(pd.DataFrame())
        assert isinstance(result, EquitySignal)
        assert result.signal == "NO DATA"
        assert result.warmup is True
        assert result.bars == 0

    def test_warmup(self):
        df = _make_indicator_df(n=5)
        calc = EquitySignalCalculator()
        result = calc.calculate(df)
        assert "WARMING UP" in result.signal
        assert result.warmup is True

    def test_bullish_trend(self):
        df = _make_indicator_df(n=40, trend="up")
        calc = EquitySignalCalculator()
        result = calc.calculate(df)
        assert isinstance(result, EquitySignal)
        # Strong uptrend should produce a non-bearish signal
        assert result.signal in ("BULLISH", "NEUTRAL")
        assert result.score is not None
        assert result.score >= 0

    def test_bearish_trend(self):
        df = _make_indicator_df(n=40, trend="down")
        calc = EquitySignalCalculator()
        result = calc.calculate(df)
        assert result.signal in ("BEARISH", "NEUTRAL")
        assert result.score is not None
        assert result.score <= 0


class TestVixSignalCalculator:
    def test_empty(self):
        calc = VixSignalCalculator()
        result = calc.calculate(pd.DataFrame())
        assert isinstance(result, VixSignal)
        assert result.signal == "NO DATA"

    def test_low_vol(self):
        daily = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10),
                "close": [12.0] * 10,
            }
        )
        calc = VixSignalCalculator()
        result = calc.calculate(daily)
        assert result.level == "LOW"
        assert result.signal in ("LOW VOL", "COMPLACENCY")

    def test_high_vol(self):
        daily = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10),
                "close": [40.0] * 10,
            }
        )
        calc = VixSignalCalculator()
        result = calc.calculate(daily)
        assert result.level == "HIGH"
        assert result.signal in ("HIGH VOL", "RISING FEAR")
