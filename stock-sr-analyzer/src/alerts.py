"""Multi-timeframe proximity and reaction alerts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .detectors import Level
from .atr_utils import compute_atr, distance_in_atr, atr_zone_width


@dataclass
class Alert:
    ticker: str
    timestamp: str
    severity: str  # "info" | "watch" | "action"
    timeframe: str
    message: str
    level_price: float
    current_price: float
    distance_atr: float
    kind: str
    score: float = 0.0

    def __str__(self) -> str:
        return (
            f"[{self.severity.upper():6}] {self.ticker} {self.timeframe:11} | "
            f"{self.message} | px={self.current_price:.2f} lvl={self.level_price:.2f} "
            f"({self.distance_atr:+.2f} ATR) score={self.score:.0f}"
        )


def generate_alerts(
    ticker: str,
    df: pd.DataFrame,
    levels: List[Level],
    atr_period: int = 14,
    proximity_atr: float = 1.0,
    strong_score_threshold: float = 60.0,
    lookback_bars: int = 3,
) -> List[Alert]:
    """
    Produce multi-timeframe alerts:

    - Proximity: price within `proximity_atr` ATRs of a level
    - Touch / bounce / break in the last few bars
    - Prioritise confluence / weekly / high-score levels
    """
    if df.empty or not levels:
        return []

    atr = compute_atr(df, atr_period)
    last_atr = float(atr.iloc[-1]) if not atr.empty else 1.0
    current = float(df["Close"].iloc[-1])
    recent = df.iloc[-lookback_bars:]
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    alerts: List[Alert] = []

    # Rank levels: confluence > weekly > high score
    ranked = sorted(
        levels,
        key=lambda L: (
            0 if L.timeframe == "confluence" else 1 if L.timeframe == "weekly" else 2,
            -L.score if L.score else -L.strength,
        ),
    )

    for L in ranked[:25]:  # limit noise
        dist = distance_in_atr(current, L.price, last_atr)
        abs_dist = abs(dist)

        # --- Proximity alert ---
        if abs_dist <= proximity_atr:
            severity = "action" if (L.score >= strong_score_threshold or L.timeframe == "confluence") else "watch"
            side = "above" if dist > 0 else "below"
            msg = (
                f"Price is {abs_dist:.2f} ATR {side} {L.kind} "
                f"({L.timeframe}, str={L.strength})"
            )
            alerts.append(
                Alert(
                    ticker=ticker,
                    timestamp=now_str,
                    severity=severity,
                    timeframe=L.timeframe,
                    message=msg,
                    level_price=L.price,
                    current_price=current,
                    distance_atr=dist,
                    kind=L.kind,
                    score=L.score or float(L.strength),
                )
            )

        # --- Recent touch / break detection ---
        half_zone = atr_zone_width(last_atr, 0.6)
        touched = False
        broke = False
        for _, row in recent.iterrows():
            low, high = float(row["Low"]), float(row["High"])
            if low - half_zone <= L.price <= high + half_zone:
                touched = True
            if L.kind in ("support", "both") and low < L.price - half_zone:
                broke = True
            if L.kind in ("resistance", "both") and high > L.price + half_zone:
                broke = True

        if touched and not broke:
            alerts.append(
                Alert(
                    ticker=ticker,
                    timestamp=now_str,
                    severity="watch",
                    timeframe=L.timeframe,
                    message=f"Recent touch of {L.kind} – watching for bounce",
                    level_price=L.price,
                    current_price=current,
                    distance_atr=dist,
                    kind=L.kind,
                    score=L.score or float(L.strength),
                )
            )
        elif broke:
            alerts.append(
                Alert(
                    ticker=ticker,
                    timestamp=now_str,
                    severity="action",
                    timeframe=L.timeframe,
                    message=f"Potential BREAK of {L.kind} ({L.timeframe})",
                    level_price=L.price,
                    current_price=current,
                    distance_atr=dist,
                    kind=L.kind,
                    score=L.score or float(L.strength),
                )
            )

    # Deduplicate similar messages
    seen = set()
    unique = []
    for a in alerts:
        key = (a.level_price, a.message[:40])
        if key not in seen:
            seen.add(key)
            unique.append(a)

    # Sort: action first, then by |distance|
    unique.sort(key=lambda a: (0 if a.severity == "action" else 1 if a.severity == "watch" else 2, abs(a.distance_atr)))
    return unique


def print_alerts(alerts: List[Alert]) -> None:
    if not alerts:
        print("  No proximity / reaction alerts at this time.")
        return
    print(f"\n{'='*90}")
    print(f"{'MULTI-TIMEFRAME ALERTS':^90}")
    print(f"{'='*90}")
    for a in alerts:
        print(str(a))
    print(f"{'='*90}\n")


def save_alerts(alerts: List[Alert], path: Path) -> None:
    lines = [str(a) for a in alerts]
    path.write_text("\n".join(lines) + "\n" if lines else "No alerts\n")
    print(f"Alerts saved → {path}")
