# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/src/utils/atr.py
# ================================================================================

import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float | None:
    """
    Calculate the Average True Range (ATR).
    
    Standard method:
    1. Compute True Range (TR) for each bar
    2. Take simple moving average of TR over the period
    """
    if len(df) < period + 10:
        logger.debug(f"Not enough bars to calculate ATR (need {period+10}, got {len(df)})")
        return None

    # True Range calculation
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # Simple Moving Average (common implementation)
    atr_series = true_range.rolling(window=period).mean()
    latest_atr = atr_series.iloc[-1]

    if pd.isna(latest_atr):
        return None

    return float(latest_atr)