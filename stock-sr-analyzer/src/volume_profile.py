"""Volume Profile and VWAP utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .detectors import Level


@dataclass
class VolumeNode:
    price: float
    volume: float
    pct_of_total: float


@dataclass
class VolumeProfileResult:
    nodes: List[VolumeNode]
    poc: float  # Point of Control (highest volume price)
    vah: float  # Value Area High (~70% volume)
    val: float  # Value Area Low
    total_volume: float


def compute_volume_profile(
    df: pd.DataFrame,
    bins: int = 50,
    value_area_pct: float = 0.70,
) -> VolumeProfileResult:
    """
    Approximate volume profile by distributing each bar's volume
    across the High-Low range (uniform assumption) into price bins.
    """
    if df.empty or "Volume" not in df.columns:
        raise ValueError("DataFrame must contain Volume")

    price_min = df["Low"].min()
    price_max = df["High"].max()
    if price_max <= price_min:
        price_max = price_min + 1e-6

    bin_edges = np.linspace(price_min, price_max, bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    vol_per_bin = np.zeros(bins)

    for _, row in df.iterrows():
        low, high, vol = row["Low"], row["High"], row["Volume"]
        if high <= low or vol <= 0:
            # assign all volume to closest bin
            idx = np.clip(np.searchsorted(bin_edges, (low + high) / 2) - 1, 0, bins - 1)
            vol_per_bin[idx] += vol
            continue

        # fraction of bar range overlapping each bin
        for i in range(bins):
            b_low, b_high = bin_edges[i], bin_edges[i + 1]
            overlap = max(0.0, min(high, b_high) - max(low, b_low))
            if overlap > 0:
                vol_per_bin[i] += vol * (overlap / (high - low))

    total = vol_per_bin.sum()
    if total <= 0:
        total = 1.0

    nodes = [
        VolumeNode(price=float(c), volume=float(v), pct_of_total=float(v / total))
        for c, v in zip(bin_centers, vol_per_bin)
        if v > 0
    ]
    nodes.sort(key=lambda n: -n.volume)

    # POC
    poc_idx = int(np.argmax(vol_per_bin))
    poc = float(bin_centers[poc_idx])

    # Value Area (expand from POC until ~value_area_pct of volume is covered)
    sorted_idx = np.argsort(vol_per_bin)[::-1]
    cum = 0.0
    va_bins = set()
    for i in sorted_idx:
        cum += vol_per_bin[i]
        va_bins.add(i)
        if cum / total >= value_area_pct:
            break

    va_prices = [bin_centers[i] for i in va_bins]
    vah = float(max(va_prices)) if va_prices else poc
    val = float(min(va_prices)) if va_prices else poc

    return VolumeProfileResult(
        nodes=nodes,
        poc=poc,
        vah=vah,
        val=val,
        total_volume=float(total),
    )


def profile_to_levels(vp: VolumeProfileResult, top_n: int = 5) -> List[Level]:
    """Convert top volume nodes + POC/VA into Level objects."""
    levels = []
    # POC is strongest
    levels.append(Level(price=vp.poc, kind="both", strength=10, method="vp_poc"))
    levels.append(Level(price=vp.vah, kind="resistance", strength=6, method="vp_vah"))
    levels.append(Level(price=vp.val, kind="support", strength=6, method="vp_val"))

    for node in vp.nodes[:top_n]:
        if abs(node.price - vp.poc) / vp.poc < 0.005:
            continue  # already have POC
        kind = "resistance" if node.price > vp.poc else "support"
        strength = max(2, int(node.pct_of_total * 40))
        levels.append(Level(price=node.price, kind=kind, strength=strength, method="vp_node"))

    return levels


def compute_vwap(df: pd.DataFrame, window: Optional[int] = None) -> pd.Series:
    """
    Volume Weighted Average Price.
    If window is None → cumulative (session-style) VWAP from start of data.
    Else → rolling VWAP of `window` bars.
    """
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    if window is None:
        cum_vol = df["Volume"].cumsum()
        cum_tp_vol = (typical * df["Volume"]).cumsum()
        vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    else:
        tp_vol = typical * df["Volume"]
        vwap = tp_vol.rolling(window).sum() / df["Volume"].rolling(window).sum()
    return vwap


def anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """VWAP starting from a specific bar index (e.g. major swing)."""
    sub = df.iloc[anchor_idx:].copy()
    typical = (sub["High"] + sub["Low"] + sub["Close"]) / 3
    cum_vol = sub["Volume"].cumsum()
    cum_tp_vol = (typical * sub["Volume"]).cumsum()
    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    full = pd.Series(index=df.index, dtype=float)
    full.iloc[anchor_idx:] = vwap.values
    return full

# ---------------------------------------------------------------------------
# Volume Profile Divergence
# ---------------------------------------------------------------------------
@dataclass
class VPDivergence:
    kind: str          # "bearish_poc" | "bullish_poc" | "volume_exhaustion" | "va_rejection"
    severity: str      # "watch" | "action"
    message: str
    price: float
    poc: float
    lookback: int
    details: dict


def _rolling_poc(df: pd.DataFrame, window: int = 20, bins: int = 30) -> pd.Series:
    """Approximate rolling POC using a simple volume-weighted median of typical price."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    # Volume-weighted rolling mean as a fast POC proxy (true histogram POC is slower)
    tp_vol = typical * df["Volume"]
    roll_poc = tp_vol.rolling(window).sum() / df["Volume"].rolling(window).sum()
    return roll_poc


def detect_vp_divergence(
    df: pd.DataFrame,
    lookback: int = 20,
    bins: int = 40,
    min_move_pct: float = 3.0,
) -> List[VPDivergence]:
    """
    Detect practical volume-profile style divergences:

    1. POC migration divergence
       - Price makes a higher high while rolling POC is flat/falling → bearish
       - Price makes a lower low while rolling POC is flat/rising → bullish

    2. Volume exhaustion at extremes
       - New swing high/low on noticeably lower volume than the prior swing

    3. Value-area rejection
       - Price briefly outside VAH/VAL then closes back inside on the full profile
    """
    if len(df) < lookback + 10:
        return []

    divergences: List[VPDivergence] = []
    recent = df.iloc[-lookback:]
    prior = df.iloc[-2 * lookback : -lookback] if len(df) >= 2 * lookback else df.iloc[:-lookback]

    # --- Full-period profile for VA context ---
    try:
        vp = compute_volume_profile(df.iloc[-lookback * 2 :], bins=bins)
    except Exception:
        return []

    current_price = float(df["Close"].iloc[-1])
    roll_poc = _rolling_poc(df, window=max(10, lookback // 2))
    poc_now = float(roll_poc.iloc[-1]) if not roll_poc.empty else vp.poc
    poc_prev = float(roll_poc.iloc[-lookback]) if len(roll_poc) >= lookback else poc_now

    # Price extremes
    recent_high = float(recent["High"].max())
    recent_low = float(recent["Low"].min())
    prior_high = float(prior["High"].max()) if not prior.empty else recent_high
    prior_low = float(prior["Low"].min()) if not prior.empty else recent_low

    price_hh = recent_high > prior_high * (1 + min_move_pct / 200)  # mild new high
    price_ll = recent_low < prior_low * (1 - min_move_pct / 200)

    poc_rising = poc_now > poc_prev * 1.005
    poc_falling = poc_now < poc_prev * 0.995
    poc_flat = not poc_rising and not poc_falling

    # 1. POC migration divergence
    if price_hh and (poc_falling or poc_flat):
        divergences.append(
            VPDivergence(
                kind="bearish_poc",
                severity="action" if poc_falling else "watch",
                message=(
                    f"Bearish POC divergence: price higher high ({recent_high:.2f}) "
                    f"while POC {'falling' if poc_falling else 'flat'} "
                    f"({poc_prev:.2f} → {poc_now:.2f})"
                ),
                price=current_price,
                poc=poc_now,
                lookback=lookback,
                details={"recent_high": recent_high, "prior_high": prior_high, "poc_prev": poc_prev},
            )
        )
    if price_ll and (poc_rising or poc_flat):
        divergences.append(
            VPDivergence(
                kind="bullish_poc",
                severity="action" if poc_rising else "watch",
                message=(
                    f"Bullish POC divergence: price lower low ({recent_low:.2f}) "
                    f"while POC {'rising' if poc_rising else 'flat'} "
                    f"({poc_prev:.2f} → {poc_now:.2f})"
                ),
                price=current_price,
                poc=poc_now,
                lookback=lookback,
                details={"recent_low": recent_low, "prior_low": prior_low, "poc_prev": poc_prev},
            )
        )

    # 2. Volume exhaustion at swing extremes
    # Compare volume on the bar of the recent extreme vs average of prior extreme region
    try:
        rh_idx = recent["High"].idxmax()
        rl_idx = recent["Low"].idxmin()
        vol_at_rh = float(df.loc[rh_idx, "Volume"])
        vol_at_rl = float(df.loc[rl_idx, "Volume"])
        avg_vol = float(recent["Volume"].mean())

        if price_hh and vol_at_rh < avg_vol * 0.75:
            divergences.append(
                VPDivergence(
                    kind="volume_exhaustion",
                    severity="watch",
                    message=(
                        f"Volume exhaustion at high: new high {recent_high:.2f} "
                        f"on volume {vol_at_rh:.0f} vs avg {avg_vol:.0f} ({vol_at_rh/avg_vol:.0%})"
                    ),
                    price=current_price,
                    poc=poc_now,
                    lookback=lookback,
                    details={"vol_at_extreme": vol_at_rh, "avg_vol": avg_vol},
                )
            )
        if price_ll and vol_at_rl < avg_vol * 0.75:
            divergences.append(
                VPDivergence(
                    kind="volume_exhaustion",
                    severity="watch",
                    message=(
                        f"Volume exhaustion at low: new low {recent_low:.2f} "
                        f"on volume {vol_at_rl:.0f} vs avg {avg_vol:.0f} ({vol_at_rl/avg_vol:.0%})"
                    ),
                    price=current_price,
                    poc=poc_now,
                    lookback=lookback,
                    details={"vol_at_extreme": vol_at_rl, "avg_vol": avg_vol},
                )
            )
    except Exception:
        pass

    # 3. Value-area rejection (price poked outside then closed back inside)
    last_close = current_price
    last_high = float(df["High"].iloc[-1])
    last_low = float(df["Low"].iloc[-1])
    if last_high > vp.vah and last_close < vp.vah:
        divergences.append(
            VPDivergence(
                kind="va_rejection",
                severity="watch",
                message=f"Rejection at Value Area High ({vp.vah:.2f}) – closed back inside",
                price=current_price,
                poc=vp.poc,
                lookback=lookback,
                details={"vah": vp.vah, "val": vp.val},
            )
        )
    if last_low < vp.val and last_close > vp.val:
        divergences.append(
            VPDivergence(
                kind="va_rejection",
                severity="watch",
                message=f"Rejection at Value Area Low ({vp.val:.2f}) – closed back inside",
                price=current_price,
                poc=vp.poc,
                lookback=lookback,
                details={"vah": vp.vah, "val": vp.val},
            )
        )

    return divergences


def print_vp_divergences(divs: List[VPDivergence]) -> None:
    if not divs:
        print("  No volume-profile divergences detected.")
        return
    print(f"\n{'='*90}")
    print(f"{'VOLUME PROFILE DIVERGENCE':^90}")
    print(f"{'='*90}")
    for d in divs:
        tag = "ACTION" if d.severity == "action" else "WATCH "
        print(f"[{tag}] {d.kind:20} | {d.message}")
    print(f"{'='*90}\n")


def vwap_summary(df: pd.DataFrame) -> dict:
    """
    Compute several VWAP flavours and relationship to last price.
    Returns dict suitable for display / JSON.
    """
    if df.empty or "Volume" not in df.columns:
        return {}

    last = float(df["Close"].iloc[-1])
    cum = compute_vwap(df)  # from start of series
    roll_20 = compute_vwap(df, window=20)
    roll_50 = compute_vwap(df, window=50)

    # Anchor at most recent major swing low and swing high (last 60 bars)
    window = df.iloc[-min(60, len(df)) :]
    low_idx = window["Low"].idxmin()
    high_idx = window["High"].idxmax()
    # map to integer position
    pos_low = df.index.get_loc(low_idx)
    pos_high = df.index.get_loc(high_idx)
    if isinstance(pos_low, slice):
        pos_low = pos_low.start
    if isinstance(pos_high, slice):
        pos_high = pos_high.start

    avwap_from_low = anchored_vwap(df, int(pos_low))
    avwap_from_high = anchored_vwap(df, int(pos_high))

    def _last(s):
        if s is None or s.empty:
            return None
        v = s.dropna()
        return float(v.iloc[-1]) if len(v) else None

    out = {
        "last_price": last,
        "vwap_cumulative": _last(cum),
        "vwap_roll_20": _last(roll_20),
        "vwap_roll_50": _last(roll_50),
        "avwap_from_swing_low": _last(avwap_from_low),
        "avwap_from_swing_high": _last(avwap_from_high),
    }
    # Distances in %
    for k in list(out.keys()):
        if k == "last_price" or out[k] is None:
            continue
        out[f"dist_pct_{k}"] = (last - out[k]) / out[k] * 100
    return out


def compute_vwap_bands(
    df: pd.DataFrame,
    window: Optional[int] = None,
    std_mults: tuple = (1.0, 2.0),
) -> pd.DataFrame:
    """
    VWAP ± N standard deviations of (typical price - VWAP), volume-aware.

    If window is None → cumulative VWAP from start of data.
    Returns DataFrame with columns: vwap, upper_1, lower_1, upper_2, lower_2, ...
    """
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].astype(float).replace(0, np.nan)

    if window is None:
        cum_vol = vol.cumsum()
        cum_tp_vol = (typical * vol).cumsum()
        vwap = cum_tp_vol / cum_vol
        # rolling-ish std of deviation using expanding window
        dev = typical - vwap
        # volume-weighted variance approximation via expanding
        var = (dev ** 2 * vol).cumsum() / cum_vol
        std = np.sqrt(var)
    else:
        tp_vol = typical * vol
        vwap = tp_vol.rolling(window).sum() / vol.rolling(window).sum()
        dev = typical - vwap
        var = (dev ** 2).rolling(window).mean()
        std = np.sqrt(var)

    out = pd.DataFrame(index=df.index)
    out["vwap"] = vwap
    for m in std_mults:
        out[f"upper_{m:g}"] = vwap + m * std
        out[f"lower_{m:g}"] = vwap - m * std
    out["std"] = std
    return out


def vwap_band_position(df: pd.DataFrame, bands: pd.DataFrame) -> dict:
    """Where is last price relative to VWAP bands?"""
    if bands.empty or df.empty:
        return {}
    last = float(df["Close"].iloc[-1])
    row = bands.iloc[-1]
    vwap = float(row["vwap"]) if pd.notna(row["vwap"]) else last
    result = {
        "last": last,
        "vwap": vwap,
        "dist_pct_vwap": (last - vwap) / vwap * 100 if vwap else 0,
    }
    for col in bands.columns:
        if col.startswith("upper_") or col.startswith("lower_"):
            val = row[col]
            if pd.notna(val):
                result[col] = float(val)
                result[f"dist_pct_{col}"] = (last - float(val)) / float(val) * 100
    # Zone label
    u1 = result.get("upper_1")
    l1 = result.get("lower_1")
    u2 = result.get("upper_2")
    l2 = result.get("lower_2")
    if u2 is not None and last >= u2:
        result["zone"] = "above_upper_2"
    elif u1 is not None and last >= u1:
        result["zone"] = "between_upper_1_and_2"
    elif l1 is not None and last <= l1:
        if l2 is not None and last <= l2:
            result["zone"] = "below_lower_2"
        else:
            result["zone"] = "between_lower_1_and_2"
    else:
        result["zone"] = "inside_1_std"
    return result
