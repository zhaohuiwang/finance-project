"""
Trading-signal logic built on top of the indicator DataFrame.

Two independent calculators live here:
  - EquitySignalCalculator  – multi-factor score for individual symbols
  - VixSignalCalculator     – simple regime classification from daily VIX closes

Return values are dataclasses for type safety and clearer API contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EquitySignal:
    """Result of the equity multi-factor signal calculation."""

    signal: str
    score: Optional[int]
    price_vs_vwap: Optional[str]
    price_vs_vwap_pct: Optional[float]
    ema_alignment: Optional[str]
    crossover: Optional[str]
    warmup: bool
    bars: int
    needed: int = 30


@dataclass(frozen=True, slots=True)
class VixSignal:
    """Result of the VIX regime classification."""

    signal: str
    level: Optional[str]
    latest: Optional[float]
    change_3d_pct: Optional[float]
    vs_mean: Optional[float]
    days: int


# ---------------------------------------------------------------------------
# Calculators
# ---------------------------------------------------------------------------


class EquitySignalCalculator:
    """
    Calculate a simple bullish / neutral / bearish signal.

    Components
    ----------
    1. Price vs. session VWAP
    2. EMA 5 vs. EMA 10
    3. EMA 10 vs. EMA 30

    Score interpretation
    --------------------
    +3 to +2  -> BULLISH
    +1 to -1  -> NEUTRAL
    -2 to -3  -> BEARISH
    """

    def calculate(self, df: pd.DataFrame) -> EquitySignal:
        n = len(df)
        if df.empty:
            return EquitySignal(
                signal="NO DATA",
                score=None,
                price_vs_vwap=None,
                price_vs_vwap_pct=None,
                ema_alignment=None,
                crossover=None,
                warmup=True,
                bars=0,
            )

        latest = df.iloc[-1]
        previous = df.iloc[-2] if n >= 2 else latest

        price = latest["close"]
        vwap = latest.get("VWAP")
        ema5 = latest.get("EMA_5")
        ema10 = latest.get("EMA_10")
        ema30 = latest.get("EMA_30")

        score = 0
        price_vs_vwap = "N/A"
        price_vwap_pct: Optional[float] = None
        ema_alignment = "WARMING UP"
        crossover = "NONE"
        warmup = n < 30

        # 1. Price vs Session VWAP
        if pd.notna(vwap) and vwap != 0:
            price_vwap_pct = (price - vwap) / vwap * 100.0
            if price_vwap_pct > 0.10:
                score += 1
                price_vs_vwap = "ABOVE"
            elif price_vwap_pct < -0.10:
                score -= 1
                price_vs_vwap = "BELOW"
            else:
                price_vs_vwap = "NEAR"

        # 2. EMA Alignment (only when enough history)
        if n >= 30 and pd.notna(ema5) and pd.notna(ema10) and pd.notna(ema30):
            if ema5 > ema10:
                score += 1
            elif ema5 < ema10:
                score -= 1
            if ema10 > ema30:
                score += 1
            elif ema10 < ema30:
                score -= 1

            if ema5 > ema10 > ema30:
                ema_alignment = "BULLISH"
            elif ema5 < ema10 < ema30:
                ema_alignment = "BEARISH"
            else:
                ema_alignment = "MIXED"
        elif n >= 10:
            # Degraded signal while warming up
            if pd.notna(ema5) and pd.notna(ema10):
                if ema5 > ema10:
                    score += 1
                    ema_alignment = "BULLISH (partial)"
                elif ema5 < ema10:
                    score -= 1
                    ema_alignment = "BEARISH (partial)"
                else:
                    ema_alignment = "MIXED (partial)"

        # 3. EMA Crossover
        if (
            n >= 2
            and pd.notna(previous.get("EMA_5"))
            and pd.notna(previous.get("EMA_10"))
            and pd.notna(ema5)
            and pd.notna(ema10)
        ):
            if previous["EMA_5"] <= previous["EMA_10"] and ema5 > ema10:
                crossover = "BULLISH CROSS"
            elif previous["EMA_5"] >= previous["EMA_10"] and ema5 < ema10:
                crossover = "BEARISH CROSS"

        # 4. Overall signal
        if warmup and n < 10:
            signal = f"WARMING UP ({n}/30)"
        elif score >= 2:
            signal = "BULLISH"
        elif score <= -2:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        return EquitySignal(
            signal=signal,
            score=score,
            price_vs_vwap=price_vs_vwap,
            price_vs_vwap_pct=price_vwap_pct,
            ema_alignment=ema_alignment,
            crossover=crossover,
            warmup=warmup,
            bars=n,
        )


class VixSignalCalculator:
    """Simple VIX regime from daily closes."""

    def calculate(self, daily_vix: pd.DataFrame) -> VixSignal:
        if daily_vix.empty or len(daily_vix) < 3:
            return VixSignal(
                signal="NO DATA",
                level=None,
                latest=None,
                change_3d_pct=None,
                vs_mean=None,
                days=len(daily_vix),
            )

        closes = daily_vix["close"].astype(float)
        latest = float(closes.iloc[-1])
        mean = float(closes.mean())
        change_3d = (
            (latest / float(closes.iloc[-3]) - 1.0) * 100.0
            if len(closes) >= 3
            else None
        )

        # Level classification
        if latest < 15:
            level = "LOW"
        elif latest < 25:
            level = "NORMAL"
        elif latest < 35:
            level = "ELEVATED"
        else:
            level = "HIGH"

        # Simple composite signal
        if level in ("HIGH", "ELEVATED") and change_3d is not None and change_3d > 5:
            signal = "RISING FEAR"
        elif level == "HIGH":
            signal = "HIGH VOL"
        elif level == "LOW" and change_3d is not None and change_3d < -5:
            signal = "COMPLACENCY"
        elif level == "LOW":
            signal = "LOW VOL"
        else:
            signal = "NEUTRAL VOL"

        return VixSignal(
            signal=signal,
            level=level,
            latest=latest,
            change_3d_pct=change_3d,
            vs_mean=(latest / mean - 1.0) * 100.0,
            days=len(daily_vix),
        )
