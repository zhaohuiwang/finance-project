"""Algorithms to detect support and resistance levels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from sklearn.cluster import AgglomerativeClustering, KMeans


@dataclass
class Level:
    """A single support or resistance level with metadata."""

    price: float
    kind: str  # "support" | "resistance" | "both"
    strength: int = 1  # number of touches / cluster size
    method: str = ""
    touches: List[pd.Timestamp] = field(default_factory=list)
    timeframe: str = "daily"  # "daily" | "weekly" | "confluence"
    score: float = 0.0  # composite 0-100 (filled later by backtester or confluence)

    def __repr__(self) -> str:
        return (
            f"Level({self.kind} @ {self.price:.2f}, str={self.strength}, "
            f"score={self.score:.1f}, method={self.method}, tf={self.timeframe})"
        )


def _cluster_prices(
    prices: np.ndarray,
    timestamps: Optional[List] = None,
    tolerance_pct: float = 1.5,
    min_strength: int = 2,
) -> List[Tuple[float, int, List]]:
    """
    Cluster prices that lie within tolerance_pct of each other.
    Returns list of (cluster_mean, strength, member_timestamps).
    """
    if len(prices) == 0:
        return []

    # Sort
    order = np.argsort(prices)
    prices = prices[order]
    if timestamps is not None:
        timestamps = [timestamps[i] for i in order]

    clusters = []
    current = [prices[0]]
    current_ts = [timestamps[0]] if timestamps else []

    for i in range(1, len(prices)):
        # relative distance to current cluster mean
        mean = np.mean(current)
        if abs(prices[i] - mean) / mean * 100 <= tolerance_pct:
            current.append(prices[i])
            if timestamps:
                current_ts.append(timestamps[i])
        else:
            if len(current) >= min_strength:
                clusters.append((float(np.mean(current)), len(current), current_ts.copy()))
            current = [prices[i]]
            current_ts = [timestamps[i]] if timestamps else []

    if len(current) >= min_strength:
        clusters.append((float(np.mean(current)), len(current), current_ts.copy()))

    return clusters


# ---------------------------------------------------------------------------
# 1. Swing High / Low + Clustering
# ---------------------------------------------------------------------------
def detect_swing_levels(
    df: pd.DataFrame,
    prominence_pct: float = 1.5,
    distance: int = 5,
    tolerance_pct: float = 1.8,
    min_strength: int = 2,
) -> List[Level]:
    """
    Find local extrema with scipy.signal.find_peaks, then cluster them.
    """
    highs = df["High"].values
    lows = df["Low"].values
    idx = df.index

    # Adaptive prominence based on recent volatility
    atr_proxy = np.mean(highs - lows)
    prom = max(atr_proxy * (prominence_pct / 100), atr_proxy * 0.3)

    peak_idx, _ = find_peaks(highs, distance=distance, prominence=prom)
    valley_idx, _ = find_peaks(-lows, distance=distance, prominence=prom)

    res_prices = highs[peak_idx]
    res_ts = [idx[i] for i in peak_idx]
    sup_prices = lows[valley_idx]
    sup_ts = [idx[i] for i in valley_idx]

    levels: List[Level] = []

    for mean, strength, ts_list in _cluster_prices(res_prices, res_ts, tolerance_pct, min_strength):
        levels.append(
            Level(price=mean, kind="resistance", strength=strength, method="swing", touches=ts_list)
        )
    for mean, strength, ts_list in _cluster_prices(sup_prices, sup_ts, tolerance_pct, min_strength):
        levels.append(
            Level(price=mean, kind="support", strength=strength, method="swing", touches=ts_list)
        )

    # Sort by strength descending
    levels.sort(key=lambda L: (-L.strength, L.price))
    return levels


# ---------------------------------------------------------------------------
# 2. K-Means on extrema
# ---------------------------------------------------------------------------
def detect_kmeans_levels(
    df: pd.DataFrame,
    n_clusters: int = 8,
    prominence_pct: float = 1.0,
    distance: int = 4,
) -> List[Level]:
    """Cluster significant highs and lows with K-Means."""
    highs = df["High"].values
    lows = df["Low"].values
    atr_proxy = np.mean(highs - lows)
    prom = atr_proxy * (prominence_pct / 100)

    peak_idx, _ = find_peaks(highs, distance=distance, prominence=prom)
    valley_idx, _ = find_peaks(-lows, distance=distance, prominence=prom)

    points = np.concatenate([highs[peak_idx], lows[valley_idx]]).reshape(-1, 1)
    if len(points) < n_clusters:
        n_clusters = max(2, len(points) // 2)

    if len(points) < 2:
        return []

    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = km.fit_predict(points)
    centers = km.cluster_centers_.flatten()

    # Determine kind by majority of members (high vs low)
    levels = []
    for i, c in enumerate(centers):
        member_prices = points[labels == i].flatten()
        # crude: if average of members is closer to recent highs → resistance
        strength = len(member_prices)
        # Simple heuristic: levels above current close are resistance, below support
        last_close = df["Close"].iloc[-1]
        kind = "resistance" if c > last_close else "support"
        levels.append(Level(price=float(c), kind=kind, strength=strength, method="kmeans"))

    levels.sort(key=lambda L: (-L.strength, L.price))
    return levels


# ---------------------------------------------------------------------------
# 3. Fibonacci Retracement
# ---------------------------------------------------------------------------
def detect_fibonacci_levels(
    df: pd.DataFrame,
    lookback: int = 120,
    ratios: Optional[List[float]] = None,
) -> List[Level]:
    """
    Compute Fibonacci retracement levels from the most significant swing
    in the last `lookback` bars.
    """
    if ratios is None:
        ratios = [0.236, 0.382, 0.5, 0.618, 0.786]

    window = df.iloc[-lookback:] if len(df) > lookback else df
    swing_high = window["High"].max()
    swing_low = window["Low"].min()
    high_idx = window["High"].idxmax()
    low_idx = window["Low"].idxmin()

    # Direction: if high occurred after low → up-move, retrace from high
    if high_idx > low_idx:
        # Retracement of an up-move → levels between high and low
        diff = swing_high - swing_low
        levels = []
        for r in ratios:
            price = swing_high - diff * r
            levels.append(
                Level(
                    price=float(price),
                    kind="support" if price < df["Close"].iloc[-1] else "resistance",
                    strength=1,
                    method=f"fib_{r}",
                )
            )
        # Also add the swing extremes
        levels.append(Level(price=float(swing_high), kind="resistance", strength=3, method="fib_swing_high"))
        levels.append(Level(price=float(swing_low), kind="support", strength=3, method="fib_swing_low"))
    else:
        # Retracement of a down-move
        diff = swing_high - swing_low
        levels = []
        for r in ratios:
            price = swing_low + diff * r
            levels.append(
                Level(
                    price=float(price),
                    kind="resistance" if price > df["Close"].iloc[-1] else "support",
                    strength=1,
                    method=f"fib_{r}",
                )
            )
        levels.append(Level(price=float(swing_high), kind="resistance", strength=3, method="fib_swing_high"))
        levels.append(Level(price=float(swing_low), kind="support", strength=3, method="fib_swing_low"))

    return levels


# ---------------------------------------------------------------------------
# 4. Classic Pivot Points (from previous period)
# ---------------------------------------------------------------------------
def detect_pivot_levels(df: pd.DataFrame, period: str = "daily") -> List[Level]:
    """
    Classic pivot points.
    period='daily' uses previous day; 'weekly' uses previous week.
    """
    if period == "weekly":
        # Resample to week
        weekly = df.resample("W").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
        if len(weekly) < 2:
            return []
        prev = weekly.iloc[-2]
    else:
        if len(df) < 2:
            return []
        prev = df.iloc[-2]

    high, low, close = prev["High"], prev["Low"], prev["Close"]
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)

    levels = [
        Level(price=float(pp), kind="both", strength=2, method="pivot_pp"),
        Level(price=float(r1), kind="resistance", strength=2, method="pivot_r1"),
        Level(price=float(s1), kind="support", strength=2, method="pivot_s1"),
        Level(price=float(r2), kind="resistance", strength=1, method="pivot_r2"),
        Level(price=float(s2), kind="support", strength=1, method="pivot_s2"),
        Level(price=float(r3), kind="resistance", strength=1, method="pivot_r3"),
        Level(price=float(s3), kind="support", strength=1, method="pivot_s3"),
    ]
    return levels


# ---------------------------------------------------------------------------
# Convenience: run selected methods and merge
# ---------------------------------------------------------------------------
def analyze_levels(
    df: pd.DataFrame,
    methods: Optional[List[str]] = None,
    **kwargs,
) -> List[Level]:
    """
    Run one or more detectors and return a combined, de-duplicated list.
    """
    if methods is None:
        methods = ["swing", "fib", "kmeans", "pivot"]

    all_levels: List[Level] = []

    if "swing" in methods:
        all_levels.extend(detect_swing_levels(df, **{k: v for k, v in kwargs.items() if k in ("prominence_pct", "distance", "tolerance_pct", "min_strength")}))
    if "kmeans" in methods:
        all_levels.extend(detect_kmeans_levels(df, **{k: v for k, v in kwargs.items() if k in ("n_clusters", "prominence_pct", "distance")}))
    if "fib" in methods:
        all_levels.extend(detect_fibonacci_levels(df, **{k: v for k, v in kwargs.items() if k in ("lookback", "ratios")}))
    if "pivot" in methods:
        all_levels.extend(detect_pivot_levels(df, period=kwargs.get("pivot_period", "daily")))

    # Simple de-duplication: merge levels within 0.8 % of each other, keep higher strength
    all_levels.sort(key=lambda L: L.price)
    merged: List[Level] = []
    for lvl in all_levels:
        if not merged:
            merged.append(lvl)
            continue
        last = merged[-1]
        if abs(lvl.price - last.price) / last.price * 100 < 0.8:
            # keep the stronger one, or combine
            if lvl.strength > last.strength:
                merged[-1] = lvl
            else:
                last.strength = max(last.strength, lvl.strength)
        else:
            merged.append(lvl)

    # Final sort by strength
    merged.sort(key=lambda L: (-L.strength, L.price))
    return merged


def filter_nearby(
    levels: List[Level],
    current_price: float,
    max_distance_pct: float = 25.0,
) -> List[Level]:
    """Keep only levels reasonably close to current price (useful for display)."""
    return [
        L
        for L in levels
        if abs(L.price - current_price) / current_price * 100 <= max_distance_pct
    ]

# ---------------------------------------------------------------------------
# Weekly levels
# ---------------------------------------------------------------------------
def detect_weekly_levels(
    df: pd.DataFrame,
    methods: Optional[List[str]] = None,
    **kwargs,
) -> List[Level]:
    """
    Resample daily data to weekly OHLC and run the same detectors.
    Weekly levels are higher-timeframe and generally more significant.
    """
    if len(df) < 40:
        return []

    weekly = (
        df.resample("W")
        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        .dropna()
    )
    if len(weekly) < 15:
        return []

    levels = analyze_levels(weekly, methods=methods or ["swing", "kmeans", "fib"], **kwargs)
    for L in levels:
        L.timeframe = "weekly"
        L.strength = max(L.strength, L.strength + 2)  # boost weekly
        L.method = f"weekly_{L.method}"
    return levels


# ---------------------------------------------------------------------------
# Multi-timeframe confluence
# ---------------------------------------------------------------------------
def find_confluence(
    daily_levels: List[Level],
    weekly_levels: List[Level],
    tolerance_pct: float = 1.5,
) -> List[Level]:
    """
    Levels that appear on both daily and weekly (within tolerance)
    receive a large strength boost and are marked as confluence.
    """
    conf: List[Level] = []
    used_weekly = set()

    for d in daily_levels:
        for i, w in enumerate(weekly_levels):
            if i in used_weekly:
                continue
            if abs(d.price - w.price) / max(d.price, 1e-9) * 100 <= tolerance_pct:
                avg_price = (d.price + w.price) / 2
                combined = Level(
                    price=avg_price,
                    kind=d.kind if d.kind == w.kind else "both",
                    strength=d.strength + w.strength + 5,
                    method=f"confluence({d.method}+{w.method})",
                    timeframe="confluence",
                    score=min(100.0, (d.strength + w.strength) * 8),
                )
                conf.append(combined)
                used_weekly.add(i)
                break

    conf.sort(key=lambda L: -L.strength)
    return conf


def enrich_with_volume_profile(
    df: pd.DataFrame,
    levels: List[Level],
    bins: int = 40,
) -> List[Level]:
    """Add volume-profile derived levels and boost existing levels near high-volume nodes."""
    from .volume_profile import compute_volume_profile, profile_to_levels

    try:
        vp = compute_volume_profile(df, bins=bins)
        vp_levels = profile_to_levels(vp, top_n=6)
        for L in levels:
            for node in vp.nodes[:8]:
                if abs(L.price - node.price) / max(L.price, 1e-9) * 100 < 1.2:
                    L.strength += max(1, int(node.pct_of_total * 20))
                    L.method += "+vp"
                    break
        levels.extend(vp_levels)
    except Exception as e:
        print(f"[volume profile warning] {e}")
    return levels
