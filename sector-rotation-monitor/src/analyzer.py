"""Core analysis: performance rankings, relative strength, RRG-style metrics."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SectorAnalyzer:
    """
    Computes sector performance metrics, relative strength vs benchmark,
    and simplified Relative Rotation Graph (RRG) coordinates.
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        benchmark: str = "SPY",
        sector_meta: Optional[Dict[str, Dict]] = None,
        rrg_params: Optional[Dict[str, Any]] = None,
    ):
        if benchmark not in prices.columns:
            raise ValueError(f"Benchmark {benchmark} not in price data")
        self.prices = prices
        self.benchmark = benchmark
        self.sector_tickers = [c for c in prices.columns if c != benchmark]
        self.sector_meta = sector_meta or {}
        self.rrg_params = rrg_params or {
            "rs_lookback": 63,
            "momentum_lookback": 21,
            "normalize": True,
        }

    def tickers_by_group(self, group: Optional[str] = None) -> List[str]:
        """
        Return tickers filtered by meta 'group' field ('sector' or 'industry').
        If group is None, return all non-benchmark tickers.
        """
        if group is None:
            return list(self.sector_tickers)
        out = []
        for t in self.sector_tickers:
            meta = self.sector_meta.get(t, {})
            if meta.get("group", "sector") == group:
                out.append(t)
        return out

    # ------------------------------------------------------------------
    # Performance tables
    # ------------------------------------------------------------------
    def performance_table(self, periods: Dict[str, Optional[int]]) -> pd.DataFrame:
        """
        Absolute % returns for each sector (and benchmark) across periods.
        """
        latest = self.prices.iloc[-1]
        records = []

        for label, days in periods.items():
            if label.upper() == "YTD" or days is None:
                year = self.prices.index[-1].year
                year_start = pd.Timestamp(f"{year}-01-01")
                subset = self.prices[self.prices.index >= year_start]
                if len(subset) < 2:
                    ret = pd.Series(np.nan, index=self.prices.columns)
                else:
                    ret = (latest / subset.iloc[0] - 1.0) * 100.0
            else:
                if len(self.prices) <= days:
                    ret = pd.Series(np.nan, index=self.prices.columns)
                else:
                    past = self.prices.iloc[-(days + 1)]
                    ret = (latest / past - 1.0) * 100.0

            for ticker, val in ret.items():
                records.append({"Period": label, "Ticker": ticker, "Return_%": val})

        df = pd.DataFrame(records)
        pivot = df.pivot(index="Ticker", columns="Period", values="Return_%")
        # Reorder columns sensibly
        ordered = [p for p in periods.keys() if p in pivot.columns]
        pivot = pivot[ordered]
        return pivot

    def relative_performance(self, periods: Dict[str, Optional[int]]) -> pd.DataFrame:
        """
        Excess return vs benchmark for each period (sector − SPY).
        """
        abs_perf = self.performance_table(periods)
        if self.benchmark not in abs_perf.index:
            raise ValueError("Benchmark missing from performance table")
        bench = abs_perf.loc[self.benchmark]
        rel = abs_perf.subtract(bench, axis=1)
        rel = rel.drop(index=self.benchmark, errors="ignore")
        return rel

    def rank_sectors(
        self,
        periods: Dict[str, Optional[int]],
        by: str = "relative",
        primary_period: str = "3M",
        group: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Rank sectors/industries by absolute or relative performance.

        group: None = all, 'sector' = broad sectors only, 'industry' = industries only.
        """
        if by == "relative":
            matrix = self.relative_performance(periods)
        else:
            matrix = self.performance_table(periods)
            matrix = matrix.drop(index=self.benchmark, errors="ignore")

        if group is not None:
            keep = self.tickers_by_group(group)
            matrix = matrix.loc[matrix.index.intersection(keep)]

        ranks = matrix.rank(ascending=False, method="min")
        ranks = ranks.add_suffix("_Rank")

        weights = {
            "1D": 0.05,
            "1W": 0.10,
            "1M": 0.20,
            "3M": 0.30,
            "6M": 0.20,
            "YTD": 0.10,
            "1Y": 0.05,
        }
        available = [c for c in matrix.columns if c in weights]
        if not available:
            available = list(matrix.columns)

        w = np.array([weights.get(c, 1.0 / len(available)) for c in available])
        w = w / w.sum()
        composite = (ranks[[f"{c}_Rank" for c in available]] * w).sum(axis=1)
        composite.name = "Composite_Rank"

        result = pd.concat([matrix, ranks, composite], axis=1)
        result = result.sort_values("Composite_Rank")
        result["Overall_Rank"] = range(1, len(result) + 1)

        if self.sector_meta:
            result["Name"] = [self.sector_meta.get(t, {}).get("name", t) for t in result.index]
            result["Style"] = [self.sector_meta.get(t, {}).get("style", "") for t in result.index]
            result["Group"] = [self.sector_meta.get(t, {}).get("group", "") for t in result.index]
            parent = [self.sector_meta.get(t, {}).get("parent_sector", "") for t in result.index]
            result["Parent"] = parent
            cols = ["Name", "Style", "Group"] + [
                c for c in result.columns if c not in ("Name", "Style", "Group", "Parent")
            ]
            if any(parent):
                cols = ["Name", "Style", "Group", "Parent"] + [
                    c for c in result.columns if c not in ("Name", "Style", "Group", "Parent")
                ]
            result = result[cols]

        return result

    # ------------------------------------------------------------------
    # Relative Strength & simplified RRG
    # ------------------------------------------------------------------
    def _price_relative(self) -> pd.DataFrame:
        """Price of each sector divided by benchmark (raw ratio)."""
        bench = self.prices[self.benchmark]
        rel = self.prices[self.sector_tickers].div(bench, axis=0)
        return rel

    def rs_ratio_series(self, lookback: Optional[int] = None) -> pd.DataFrame:
        """
        JdK-style RS-Ratio approximation.

        We normalize the price relative so that a moving average of the
        ratio sits at 100. Values > 100 → relative strength; < 100 → weakness.
        """
        lookback = lookback or self.rrg_params.get("rs_lookback", 63)
        ratio = self._price_relative()
        # Rolling mean of the ratio
        ma = ratio.rolling(window=lookback, min_periods=max(10, lookback // 3)).mean()
        # Normalize: current ratio / its MA * 100
        rs = (ratio / ma) * 100.0
        return rs

    def rs_momentum_series(self, lookback: Optional[int] = None) -> pd.DataFrame:
        """
        Rate-of-change of RS-Ratio (momentum of relative strength).
        """
        lookback = lookback or self.rrg_params.get("momentum_lookback", 21)
        rs = self.rs_ratio_series()
        # Percentage change of RS over the momentum window
        mom = rs.pct_change(periods=lookback) * 100.0
        return mom

    def rrg_snapshot(self, group: Optional[str] = None) -> pd.DataFrame:
        """
        Current RRG coordinates for each ticker (optionally filtered by group).

        Returns DataFrame with RS_Ratio, RS_Momentum, Quadrant, Distance.
        """
        rs = self.rs_ratio_series().iloc[-1]
        mom = self.rs_momentum_series().iloc[-1]

        df = pd.DataFrame({
            "RS_Ratio": rs,
            "RS_Momentum": mom,
        })

        if group is not None:
            keep = self.tickers_by_group(group)
            df = df.loc[df.index.intersection(keep)]

        def quadrant(row):
            x, y = row["RS_Ratio"], row["RS_Momentum"]
            if x >= 100 and y >= 0:
                return "Leading"
            if x >= 100 and y < 0:
                return "Weakening"
            if x < 100 and y < 0:
                return "Lagging"
            return "Improving"

        df["Quadrant"] = df.apply(quadrant, axis=1)
        df["Distance"] = np.sqrt((df["RS_Ratio"] - 100) ** 2 + df["RS_Momentum"] ** 2)
        df = df.sort_values("Distance", ascending=False)

        if self.sector_meta:
            df["Name"] = [self.sector_meta.get(t, {}).get("name", t) for t in df.index]
            df["Style"] = [self.sector_meta.get(t, {}).get("style", "") for t in df.index]
            df["Group"] = [self.sector_meta.get(t, {}).get("group", "") for t in df.index]

        return df

    # ------------------------------------------------------------------
    # Regime helpers
    # ------------------------------------------------------------------
    def cyclical_vs_defensive(self, period: str = "1M") -> Dict[str, float]:
        """
        Simple risk-on / risk-off gauge using broad sectors only.
        """
        cyclical = ["XLK", "XLF", "XLE", "XLI", "XLY", "XLB"]
        defensive = ["XLV", "XLU", "XLP"]

        days = None if period == "YTD" else {"1D": 1, "1W": 5, "1M": 21, "3M": 63}.get(period, 21)
        rel = self.relative_performance({period: days})
        col = period if period in rel.columns else rel.columns[0]

        cyc = [t for t in cyclical if t in rel.index]
        defn = [t for t in defensive if t in rel.index]

        cyc_avg = rel.loc[cyc, col].mean() if cyc else np.nan
        def_avg = rel.loc[defn, col].mean() if defn else np.nan
        spread = cyc_avg - def_avg

        return {
            "cyclical_avg_excess": float(cyc_avg) if not np.isnan(cyc_avg) else None,
            "defensive_avg_excess": float(def_avg) if not np.isnan(def_avg) else None,
            "risk_on_spread": float(spread) if not np.isnan(spread) else None,
            "regime": "Risk-On" if spread > 0.5 else ("Risk-Off" if spread < -0.5 else "Neutral"),
        }

    def summary_stats(self, group: Optional[str] = "sector") -> Dict[str, Any]:
        """High-level snapshot for dashboards / reports (default: broad sectors)."""
        rrg = self.rrg_snapshot(group=group)
        leading = rrg[rrg["Quadrant"] == "Leading"].index.tolist()
        improving = rrg[rrg["Quadrant"] == "Improving"].index.tolist()
        weakening = rrg[rrg["Quadrant"] == "Weakening"].index.tolist()
        lagging = rrg[rrg["Quadrant"] == "Lagging"].index.tolist()

        regime = self.cyclical_vs_defensive("1M")

        return {
            "as_of": str(self.prices.index[-1].date()),
            "benchmark": self.benchmark,
            "leading": leading,
            "improving": improving,
            "weakening": weakening,
            "lagging": lagging,
            "regime": regime,
            "n_tickers": len(self.sector_tickers),
            "n_sectors": len(self.tickers_by_group("sector")),
            "n_industries": len(self.tickers_by_group("industry")),
        }
