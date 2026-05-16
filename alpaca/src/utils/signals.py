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
) -> tuple[Optional[str], Optional[float]]:
    """Derive a BUY/SELL/None signal from SMA crossover and RSI filter.

    Returns (signal, current_rsi). Signal is 'BUY' on bullish crossover when RSI is
    below rsi_max_for_buy, 'SELL' on bearish crossover, or None to hold.
    """
    if len(df) < max(slow_ma, rsi_period + 10):
        return None, None

    df = df.copy()
    df["fast_ma"] = df["close"].rolling(window=fast_ma).mean()
    df["slow_ma"] = df["close"].rolling(window=slow_ma).mean()
    df["rsi"] = calculate_rsi(df, rsi_period)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None
    if prev["fast_ma"] <= prev["slow_ma"] and latest["fast_ma"] > latest["slow_ma"]:
        if latest["rsi"] < rsi_max_for_buy:
            signal = "BUY"
    elif prev["fast_ma"] >= prev["slow_ma"] and latest["fast_ma"] < latest["slow_ma"]:
        signal = "SELL"

    return signal, latest.get("rsi")
