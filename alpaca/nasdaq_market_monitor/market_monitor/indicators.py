"""
Technical indicator calculations (SMA, EMA, session VWAP).

All calculations operate on a DataFrame of one-minute bars that already
contains the columns: timestamp, open, high, low, close, volume.
"""

from __future__ import annotations

import pandas as pd

from .config import PERIODS, EASTERN


class IndicatorCalculator:
    """
    Computes Simple Moving Averages, Exponential Moving Averages and
    session-based VWAP on a bar DataFrame.
    """

    def __init__(self, periods: list[int] | None = None) -> None:
        self.periods = periods if periods is not None else PERIODS

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a copy of `df` with indicator columns appended.

        SMA / EMA columns are named ``SMA_{period}`` and ``EMA_{period}``.
        Session VWAP is named simply ``VWAP``.
        """
        if df.empty:
            return df

        df = df.copy()

        # ----------- Moving averages -----------
        for period in self.periods:
            df[f"SMA_{period}"] = (
                df["close"].rolling(window=period, min_periods=period).mean()
            )
            df[f"EMA_{period}"] = (
                df["close"].ewm(span=period, adjust=False, min_periods=period).mean()
            )

        # --- Session VWAP (resets each calendar day in US/Eastern) ----
        # Convert to Eastern so the daily boundary matches the regular
        # trading session.
        eastern_ts = df["timestamp"].dt.tz_convert(EASTERN)
        df["_session_date"] = eastern_ts.dt.date

        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0

        # Cumulative volume and cumulative (typical_price * volume)
        # within each session day
        df["_cum_vol"] = df.groupby("_session_date")["volume"].cumsum()
        df["_cum_tp_vol"] = (
            (typical_price * df["volume"]).groupby(df["_session_date"]).cumsum()
        )
        df["VWAP"] = df["_cum_tp_vol"] / df["_cum_vol"]

        # Clean up helper columns
        df = df.drop(columns=["_session_date", "_cum_vol", "_cum_tp_vol"])
        return df
