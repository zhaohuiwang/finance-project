"""Support & Resistance analysis for sector/industry ETFs.

Uses true OHLC (when available) for classic floor-trader pivots:
  - Daily pivots from prior session High / Low / Close
  - Weekly pivots from prior week High / Low / Close
Falls back to close-based approximation only if OHLC is missing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_AT_TOLERANCE = 0.005  # 0.5%


class SupportResistanceAnalyzer:
    """
    Compute pivot levels, moving averages, and S/R status for each ticker.
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        ohlc: Optional[Dict[str, pd.DataFrame]] = None,
        ma_windows: Optional[List[int]] = None,
        at_tolerance: float = DEFAULT_AT_TOLERANCE,
        meta: Optional[Dict[str, Dict]] = None,
    ):
        """
        Parameters
        ----------
        prices : DataFrame of adjusted closes (index=date, columns=tickers)
        ohlc : dict ticker -> DataFrame with at least High, Low, Close
        ma_windows : SMA periods (default 20, 50, 200)
        at_tolerance : fraction of price to count as "touching" a level
        meta : optional ticker metadata
        """
        self.prices = prices.sort_index()
        self.ohlc = ohlc or {}
        self.ma_windows = ma_windows or [20, 50, 200]
        self.at_tolerance = at_tolerance
        self.meta = meta or {}
        self._levels: Optional[pd.DataFrame] = None
        self._status: Optional[pd.DataFrame] = None

        n_true = sum(
            1
            for t, df in self.ohlc.items()
            if df is not None and not df.empty and {"High", "Low", "Close"}.issubset(set(df.columns))
        )
        logger.info(
            "S/R analyzer: %d tickers with true OHLC, %d close-only",
            n_true,
            len(self.prices.columns) - n_true,
        )

    # ------------------------------------------------------------------
    # Moving averages (on close)
    # ------------------------------------------------------------------
    def moving_averages(self) -> pd.DataFrame:
        rows = []
        latest = self.prices.iloc[-1]
        for t in self.prices.columns:
            row = {"Ticker": t, "Price": float(latest[t])}
            series = self.prices[t].dropna()
            for w in self.ma_windows:
                if len(series) >= w:
                    row[f"SMA_{w}"] = float(series.iloc[-w:].mean())
                else:
                    row[f"SMA_{w}"] = np.nan
            rows.append(row)
        return pd.DataFrame(rows).set_index("Ticker")

    # ------------------------------------------------------------------
    # True OHLC helpers
    # ------------------------------------------------------------------
    def _normalize_ohlc_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d.columns = [str(c).capitalize() for c in d.columns]
        return d

    def _prior_session_hlc(self, ticker: str) -> Optional[Dict[str, float]]:
        """
        Prior completed session High / Low / Close.

        Uses true OHLC when present. The prior bar is iloc[-2] (last completed
        day if today's bar is still forming, or previous day if market closed).
        """
        if ticker in self.ohlc and self.ohlc[ticker] is not None:
            df = self._normalize_ohlc_frame(self.ohlc[ticker]).dropna(subset=["High", "Low", "Close"])
            if len(df) >= 2:
                # Use second-to-last bar as the completed prior session
                bar = df.iloc[-2]
                return {
                    "High": float(bar["High"]),
                    "Low": float(bar["Low"]),
                    "Close": float(bar["Close"]),
                    "source": "ohlc",
                }

        # Fallback: approximate from closes
        s = self.prices[ticker].dropna()
        if len(s) < 5:
            return None
        window = s.iloc[-4:-1]
        return {
            "High": float(window.max()),
            "Low": float(window.min()),
            "Close": float(s.iloc[-2]),
            "source": "approx",
        }

    def _prior_week_hlc(self, ticker: str) -> Optional[Dict[str, float]]:
        """
        Prior completed week High / Low / Close.

        Prefer true OHLC resampled weekly; else close-based resample.
        """
        if ticker in self.ohlc and self.ohlc[ticker] is not None:
            df = self._normalize_ohlc_frame(self.ohlc[ticker])
            need = [c for c in ("High", "Low", "Close") if c in df.columns]
            if len(need) == 3:
                weekly = (
                    df[need]
                    .resample("W-FRI")
                    .agg({"High": "max", "Low": "min", "Close": "last"})
                    .dropna()
                )
                if len(weekly) >= 2:
                    prev = weekly.iloc[-2]
                    return {
                        "High": float(prev["High"]),
                        "Low": float(prev["Low"]),
                        "Close": float(prev["Close"]),
                        "source": "ohlc",
                    }

        s = self.prices[ticker].dropna()
        if len(s) < 10:
            return None
        weekly = s.resample("W-FRI").agg(["max", "min", "last"]).dropna()
        if len(weekly) < 2:
            return None
        prev = weekly.iloc[-2]
        return {
            "High": float(prev["max"]),
            "Low": float(prev["min"]),
            "Close": float(prev["last"]),
            "source": "approx",
        }

    @staticmethod
    def _classic_pivots(h: float, l: float, c: float) -> Dict[str, float]:
        """Standard floor-trader pivots."""
        p = (h + l + c) / 3.0
        r1 = 2 * p - l
        s1 = 2 * p - h
        r2 = p + (h - l)
        s2 = p - (h - l)
        r3 = h + 2 * (p - l)
        s3 = l - 2 * (h - p)
        return {
            "Pivot": p,
            "R1": r1,
            "R2": r2,
            "R3": r3,
            "S1": s1,
            "S2": s2,
            "S3": s3,
        }

    def daily_pivots(self) -> pd.DataFrame:
        rows = []
        for t in self.prices.columns:
            hlc = self._prior_session_hlc(t)
            if hlc is None:
                continue
            piv = self._classic_pivots(hlc["High"], hlc["Low"], hlc["Close"])
            piv["Ticker"] = t
            piv["Pivot_Source"] = hlc.get("source", "unknown")
            piv["Prior_High"] = hlc["High"]
            piv["Prior_Low"] = hlc["Low"]
            piv["Prior_Close"] = hlc["Close"]
            rows.append(piv)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("Ticker")

    def weekly_pivots(self) -> pd.DataFrame:
        rows = []
        for t in self.prices.columns:
            hlc = self._prior_week_hlc(t)
            if hlc is None:
                continue
            piv = self._classic_pivots(hlc["High"], hlc["Low"], hlc["Close"])
            piv = {f"W_{k}": v for k, v in piv.items()}
            piv["Ticker"] = t
            piv["W_Pivot_Source"] = hlc.get("source", "unknown")
            rows.append(piv)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("Ticker")

    # ------------------------------------------------------------------
    # Combined levels + status
    # ------------------------------------------------------------------
    def levels_table(self) -> pd.DataFrame:
        ma = self.moving_averages()
        piv = self.daily_pivots()
        wpiv = self.weekly_pivots()

        df = ma.join(piv, how="left")
        if not wpiv.empty:
            df = df.join(wpiv, how="left")

        level_cols = [
            c
            for c in df.columns
            if c in ("Pivot", "S1", "S2", "S3", "R1", "R2", "R3")
            or c.startswith("SMA_")
            or (c.startswith("W_") and c[2:] in ("Pivot", "S1", "S2", "S3", "R1", "R2", "R3"))
        ]

        nearest_sup, nearest_res = [], []
        dist_sup_pct, dist_res_pct = [], []

        for t, row in df.iterrows():
            price = row["Price"]
            levels = []
            for c in level_cols:
                v = row.get(c)
                if pd.notna(v):
                    levels.append((c, float(v)))

            supports = [(n, v) for n, v in levels if v < price]
            resistances = [(n, v) for n, v in levels if v > price]

            if supports:
                name, val = max(supports, key=lambda x: x[1])
                nearest_sup.append(f"{name}:{val:.2f}")
                dist_sup_pct.append((price - val) / price * 100.0)
            else:
                nearest_sup.append("—")
                dist_sup_pct.append(np.nan)

            if resistances:
                name, val = min(resistances, key=lambda x: x[1])
                nearest_res.append(f"{name}:{val:.2f}")
                dist_res_pct.append((val - price) / price * 100.0)
            else:
                nearest_res.append("—")
                dist_res_pct.append(np.nan)

        df["Nearest_Support"] = nearest_sup
        df["Dist_Support_%"] = dist_sup_pct
        df["Nearest_Resistance"] = nearest_res
        df["Dist_Resistance_%"] = dist_res_pct

        if self.meta:
            df.insert(0, "Name", [self.meta.get(t, {}).get("name", t) for t in df.index])
            df.insert(1, "Group", [self.meta.get(t, {}).get("group", "") for t in df.index])

        self._levels = df
        return df

    def status_flags(self, levels: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        if levels is None:
            levels = self.levels_table()

        rows = []
        for t, row in levels.iterrows():
            price = row["Price"]
            flags: Dict[str, Any] = {"Ticker": t}

            for w in self.ma_windows:
                col = f"SMA_{w}"
                val = row.get(col)
                flags[f"Above_SMA{w}"] = bool(pd.notna(val) and price > val)

            flags["Above_All_MA"] = all(
                flags.get(f"Above_SMA{w}", False) for w in self.ma_windows
            )

            s20, s50, s200 = row.get("SMA_20"), row.get("SMA_50"), row.get("SMA_200")
            if pd.notna(s20) and pd.notna(s50) and pd.notna(s200):
                flags["Golden_Stack"] = bool(s20 > s50 > s200)
                flags["Death_Stack"] = bool(s20 < s50 < s200)
            else:
                flags["Golden_Stack"] = False
                flags["Death_Stack"] = False

            dist_s = row.get("Dist_Support_%")
            dist_r = row.get("Dist_Resistance_%")
            tol_pct = self.at_tolerance * 100.0

            at_sup = bool(pd.notna(dist_s) and dist_s <= tol_pct)
            at_res = bool(pd.notna(dist_r) and dist_r <= tol_pct)
            flags["At_Support"] = at_sup
            flags["At_Resistance"] = at_res

            if at_res and not at_sup:
                position = "At_Resistance"
            elif at_sup and not at_res:
                position = "At_Support"
            elif pd.notna(dist_r) and dist_r < 1.0:
                position = "Near_Resistance"
            elif pd.notna(dist_s) and dist_s < 1.0:
                position = "Near_Support"
            elif flags["Above_All_MA"] and flags.get("Golden_Stack"):
                position = "Trend_Support"
            elif flags.get("Death_Stack") and not flags["Above_All_MA"]:
                position = "Trend_Resistance"
            else:
                position = "Mid_Range"

            r1, s1 = row.get("R1"), row.get("S1")
            if pd.notna(r1) and price > r1 * (1 + self.at_tolerance):
                position = "Breakout"
            elif pd.notna(s1) and price < s1 * (1 - self.at_tolerance):
                position = "Breakdown"

            flags["Position"] = position
            rows.append(flags)

        status = pd.DataFrame(rows).set_index("Ticker")
        if self.meta:
            status.insert(0, "Name", [self.meta.get(t, {}).get("name", t) for t in status.index])
            status.insert(1, "Group", [self.meta.get(t, {}).get("group", "") for t in status.index])

        self._status = status
        return status

    def summary(self, group: Optional[str] = None) -> pd.DataFrame:
        levels = self.levels_table()
        status = self.status_flags(levels)
        status_cols = [c for c in status.columns if c not in ("Name", "Group")]
        merged = levels.join(status[status_cols], how="left")

        if group and "Group" in merged.columns:
            merged = merged[merged["Group"] == group]

        prefer = [
            "Name", "Group", "Price",
            "Position", "At_Support", "At_Resistance",
            "Nearest_Support", "Dist_Support_%",
            "Nearest_Resistance", "Dist_Resistance_%",
            "SMA_20", "SMA_50", "SMA_200",
            "Above_SMA20", "Above_SMA50", "Above_SMA200", "Above_All_MA",
            "Golden_Stack", "Death_Stack",
            "Pivot", "S1", "S2", "R1", "R2",
            "Prior_High", "Prior_Low", "Prior_Close", "Pivot_Source",
            "W_Pivot", "W_S1", "W_R1", "W_Pivot_Source",
        ]
        cols = [c for c in prefer if c in merged.columns]
        cols += [c for c in merged.columns if c not in cols]
        return merged[cols]

    def position_counts(self, group: Optional[str] = None) -> Dict[str, int]:
        s = self.summary(group=group)
        if "Position" not in s.columns:
            return {}
        return s["Position"].value_counts().to_dict()
