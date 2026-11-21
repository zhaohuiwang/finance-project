"""
Streamlit presentation layer for the live market dashboard.

All visual components live here so that the business logic modules stay
free of UI concerns.  The main fragment is refreshed every two seconds.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st
import altair as alt

from .config import (
    SYMBOLS,
    VIX_SYMBOL,
    PERIODS,
    RETENTION_DAYS,
    VIX_RETENTION_DAYS,
    EASTERN,
    DATABASE,
    VIX_DATABASE,
    IDLE_AFTER_SECONDS,
)
from .database import BarDatabase
from .indicators import IndicatorCalculator
from .signals import EquitySignalCalculator, VixSignalCalculator
from .status import StatusManager
from .stream import MarketDataStream


def _is_idle(status_snapshot: dict) -> bool:
    """
    Return True when no new bar has arrived for longer than
    IDLE_AFTER_SECONDS.  In that case we render a lightweight view
    to save CPU.
    """
    last = status_snapshot.get("last_bar_time")
    if last is None:
        # Still waiting for the very first bar – treat as idle
        return True
    age = (datetime.now(timezone.utc) - last).total_seconds()
    return age > IDLE_AFTER_SECONDS


def display_market(
    equity_db: BarDatabase,
    vix_db: BarDatabase,
    status: StatusManager,
    stream: MarketDataStream,
    indicator_calc: IndicatorCalculator,
    equity_signal_calc: EquitySignalCalculator,
    vix_signal_calc: VixSignalCalculator,
) -> None:
    """
    Main live dashboard fragment.  Designed to be called from a
    @st.fragment(run_every=...) decorator so it refreshes automatically.

    When no new bar has arrived for IDLE_AFTER_SECONDS a clear "Idle mode"
    banner is shown at the top, but the last known data (tables, signals,
    charts) remains visible.  Live updates resume automatically as soon as
    the next bar arrives.
    """
    # ---- Status bar ----
    status_snapshot = status.get()
    idle = _is_idle(status_snapshot)

    # Idle banner – still show the last known data below
    if idle:
        # st.warning(
        #     f"💤 Idle mode – no new bars for more than {IDLE_AFTER_SECONDS}s. "
        #     "Showing last known data. Full live updates will resume automatically "
        #     "when the next bar arrives. The WebSocket connection stays open and ready."
        # )
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(90deg, #fff3cd 0%, #ffe69c 100%);
                border: 2px solid #ffc107;
                border-left: 8px solid #e0a800;
                border-radius: 8px;
                padding: 14px 18px;
                margin: 10px 0 16px 0;
                font-size: 1.05rem;
                color: #664d03;
                box-shadow: 0 2px 6px rgba(0,0,0,0.08);
            ">
                <strong style="font-size: 1.15rem;">💤 IDLE MODE</strong>
                &nbsp;·&nbsp; No new bars for more than <strong>{IDLE_AFTER_SECONDS}s</strong>.
                Showing last known data.
                Live updates will resume automatically when the next bar arrives.
                <br>
                <span style="font-size: 0.9rem; opacity: 0.85;">
                    WebSocket connection remains open and ready.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Streaming bar status banner    
    col_a, col_b, col_c = st.columns([2, 2, 3])

    with col_a:
        if stream.stream_thread and stream.stream_thread.is_alive():
            if idle:
                st.warning("Stream alive · idle (no new bars)")
            else:
                st.success("Market data stream is running")
        else:
            st.error("Market data stream stopped")

    with col_b:
        if status_snapshot["last_bar_time"]:
            age = datetime.now(timezone.utc) - status_snapshot["last_bar_time"]
            age_s = int(age.total_seconds())
            st.info(
                f"Last bar: {status_snapshot['last_bar_time'].strftime('%H:%M:%S')} UTC  "
                f"({age_s}s ago)"
            )
        else:
            st.warning("Waiting for first bar…")

    with col_c:
        if status_snapshot["last_error"]:
            st.error(
                f"Last error ({status_snapshot['last_error_time'].strftime('%H:%M:%S')} UTC): "
                f"{status_snapshot['last_error']}"
            )
        else:
            st.caption(
                f"Bars received this session: {status_snapshot['bars_received']}"
            )

    # Data info banner
    st.info(
        "This dashboard uses IEX exchange data, not the consolidated US market feed."
    )

    # ---- VIX Regime ----
    vix_daily = vix_db.get_daily_closes(VIX_SYMBOL, VIX_RETENTION_DAYS)
    vix_signal = vix_signal_calc.calculate(vix_daily)

    st.subheader("VIX Regime (via VIXY)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Signal", vix_signal.signal)
    c2.metric(
        "Latest",
        f"{vix_signal.latest:.2f}" if vix_signal.latest is not None else "—",
    )
    c3.metric(
        "3-day Δ",
        (
            f"{vix_signal.change_3d_pct:+.1f}%"
            if vix_signal.change_3d_pct is not None
            else "—"
        ),
    )
    c4.metric(
        "vs mean",
        (f"{vix_signal.vs_mean:+.1f}%" if vix_signal.vs_mean is not None else "—"),
    )
    if not vix_daily.empty:
        st.caption(
            f"Based on last {vix_signal.days} daily closes · "
            f"Retention: {VIX_RETENTION_DAYS} days"
        )

    st.divider()

    # ---- Equity summary table ----
    summary = []
    for symbol in SYMBOLS:
        df = equity_db.get_bars(symbol)
        if df.empty:
            continue

        df = indicator_calc.calculate(df)
        latest = df.iloc[-1]
        signal = equity_signal_calc.calculate(df)

        row = {
            "Symbol": symbol,
            "Last Price": latest["close"],
            "Signal": signal.signal,
            "Score": signal.score,
            "VWAP": latest["VWAP"],
            "Price vs VWAP": signal.price_vs_vwap,
            "EMA Alignment": signal.ema_alignment,
            "Crossover": signal.crossover,
            "Bars": signal.bars,
            "Last Bar (EST)": latest["timestamp"].tz_convert(EASTERN),
        }

        # Combine SMA + EMA into a single cell per period
        for period in PERIODS:
            sma = latest.get(f"SMA_{period}")
            ema = latest.get(f"EMA_{period}")
            if pd.notna(sma) and pd.notna(ema):
                row[f"{period}m"] = f"{sma:,.2f} / {ema:,.2f}"
            elif pd.notna(sma):
                row[f"{period}m"] = f"{sma:,.2f} / —"
            elif pd.notna(ema):
                row[f"{period}m"] = f"— / {ema:,.2f}"
            else:
                row[f"{period}m"] = "warming up"

        summary.append(row)

    if not summary:
        st.warning(
            "Waiting for market data. Indicators will appear as bars accumulate."
        )
        return

    result = pd.DataFrame(summary)
    preferred_order = [
        "Symbol",
        "Last Price",
        "Signal",
        "Score",
        "VWAP",
        "Price vs VWAP",
        "EMA Alignment",
        "Crossover",
        "Bars",
        "Last Bar (EST)",
    ] + [f"{p}m" for p in PERIODS]
    result = result[[c for c in preferred_order if c in result.columns]]

    st.subheader("Current Market Indicators")

    def color_signal(val: str) -> str:
        if isinstance(val, str):
            if "BULLISH" in val:
                return "background-color: #d4edda; color: #155724"
            if "BEARISH" in val:
                return "background-color: #f8d7da; color: #721c24"
            if "NEUTRAL" in val:
                return "background-color: #fff3cd; color: #856404"
            if "WARMING" in val or "NO DATA" in val:
                return "background-color: #e2e3e5; color: #383d41"
        return ""

    styled = result.style.map(color_signal, subset=["Signal"])

    st.dataframe(
        styled,
        width="stretch",  # makes the whole table use the available page width
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn(
                "Symbol",
                pinned=True,  # stay even when you move the slide bar
            ),
            "Last Price": st.column_config.NumberColumn("Last Price", format="%.2f"),
            "VWAP": st.column_config.NumberColumn("VWAP", format="%.2f"),
            "Score": st.column_config.NumberColumn("Score", format="%d"),
            "Bars": st.column_config.NumberColumn("Bars", format="%d"),
            "Last Bar (EST)": st.column_config.DatetimeColumn(
                "Last Bar (EST)", format="HH:mm:ss"
            ),
            **{
                f"{p}m": st.column_config.TextColumn(f"{p}m\nSMA | EMA")
                for p in PERIODS
            },
        },
    )

    st.caption(
        "All prices are in USD ($). SMA/EMA values are based on completed "
        "one-minute bars. Session VWAP resets at the start of each calendar "
        f"day (US/Eastern). Equity retention: {RETENTION_DAYS} days · "
        f"VIX retention: {VIX_RETENTION_DAYS} days."
    )

    st.divider()

    # Individual stock details
    st.subheader("Individual Stock Details")
    for symbol in SYMBOLS:
        df = equity_db.get_bars(symbol)
        if df.empty:
            continue

        df = indicator_calc.calculate(df)
        latest = df.iloc[-1]
        signal = equity_signal_calc.calculate(df)

        st.markdown(f"### {symbol}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Signal", signal.signal)
        col2.metric(
            "Score",
            signal.score if signal.score is not None else "—",
        )
        col3.metric("Latest Price", f"{latest['close']:,.2f}")
        col4.metric(
            "Session VWAP",
            f"{latest['VWAP']:,.2f}" if pd.notna(latest["VWAP"]) else "N/A",
        )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "5-minute SMA",
            (f"{latest['SMA_5']:,.2f}" if pd.notna(latest["SMA_5"]) else "Warming up"),
        )
        col2.metric(
            "10-minute SMA",
            (
                f"{latest['SMA_10']:,.2f}"
                if pd.notna(latest["SMA_10"])
                else "Warming up"
            ),
        )
        col3.metric(
            "5-minute EMA",
            (f"{latest['EMA_5']:,.2f}" if pd.notna(latest["EMA_5"]) else "Warming up"),
        )
        col4.metric(
            "10-minute EMA",
            (
                f"{latest['EMA_10']:,.2f}"
                if pd.notna(latest["EMA_10"])
                else "Warming up"
            ),
        )

        # Chart
        chart_data = df.tail(60).copy()
        price_columns = [
            "close",
            "VWAP",
            # "SMA_5",
            # "SMA_10",
            "EMA_5",
            "EMA_10",
        ]
        available = [c for c in price_columns if c in chart_data.columns]

        price_min = chart_data[available].min().min()
        price_max = chart_data[available].max().max()
        price_range = price_max - price_min
        padding = max(price_range * 0.20, 0.05)
        y_min = price_min - padding
        y_max = price_max + padding

        plot_data = chart_data[["timestamp"] + available].melt(
            id_vars="timestamp",
            var_name="Indicator",
            value_name="Price",
        )

        chart = (
            alt.Chart(plot_data)
            .mark_line()
            .encode(
                x=alt.X("timestamp:T", title="Time"),
                y=alt.Y(
                    "Price:Q",
                    title="Price",
                    scale=alt.Scale(domain=[y_min, y_max]),
                ),
                color=alt.Color("Indicator:N", title="Indicator"),
                tooltip=[
                    alt.Tooltip("timestamp:T", title="Time"),
                    alt.Tooltip("Indicator:N"),
                    alt.Tooltip("Price:Q", format=".2f"),
                ],
            )
            .properties(height=350)
        )
        st.altair_chart(chart, width="stretch")

        with st.expander(f"{symbol} historical data"):
            st.dataframe(
                df.tail(100).sort_values("timestamp", ascending=False),
                width="stretch",
                hide_index=True,
            )

        st.divider()
