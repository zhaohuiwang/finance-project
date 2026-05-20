from typing import Optional

import pandas as pd


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute RSI for the 'close' column using a simple rolling mean (not Wilder's EMA)."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_signals(
    df: pd.DataFrame,
    fast_ma: int,
    slow_ma: int,
    rsi_period: int,
    rsi_max_for_buy: float,
    volume_min_ratio: float = 0.0,
) -> tuple[Optional[str], Optional[float]]:
    """Derive a BUY/SELL/None signal from SMA crossover, RSI filter, and optional volume check.

    Returns (signal, current_rsi). Signal is 'BUY' on bullish crossover when RSI is
    below rsi_max_for_buy (and volume clears the threshold), 'SELL' on bearish
    crossover, or None to hold.
    """
    if len(df) < max(slow_ma, rsi_period + 10):
        return None, None

    df = df.copy()
    # Simple Moving Average (SMA) gives equal weight to all prices in the period.
    # df["fast_ma"] = df["close"].rolling(window=fast_ma).mean()
    # df["slow_ma"] = df["close"].rolling(window=slow_ma).mean()

    # Exponential Moving Average (EMA) gives more weight to recent prices.
    df["fast_ma"] = df["close"].ewm(span=fast_ma, adjust=False).mean()
    df["slow_ma"] = df["close"].ewm(span=slow_ma, adjust=False).mean()
    df["rsi"] = calculate_rsi(df, rsi_period)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None
    if (
        prev["fast_ma"] <= prev["slow_ma"]
        and latest["fast_ma"] > latest["slow_ma"] + 0.01
    ):  # add a small price buffer to reduce false signals in choppy markets
        if latest["rsi"] < rsi_max_for_buy:
            signal = "BUY"
    elif (
        prev["fast_ma"] >= prev["slow_ma"]
        and latest["fast_ma"] < latest["slow_ma"] - 0.01
    ):  # add a small price buffer to reduce false signals in choppy markets
        signal = "SELL"

    # Volume confirmation: suppress BUY if volume is below the rolling average threshold.
    # SELL signals are never suppressed by volume — exits don't need volume confirmation.
    if signal == "BUY" and volume_min_ratio > 0 and "volume" in df.columns:
        avg_vol = df["volume"].rolling(window=20).mean().iloc[-1]
        if avg_vol > 0 and latest["volume"] < avg_vol * volume_min_ratio:
            signal = None

    return signal, latest.get("rsi")


def is_uptrend(df: pd.DataFrame, fast_ma: int, slow_ma: int) -> bool:
    """Return True if fast MA is above slow MA on the most recent bar.

    Used for multi-timeframe confirmation: checks trend direction on a higher timeframe
    before acting on a signal from a lower timeframe. Returns True when there is
    insufficient data so as not to block signals unnecessarily.
    """
    if len(df) < slow_ma:
        return True  # not enough data — don't suppress the signal
    # fast = df["close"].rolling(window=fast_ma).mean().iloc[-1]
    # slow = df["close"].rolling(window=slow_ma).mean().iloc[-1]

    fast = df["close"].ewm(span=fast_ma, adjust=False).mean().iloc[-1]
    slow = df["close"].ewm(span=slow_ma, adjust=False).mean().iloc[-1]

    return bool(fast > slow)
