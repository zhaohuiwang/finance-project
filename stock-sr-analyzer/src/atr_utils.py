"""ATR calculation and ATR-normalized zone helpers."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .detectors import Level


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder-style Average True Range."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return atr


def atr_zone_width(atr_value: float, multiplier: float = 0.5) -> float:
    """Half-width of an ATR-normalized zone."""
    return float(atr_value) * multiplier


def make_atr_zones(
    levels: List[Level],
    atr_series: pd.Series,
    multiplier: float = 0.5,
) -> List[dict]:
    """
    Convert point levels into ATR-normalized zones.
    Returns list of dicts: {price, low, high, kind, strength, score, method, timeframe, atr}
    """
    if atr_series.empty:
        last_atr = 1.0
    else:
        last_atr = float(atr_series.iloc[-1])

    zones = []
    for L in levels:
        half = atr_zone_width(last_atr, multiplier)
        zones.append(
            {
                "price": L.price,
                "zone_low": L.price - half,
                "zone_high": L.price + half,
                "kind": L.kind,
                "strength": L.strength,
                "score": L.score,
                "method": L.method,
                "timeframe": L.timeframe,
                "atr": last_atr,
                "width_pct": (2 * half / L.price) * 100 if L.price else 0,
            }
        )
    return zones


def price_in_zone(price: float, zone: dict) -> bool:
    return zone["zone_low"] <= price <= zone["zone_high"]


def distance_in_atr(price: float, level_price: float, atr: float) -> float:
    """Signed distance in ATR units (negative = below level)."""
    if atr <= 0:
        return 0.0
    return (price - level_price) / atr
