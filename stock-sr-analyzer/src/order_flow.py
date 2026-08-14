"""
Order-flow proxies from OHLCV data.

True order flow needs tick/bid-ask data. With daily (or intraday) OHLCV we approximate:

- Up/Down volume split (close vs open, or close vs prior close)
- Volume Delta per bar
- Cumulative Volume Delta (CVD)
- Delta divergence vs price
- Absorption-style prints (large volume, small range)
- Imbalance at swing highs/lows
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd


@dataclass
class OrderFlowSignal:
    kind: str          # "delta_div_bearish" | "delta_div_bullish" | "absorption" | "imbalance" | "cvd_trend"
    severity: str      # "watch" | "action"
    message: str
    bar_time: Optional[pd.Timestamp] = None
    value: float = 0.0
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


def _split_volume(df: pd.DataFrame, method: str = "close_open") -> pd.DataFrame:
    """
    Approximate buy vs sell volume.

    method='close_open':  close > open → all volume counted as up (buy pressure proxy)
    method='close_prev':  close > prior close → up volume
    """
    out = df.copy()
    vol = out["Volume"].astype(float)

    if method == "close_prev":
        up = out["Close"] > out["Close"].shift(1)
        dn = out["Close"] < out["Close"].shift(1)
    else:
        up = out["Close"] > out["Open"]
        dn = out["Close"] < out["Open"]

    out["up_vol"] = np.where(up, vol, np.where(~up & ~dn, vol * 0.5, 0.0))
    out["dn_vol"] = np.where(dn, vol, np.where(~up & ~dn, vol * 0.5, 0.0))
    out["delta"] = out["up_vol"] - out["dn_vol"]
    out["cvd"] = out["delta"].cumsum()
    return out


def compute_order_flow(df: pd.DataFrame, method: str = "close_open") -> pd.DataFrame:
    """Return df with up_vol, dn_vol, delta, cvd columns."""
    return _split_volume(df, method=method)


def detect_delta_divergence(
    df: pd.DataFrame,
    lookback: int = 20,
    method: str = "close_open",
) -> List[OrderFlowSignal]:
    """
    Price vs Cumulative Volume Delta divergence.

    Bearish: price higher high, CVD lower high (or flat)
    Bullish: price lower low, CVD higher low (or flat)
    """
    if len(df) < lookback + 5:
        return []

    of = compute_order_flow(df, method=method)
    recent = of.iloc[-lookback:]
    prior = of.iloc[-2 * lookback : -lookback] if len(of) >= 2 * lookback else of.iloc[:-lookback]

    signals: List[OrderFlowSignal] = []

    recent_high = float(recent["High"].max())
    recent_low = float(recent["Low"].min())
    prior_high = float(prior["High"].max()) if len(prior) else recent_high
    prior_low = float(prior["Low"].min()) if len(prior) else recent_low

    cvd_recent_max = float(recent["cvd"].max())
    cvd_recent_min = float(recent["cvd"].min())
    cvd_prior_max = float(prior["cvd"].max()) if len(prior) else cvd_recent_max
    cvd_prior_min = float(prior["cvd"].min()) if len(prior) else cvd_recent_min

    price_hh = recent_high > prior_high * 1.005
    price_ll = recent_low < prior_low * 0.995
    cvd_lh = cvd_recent_max < cvd_prior_max * 0.98   # lower high in CVD
    cvd_hl = cvd_recent_min > cvd_prior_min * 1.02   # higher low in CVD
    cvd_flat_high = abs(cvd_recent_max - cvd_prior_max) / (abs(cvd_prior_max) + 1e-9) < 0.02
    cvd_flat_low = abs(cvd_recent_min - cvd_prior_min) / (abs(cvd_prior_min) + 1e-9) < 0.02

    if price_hh and (cvd_lh or cvd_flat_high):
        signals.append(
            OrderFlowSignal(
                kind="delta_div_bearish",
                severity="action" if cvd_lh else "watch",
                message=(
                    f"Bearish delta divergence: price HH {recent_high:.2f} "
                    f"but CVD {'lower high' if cvd_lh else 'flat'} "
                    f"(CVD max {cvd_prior_max:.0f} → {cvd_recent_max:.0f})"
                ),
                value=cvd_recent_max - cvd_prior_max,
                details={
                    "price_high": recent_high,
                    "cvd_prior_max": cvd_prior_max,
                    "cvd_recent_max": cvd_recent_max,
                },
            )
        )

    if price_ll and (cvd_hl or cvd_flat_low):
        signals.append(
            OrderFlowSignal(
                kind="delta_div_bullish",
                severity="action" if cvd_hl else "watch",
                message=(
                    f"Bullish delta divergence: price LL {recent_low:.2f} "
                    f"but CVD {'higher low' if cvd_hl else 'flat'} "
                    f"(CVD min {cvd_prior_min:.0f} → {cvd_recent_min:.0f})"
                ),
                value=cvd_recent_min - cvd_prior_min,
                details={
                    "price_low": recent_low,
                    "cvd_prior_min": cvd_prior_min,
                    "cvd_recent_min": cvd_recent_min,
                },
            )
        )

    return signals


def detect_absorption(
    df: pd.DataFrame,
    lookback: int = 30,
    vol_mult: float = 1.8,
    range_pct_max: float = 1.2,
    method: str = "close_open",
) -> List[OrderFlowSignal]:
    """
    Absorption proxy: unusually high volume with a small price range
    (large participation, little net movement → possible absorption).
    """
    if len(df) < lookback:
        return []

    of = compute_order_flow(df, method=method)
    recent = of.iloc[-lookback:]
    avg_vol = float(recent["Volume"].mean())
    signals = []

    for ts, row in recent.iterrows():
        rng = float(row["High"] - row["Low"])
        mid = (float(row["High"]) + float(row["Low"])) / 2 or 1.0
        range_pct = (rng / mid) * 100
        vol = float(row["Volume"])

        if vol >= avg_vol * vol_mult and range_pct <= range_pct_max:
            side = "bid absorption (selling absorbed)" if row["delta"] < 0 else "ask absorption (buying absorbed)"
            if abs(row["delta"]) < vol * 0.15:
                side = "two-sided absorption (balanced)"
            signals.append(
                OrderFlowSignal(
                    kind="absorption",
                    severity="watch",
                    message=(
                        f"Absorption-style bar @ {ts.date() if hasattr(ts, 'date') else ts}: "
                        f"vol={vol:.0f} ({vol/avg_vol:.1f}x avg), range={range_pct:.2f}% – {side}"
                    ),
                    bar_time=ts if isinstance(ts, pd.Timestamp) else None,
                    value=vol,
                    details={"range_pct": range_pct, "delta": float(row["delta"])},
                )
            )

    # Keep only the most recent few
    return signals[-5:]


def detect_swing_imbalance(
    df: pd.DataFrame,
    lookback: int = 40,
    method: str = "close_open",
) -> List[OrderFlowSignal]:
    """
    At the most recent swing high/low, check whether delta confirmed the move.
    Weak delta at a new high/low = imbalance warning.
    """
    if len(df) < lookback:
        return []

    of = compute_order_flow(df, method=method)
    recent = of.iloc[-lookback:]
    signals = []

    hi_idx = recent["High"].idxmax()
    lo_idx = recent["Low"].idxmin()

    # Average |delta| for context
    avg_abs_delta = float(recent["delta"].abs().mean()) + 1e-9

    row_hi = of.loc[hi_idx]
    row_lo = of.loc[lo_idx]

    # At swing high: expect positive delta; weak/negative = bearish imbalance
    if float(row_hi["delta"]) < avg_abs_delta * 0.3:
        signals.append(
            OrderFlowSignal(
                kind="imbalance",
                severity="watch",
                message=(
                    f"Weak/negative delta at swing high {float(row_hi['High']):.2f} "
                    f"(delta={float(row_hi['delta']):.0f} vs avg |delta|={avg_abs_delta:.0f})"
                ),
                bar_time=hi_idx if isinstance(hi_idx, pd.Timestamp) else None,
                value=float(row_hi["delta"]),
            )
        )

    # At swing low: expect negative delta; weak/positive = bullish imbalance
    if float(row_lo["delta"]) > -avg_abs_delta * 0.3:
        signals.append(
            OrderFlowSignal(
                kind="imbalance",
                severity="watch",
                message=(
                    f"Weak/positive delta at swing low {float(row_lo['Low']):.2f} "
                    f"(delta={float(row_lo['delta']):.0f} vs avg |delta|={avg_abs_delta:.0f})"
                ),
                bar_time=lo_idx if isinstance(lo_idx, pd.Timestamp) else None,
                value=float(row_lo["delta"]),
            )
        )

    return signals




def detect_stacked_imbalance(
    df: pd.DataFrame,
    lookback: int = 15,
    delta_ratio: float = 0.55,
    min_bars: int = 3,
    method: str = "close_open",
) -> List[OrderFlowSignal]:
    """
    Stacked imbalance proxy: consecutive bars where |delta|/volume is high
    and delta keeps the same sign (persistent one-sided pressure).
    """
    if len(df) < lookback:
        return []
    of = compute_order_flow(df, method=method)
    recent = of.iloc[-lookback:].copy()
    recent["imbalance_ratio"] = recent["delta"].abs() / recent["Volume"].replace(0, np.nan)
    signals = []

    # Find runs of same-sign strong delta
    signs = np.sign(recent["delta"].values)
    ratios = recent["imbalance_ratio"].values
    times = recent.index.tolist()

    run_sign = 0
    run_len = 0
    run_start = 0
    for i in range(len(signs)):
        strong = ratios[i] >= delta_ratio if not np.isnan(ratios[i]) else False
        if strong and signs[i] == run_sign and run_sign != 0:
            run_len += 1
        elif strong and signs[i] != 0:
            if run_len >= min_bars:
                direction = "buy" if run_sign > 0 else "sell"
                signals.append(
                    OrderFlowSignal(
                        kind="stacked_imbalance",
                        severity="action" if run_len >= min_bars + 1 else "watch",
                        message=(
                            f"Stacked {direction} imbalance: {run_len} consecutive bars "
                            f"with |delta|/vol ≥ {delta_ratio:.0%} ending near {times[i-1]}"
                        ),
                        bar_time=times[i - 1] if isinstance(times[i - 1], pd.Timestamp) else None,
                        value=float(run_len),
                        details={"direction": direction, "bars": run_len},
                    )
                )
            run_sign = signs[i]
            run_len = 1
            run_start = i
        else:
            if run_len >= min_bars:
                direction = "buy" if run_sign > 0 else "sell"
                signals.append(
                    OrderFlowSignal(
                        kind="stacked_imbalance",
                        severity="action" if run_len >= min_bars + 1 else "watch",
                        message=(
                            f"Stacked {direction} imbalance: {run_len} consecutive bars "
                            f"with |delta|/vol ≥ {delta_ratio:.0%}"
                        ),
                        value=float(run_len),
                        details={"direction": direction, "bars": run_len},
                    )
                )
            run_sign = 0
            run_len = 0

    if run_len >= min_bars:
        direction = "buy" if run_sign > 0 else "sell"
        signals.append(
            OrderFlowSignal(
                kind="stacked_imbalance",
                severity="action" if run_len >= min_bars + 1 else "watch",
                message=(
                    f"Stacked {direction} imbalance: {run_len} consecutive bars "
                    f"with |delta|/vol ≥ {delta_ratio:.0%} (ongoing)"
                ),
                value=float(run_len),
                details={"direction": direction, "bars": run_len},
            )
        )
    return signals[-3:]  # most recent only


def imbalance_summary(df: pd.DataFrame, lookback: int = 20, method: str = "close_open") -> dict:
    """Numeric summary of recent order-flow imbalance for display."""
    of = compute_order_flow(df, method=method)
    recent = of.iloc[-lookback:]
    total_up = float(recent["up_vol"].sum())
    total_dn = float(recent["dn_vol"].sum())
    total = total_up + total_dn + 1e-9
    last_delta = float(of["delta"].iloc[-1])
    last_cvd = float(of["cvd"].iloc[-1])
    cvd_change = float(of["cvd"].iloc[-1] - of["cvd"].iloc[-min(lookback, len(of))])
    return {
        "lookback": lookback,
        "up_vol_share": total_up / total,
        "dn_vol_share": total_dn / total,
        "net_delta": total_up - total_dn,
        "last_bar_delta": last_delta,
        "cvd": last_cvd,
        "cvd_change": cvd_change,
        "pressure": "buy" if (total_up - total_dn) > 0 else "sell",
    }

def analyze_order_flow(
    df: pd.DataFrame,
    lookback: int = 25,
    method: str = "close_open",
) -> List[OrderFlowSignal]:
    """Run all order-flow proxy detectors and return combined signals."""
    signals: List[OrderFlowSignal] = []
    signals.extend(detect_delta_divergence(df, lookback=lookback, method=method))
    signals.extend(detect_absorption(df, lookback=max(lookback, 30), method=method))
    signals.extend(detect_swing_imbalance(df, lookback=max(lookback, 40), method=method))
    signals.extend(detect_stacked_imbalance(df, lookback=max(lookback, 15), method=method))
    # Sort action first
    signals.sort(key=lambda s: (0 if s.severity == "action" else 1))
    return signals


def print_order_flow_signals(signals: List[OrderFlowSignal]) -> None:
    if not signals:
        print("  No order-flow proxy signals detected.")
        return
    print(f"\n{'='*90}")
    print(f"{'ORDER FLOW PROXIES (from OHLCV)':^90}")
    print(f"{'='*90}")
    for s in signals:
        tag = "ACTION" if s.severity == "action" else "WATCH "
        print(f"[{tag}] {s.kind:20} | {s.message}")
    print(f"{'='*90}\n")
