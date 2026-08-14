"""Visualization helpers: heatmaps, RRG scatter, ranking bars."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)

# Consistent color palette for quadrants
QUADRANT_COLORS = {
    "Leading": "#2ecc71",      # green
    "Weakening": "#f1c40f",    # yellow
    "Lagging": "#e74c3c",      # red
    "Improving": "#3498db",    # blue
}


class SectorVisualizer:
    """Generate publication-quality charts for sector rotation analysis."""

    def __init__(self, output_dir: str | Path, dpi: int = 150):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dpi = dpi
        sns.set_theme(style="whitegrid", context="talk")

    def performance_heatmap(
        self,
        perf: pd.DataFrame,
        title: str = "Sector Absolute Returns (%)",
        filename: str = "performance_heatmap.png",
        cmap: str = "RdYlGn",
        center: float = 0.0,
    ) -> Path:
        """Heatmap of returns (rows = tickers, columns = periods)."""
        fig, ax = plt.subplots(figsize=(12, 8))
        data = perf.copy()
        # Drop benchmark if present for cleaner sector view (optional)
        sns.heatmap(
            data,
            annot=True,
            fmt=".1f",
            cmap=cmap,
            center=center,
            linewidths=0.5,
            ax=ax,
            cbar_kws={"label": "Return %"},
        )
        ax.set_title(title, fontsize=16, pad=12)
        ax.set_xlabel("")
        ax.set_ylabel("")
        plt.tight_layout()
        path = self.output_dir / filename
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved heatmap → %s", path)
        return path

    def relative_heatmap(
        self,
        rel: pd.DataFrame,
        title: str = "Relative Strength vs SPY (Excess Return %)",
        filename: str = "relative_heatmap.png",
    ) -> Path:
        return self.performance_heatmap(
            rel, title=title, filename=filename, cmap="RdYlGn", center=0.0
        )

    def ranking_bar(
        self,
        ranks: pd.DataFrame,
        value_col: str = "3M",
        title: str = "Sector Ranking by 3M Relative Performance",
        filename: str = "ranking_bar.png",
    ) -> Path:
        """Horizontal bar chart of a chosen performance column."""
        df = ranks.copy()
        if value_col not in df.columns:
            # try first numeric
            numeric = df.select_dtypes(include=[np.number]).columns
            value_col = numeric[0] if len(numeric) else df.columns[0]

        df = df.sort_values(value_col, ascending=True)
        labels = df["Sector"] if "Sector" in df.columns else df.index

        fig, ax = plt.subplots(figsize=(10, 7))
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in df[value_col]]
        ax.barh(labels, df[value_col], color=colors, edgecolor="black", linewidth=0.4)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Excess Return % vs SPY" if "Relative" in title or "Excess" in title else "Return %")
        ax.set_title(title, fontsize=14)
        plt.tight_layout()
        path = self.output_dir / filename
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved ranking bar → %s", path)
        return path

    def rrg_scatter(
        self,
        rrg: pd.DataFrame,
        title: str = "Relative Rotation Graph (Simplified)",
        filename: str = "rrg_scatter.png",
        annotate: bool = True,
    ) -> Path:
        """
        Scatter of RS-Ratio (x) vs RS-Momentum (y).
        Classic four-quadrant layout centered on (100, 0).
        """
        fig, ax = plt.subplots(figsize=(11, 9))

        for q, color in QUADRANT_COLORS.items():
            subset = rrg[rrg["Quadrant"] == q]
            if subset.empty:
                continue
            ax.scatter(
                subset["RS_Ratio"],
                subset["RS_Momentum"],
                s=180,
                c=color,
                label=q,
                edgecolors="black",
                linewidths=0.6,
                alpha=0.9,
                zorder=3,
            )
            if annotate:
                for idx, row in subset.iterrows():
                    label = row.get("Sector", idx) if "Sector" in rrg.columns else idx
                    ax.annotate(
                        label,
                        (row["RS_Ratio"], row["RS_Momentum"]),
                        textcoords="offset points",
                        xytext=(6, 6),
                        fontsize=9,
                        fontweight="medium",
                    )

        # Crosshairs at (100, 0)
        ax.axvline(100, color="gray", linestyle="--", linewidth=1.0, zorder=1)
        ax.axhline(0, color="gray", linestyle="--", linewidth=1.0, zorder=1)

        # Quadrant background shading (subtle)
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        # Expand a bit for aesthetics
        xpad = (xlim[1] - xlim[0]) * 0.05
        ypad = (ylim[1] - ylim[0]) * 0.05
        ax.set_xlim(xlim[0] - xpad, xlim[1] + xpad)
        ax.set_ylim(ylim[0] - ypad, ylim[1] + ypad)

        ax.set_xlabel("RS-Ratio (Relative Strength)", fontsize=12)
        ax.set_ylabel("RS-Momentum", fontsize=12)
        ax.set_title(title, fontsize=15, pad=10)
        ax.legend(loc="upper left", frameon=True, fontsize=10)
        ax.grid(True, alpha=0.3)

        # Quadrant labels
        ax.text(0.98, 0.98, "Leading", transform=ax.transAxes, ha="right", va="top",
                fontsize=11, color=QUADRANT_COLORS["Leading"], fontweight="bold", alpha=0.7)
        ax.text(0.98, 0.02, "Weakening", transform=ax.transAxes, ha="right", va="bottom",
                fontsize=11, color=QUADRANT_COLORS["Weakening"], fontweight="bold", alpha=0.7)
        ax.text(0.02, 0.02, "Lagging", transform=ax.transAxes, ha="left", va="bottom",
                fontsize=11, color=QUADRANT_COLORS["Lagging"], fontweight="bold", alpha=0.7)
        ax.text(0.02, 0.98, "Improving", transform=ax.transAxes, ha="left", va="top",
                fontsize=11, color=QUADRANT_COLORS["Improving"], fontweight="bold", alpha=0.7)

        plt.tight_layout()
        path = self.output_dir / filename
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved RRG scatter → %s", path)
        return path

    def cumulative_relative_chart(
        self,
        prices: pd.DataFrame,
        benchmark: str = "SPY",
        lookback_days: int = 126,
        filename: str = "cumulative_relative.png",
    ) -> Path:
        """
        Normalized cumulative relative strength lines (sector / SPY, rebased to 100).
        """
        sector_cols = [c for c in prices.columns if c != benchmark]
        subset = prices.iloc[-lookback_days:]
        ratio = subset[sector_cols].div(subset[benchmark], axis=0)
        # Rebase to 100 at start of window
        rebased = ratio / ratio.iloc[0] * 100.0

        fig, ax = plt.subplots(figsize=(13, 7))
        for col in rebased.columns:
            ax.plot(rebased.index, rebased[col], label=col, linewidth=1.6)

        ax.axhline(100, color="black", linestyle="--", linewidth=1.0, alpha=0.7)
        ax.set_title(f"Cumulative Relative Strength vs {benchmark} (last {lookback_days} sessions)", fontsize=14)
        ax.set_ylabel("Relative Strength (rebased = 100)")
        ax.legend(loc="upper left", ncol=3, fontsize=9, frameon=True)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        path = self.output_dir / filename
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved cumulative relative chart → %s", path)
        return path
