"""Charting helpers – static matplotlib + interactive Plotly."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from .detectors import Level

PLOTS_DIR = Path(__file__).resolve().parent.parent / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def plot_levels(
    df: pd.DataFrame,
    levels: List[Level],
    ticker: str,
    title: Optional[str] = None,
    save: bool = False,
    show: bool = True,
    max_levels: int = 12,
    vwap: Optional[pd.Series] = None,
    vwap_bands: Optional[pd.DataFrame] = None,
) -> Optional[Path]:
    """Static matplotlib chart with S/R lines (+ optional VWAP)."""
    if not levels:
        print(f"No levels to plot for {ticker}")
        return None

    levels = sorted(levels, key=lambda L: -L.strength)[:max_levels]

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(df.index, df["Close"], color="black", linewidth=1.2, label="Close", zorder=3)
    ax.fill_between(df.index, df["Low"], df["High"], color="gray", alpha=0.15, label="Daily range")

    if vwap is not None:
        ax.plot(df.index, vwap, color="orange", linewidth=1.4, alpha=0.9, label="VWAP", zorder=3)
    if vwap_bands is not None and not vwap_bands.empty:
        if "upper_1" in vwap_bands.columns:
            ax.plot(df.index, vwap_bands["upper_1"], color="orange", linewidth=0.8, linestyle="--", alpha=0.5, label="VWAP ±1σ")
            ax.plot(df.index, vwap_bands["lower_1"], color="orange", linewidth=0.8, linestyle="--", alpha=0.5)
        if "upper_2" in vwap_bands.columns:
            ax.plot(df.index, vwap_bands["upper_2"], color="orange", linewidth=0.7, linestyle=":", alpha=0.4, label="VWAP ±2σ")
            ax.plot(df.index, vwap_bands["lower_2"], color="orange", linewidth=0.7, linestyle=":", alpha=0.4)
            ax.fill_between(df.index, vwap_bands["lower_2"], vwap_bands["upper_2"], color="orange", alpha=0.05)

    current = df["Close"].iloc[-1]
    colors = {"support": "#2ca02c", "resistance": "#d62728", "both": "#1f77b4"}
    style = {"daily": "--", "weekly": "-", "confluence": "-"}

    for lvl in levels:
        color = colors.get(lvl.kind, "gray")
        ls = style.get(lvl.timeframe, "--")
        lw = 1.0 + 0.35 * min(lvl.strength, 6)
        ax.axhline(
            y=lvl.price,
            color=color,
            linestyle=ls,
            linewidth=lw,
            alpha=0.85,
            label=f"{lvl.kind[:3].upper()} {lvl.price:.2f} (s={lvl.strength})",
            zorder=2,
        )
        ax.annotate(
            f"{lvl.price:.1f}",
            xy=(df.index[-1], lvl.price),
            xytext=(8, 0),
            textcoords="offset points",
            fontsize=8,
            color=color,
            va="center",
        )

    ax.axhline(current, color="purple", linestyle=":", linewidth=1.2, alpha=0.7, label=f"Last {current:.2f}")
    ax.set_title(title or f"{ticker} – Support & Resistance", fontsize=14)
    ax.set_ylabel("Price")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    out_path = None
    if save:
        out_path = PLOTS_DIR / f"{ticker}_sr_levels.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved static plot → {out_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)
    return out_path


def plot_interactive(
    df: pd.DataFrame,
    levels: List[Level],
    ticker: str,
    title: Optional[str] = None,
    save: bool = False,
    max_levels: int = 15,
    vwap: Optional[pd.Series] = None,
    vwap_bands: Optional[pd.DataFrame] = None,
) -> Optional[Path]:
    """Interactive Plotly candlestick chart with S/R and VWAP."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("plotly not installed – skipping interactive chart")
        return None

    levels = sorted(levels, key=lambda L: -L.strength)[:max_levels]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.72, 0.28],
        subplot_titles=(title or f"{ticker} Support & Resistance", "Volume"),
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1, col=1,
    )

    if vwap is not None:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=vwap,
                mode="lines",
                name="VWAP",
                line=dict(color="orange", width=1.5),
            ),
            row=1, col=1,
        )

    colors = {"support": "#2ca02c", "resistance": "#d62728", "both": "#1f77b4"}
    for lvl in levels:
        color = colors.get(lvl.kind, "gray")
        fig.add_hline(
            y=lvl.price,
            line_dash="solid" if lvl.timeframe in ("weekly", "confluence") else "dash",
            line_color=color,
            line_width=1.5 + 0.3 * min(lvl.strength, 5),
            annotation_text=f"{lvl.price:.1f} ({lvl.kind[:1].upper()} s={lvl.strength})",
            annotation_position="right",
            row=1, col=1,
        )

    colors_vol = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=colors_vol, opacity=0.6),
        row=2, col=1,
    )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=800,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=50, t=80, b=40),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

    out_path = None
    if save:
        out_path = PLOTS_DIR / f"{ticker}_sr_interactive.html"
        fig.write_html(str(out_path))
        print(f"Saved interactive chart → {out_path}")

    try:
        fig.show()
    except Exception:
        pass

    return out_path


def print_levels_table(levels: List[Level], current_price: float, top_n: int = 18) -> None:
    """Pretty-print levels sorted by strength / score."""
    print(f"\n{'='*88}")
    print(f"{'Price':>9}  {'Kind':<11}  {'Str':>4}  {'Score':>6}  {'TF':<11}  {'Method':<28}  Dist%")
    print(f"{'-'*88}")
    for L in sorted(levels, key=lambda x: (-x.score if x.score else -x.strength, -x.strength))[:top_n]:
        dist = (L.price - current_price) / current_price * 100
        sc = f"{L.score:5.1f}" if L.score else "  -  "
        print(
            f"{L.price:9.2f}  {L.kind:<11}  {L.strength:4d}  {sc}  {L.timeframe:<11}  {L.method:<28}  {dist:+6.1f}%"
        )
    print(f"{'='*88}\n")
