"""Back-test how price historically reacted to detected support/resistance levels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .detectors import Level


@dataclass
class ReactionEvent:
    level_price: float
    kind: str
    touch_time: pd.Timestamp
    direction: str  # "bounce" | "break"
    bounce_pct: float  # max favorable move after touch (within horizon)
    bars_to_extreme: int
    volume_on_touch: float


@dataclass
class LevelStats:
    level: Level
    n_touches: int = 0
    n_bounces: int = 0
    n_breaks: int = 0
    avg_bounce_pct: float = 0.0
    max_bounce_pct: float = 0.0
    win_rate: float = 0.0  # bounces / touches
    events: List[ReactionEvent] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Composite strength score 0-100."""
        if self.n_touches == 0:
            return 0.0
        # weight: win rate 40%, number of touches 30%, avg bounce 30%
        touch_score = min(self.n_touches / 8.0, 1.0) * 30
        win_score = self.win_rate * 40
        bounce_score = min(self.avg_bounce_pct / 5.0, 1.0) * 30
        return round(touch_score + win_score + bounce_score, 1)


def _find_touches(
    df: pd.DataFrame,
    level_price: float,
    tolerance_pct: float = 0.8,
) -> List[int]:
    """Return bar indices where price came within tolerance of the level."""
    tol = level_price * (tolerance_pct / 100.0)
    touches = []
    for i in range(len(df)):
        low, high = df["Low"].iloc[i], df["High"].iloc[i]
        if low - tol <= level_price <= high + tol:
            touches.append(i)
    return touches


def evaluate_level(
    df: pd.DataFrame,
    level: Level,
    tolerance_pct: float = 0.8,
    horizon: int = 10,
    min_bounce_pct: float = 1.0,
) -> LevelStats:
    """
    For a given level, find historical touches and measure subsequent reaction.
    """
    stats = LevelStats(level=level)
    idxs = _find_touches(df, level.price, tolerance_pct)

    # de-duplicate closely spaced touches (keep first of a cluster)
    filtered = []
    last = -999
    for i in idxs:
        if i - last > 3:  # at least 3 bars apart
            filtered.append(i)
            last = i

    bounce_pcts = []
    for i in filtered:
        if i + 1 >= len(df):
            continue
        touch_bar = df.iloc[i]
        future = df.iloc[i + 1 : i + 1 + horizon]
        if future.empty:
            continue

        vol = float(touch_bar["Volume"])
        touch_time = df.index[i]

        if level.kind in ("support", "both"):
            # expect bounce up
            max_high = future["High"].max()
            bounce = (max_high - level.price) / level.price * 100
            # also check if it broke down
            min_low = future["Low"].min()
            broke = min_low < level.price * (1 - tolerance_pct / 100)
            direction = "break" if broke and bounce < min_bounce_pct else "bounce"
            try:
                delta = future["High"].idxmax() - touch_time
                bars_to = int(delta.days) if hasattr(delta, "days") else horizon
            except Exception:
                bars_to = horizon
        else:
            # resistance → expect bounce down
            min_low = future["Low"].min()
            bounce = (level.price - min_low) / level.price * 100
            max_high = future["High"].max()
            broke = max_high > level.price * (1 + tolerance_pct / 100)
            direction = "break" if broke and bounce < min_bounce_pct else "bounce"
            bars_to = horizon

        event = ReactionEvent(
            level_price=level.price,
            kind=level.kind,
            touch_time=touch_time,
            direction=direction,
            bounce_pct=float(bounce),
            bars_to_extreme=bars_to,
            volume_on_touch=vol,
        )
        stats.events.append(event)
        stats.n_touches += 1
        if direction == "bounce":
            stats.n_bounces += 1
            bounce_pcts.append(bounce)
        else:
            stats.n_breaks += 1

    if stats.n_touches > 0:
        stats.win_rate = stats.n_bounces / stats.n_touches
        if bounce_pcts:
            stats.avg_bounce_pct = float(np.mean(bounce_pcts))
            stats.max_bounce_pct = float(np.max(bounce_pcts))

    return stats


def backtest_levels(
    df: pd.DataFrame,
    levels: List[Level],
    tolerance_pct: float = 0.8,
    horizon: int = 10,
) -> List[LevelStats]:
    """Evaluate a list of levels and return ranked stats."""
    results = []
    for lvl in levels:
        stats = evaluate_level(df, lvl, tolerance_pct=tolerance_pct, horizon=horizon)
        results.append(stats)
    # sort by composite score
    results.sort(key=lambda s: -s.score)
    return results


def print_backtest_report(stats_list: List[LevelStats], top_n: int = 12) -> None:
    print(f"\n{'='*80}")
    print(f"{'BACKTEST – Level Reaction Statistics':^80}")
    print(f"{'='*80}")
    print(f"{'Price':>9} {'Kind':<10} {'Touches':>7} {'Bounces':>7} {'Win%':>6} {'AvgBounce':>9} {'Score':>6}")
    print(f"{'-'*80}")
    for s in stats_list[:top_n]:
        print(
            f"{s.level.price:9.2f} {s.level.kind:<10} {s.n_touches:7d} {s.n_bounces:7d} "
            f"{s.win_rate*100:5.1f}% {s.avg_bounce_pct:8.2f}% {s.score:6.1f}"
        )
    print(f"{'='*80}\n")