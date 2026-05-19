# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/src/utils/atr.py
# ================================================================================

import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)


def calculate_atr(df: pd.DataFrame, period: int = 14, wilder: bool = True) -> float | None:
    """
    Calculate Average True Range (ATR).
    
    wilder=True  → Uses J. Welles Wilder's original smoothing method (recommended)
    wilder=False → Uses simple rolling mean
    """
    if len(df) < period + 10:
        logger.debug(f"Not enough bars for ATR (need {period+10}, got {len(df)})")
        return None

    # Step 1: True Range
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    if wilder:
        # === Wilder's Smoothed ATR (Original & Preferred Method) ===
        atr = true_range.copy()
        # First value = simple average
        atr.iloc[period-1] = true_range.iloc[:period].mean()

        # Subsequent values: Wilder's smoothing formula
        for i in range(period, len(atr)):
            atr.iloc[i] = (atr.iloc[i-1] * (period - 1) + true_range.iloc[i]) / period

        latest_atr = atr.iloc[-1]
    else:
        # Simple Moving Average
        atr = true_range.rolling(window=period).mean()
        latest_atr = atr.iloc[-1]

    if pd.isna(latest_atr):
        return None

    return float(latest_atr)