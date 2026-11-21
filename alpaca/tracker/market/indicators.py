"""Moving averages, session VWAP and signal logic."""

import pandas as pd

from .config import PERIODS, EASTERN


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    # Moving averages
    for period in PERIODS:
        df[f"SMA_{period}"] = (
            df["close"].rolling(window=period, min_periods=period).mean()
        )
        df[f"EMA_{period}"] = (
            df["close"].ewm(span=period, adjust=False, min_periods=period).mean()
        )

    # Session VWAP (resets each calendar day in US/Eastern)
    eastern_ts = df["timestamp"].dt.tz_convert(EASTERN)
    df["_session_date"] = eastern_ts.dt.date

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0

    df["_cum_vol"] = df.groupby("_session_date")["volume"].cumsum()
    df["_cum_tp_vol"] = (
        (typical_price * df["volume"]).groupby(df["_session_date"]).cumsum()
    )

    df["VWAP"] = df["_cum_tp_vol"] / df["_cum_vol"]

    df = df.drop(columns=["_session_date", "_cum_vol", "_cum_tp_vol"])
    return df


def calculate_signal(df: pd.DataFrame) -> dict:
    """
    Simple bullish / neutral / bearish signal.

    Components:
        1. Price vs. session VWAP
        2. EMA 5 vs. EMA 10
        3. EMA 10 vs. EMA 30

    Score:
        +3 to +2  -> BULLISH
        +1 to -1  -> NEUTRAL
        -2 to -3  -> BEARISH
    """
    n = len(df)
    if df.empty:
        return {
            "signal": "NO DATA",
            "score": None,
            "price_vs_vwap": None,
            "price_vs_vwap_pct": None,
            "ema_alignment": None,
            "crossover": None,
            "warmup": True,
            "bars": 0,
            "needed": 30,
        }

    latest = df.iloc[-1]
    previous = df.iloc[-2] if n >= 2 else latest

    price = latest["close"]
    vwap = latest.get("VWAP")

    ema5 = latest.get("EMA_5")
    ema10 = latest.get("EMA_10")
    ema30 = latest.get("EMA_30")

    score = 0
    price_vs_vwap = "N/A"
    price_vwap_pct = None
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

    # 2. EMA Alignment
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

    return {
        "signal": signal,
        "score": score,
        "price_vs_vwap": price_vs_vwap,
        "price_vs_vwap_pct": price_vwap_pct,
        "ema_alignment": ema_alignment,
        "crossover": crossover,
        "warmup": warmup,
        "bars": n,
        "needed": 30,
    }
