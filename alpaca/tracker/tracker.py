"""
NASDAQ Live Market Monitor - Streamlit entry point.

Run with:
    streamlit run scripts/tracker.py
"""

import logging
from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st
import altair as alt

from market.config import (
    SYMBOLS,
    PERIODS,
    RETENTION_DAYS,
    DATABASE,
    EASTERN,
    API_KEY,
    API_SECRET,
)

# from market import db, indicators, stream
from market import db, indicators
from market.stream import get_market_stream

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Start / get the stream (cached)
market_stream = get_market_stream()

# ---- Page config (must be first Streamlit call) ----
st.set_page_config(
    page_title="NASDAQ Market Monitor",
    page_icon="📈",
    layout="wide",
)

if not API_KEY or not API_SECRET:
    st.error("Missing Alpaca API credentials. Check your .env file.")
    st.stop()


# ============================================================
# LIVE DISPLAY
# ============================================================
@st.fragment(run_every=timedelta(seconds=2))
def display_market():
    # status = stream.get_status()
    status = market_stream.get_status()

    # ---- Status bar ----
    col_a, col_b, col_c = st.columns([2, 2, 3])

    with col_a:
        # if stream.stream_is_alive():
        #     st.success("Market data stream is running")
        # else:
        #     st.error("Market data stream stopped")
        if market_stream.is_alive():
            st.success("Market data stream is running")
        else:
            st.error("Market data stream stopped")

    with col_b:
        if status["last_bar_time"]:
            age = datetime.now(timezone.utc) - status["last_bar_time"]
            st.info(
                f"Last bar: {status['last_bar_time'].strftime('%H:%M:%S')} UTC  "
                f"({int(age.total_seconds())}s ago)"
            )
        else:
            st.warning("Waiting for first bar…")

    with col_c:
        if status["last_error"]:
            st.error(
                f"Last error ({status['last_error_time'].strftime('%H:%M:%S')} UTC): "
                f"{status['last_error']}"
            )
        else:
            st.caption(f"Bars received this session: {status['bars_received']}")

    st.info(
        "This dashboard uses IEX exchange data, not the consolidated US market feed."
    )

    # ---- Summary table ----
    summary = []

    for symbol in SYMBOLS:
        df = db.get_bars(symbol)
        if df.empty:
            continue

        df = indicators.calculate_indicators(df)
        latest = df.iloc[-1]
        signal = indicators.calculate_signal(df)

        row = {
            "Symbol": symbol,
            "Last Price": latest["close"],
            "Signal": signal["signal"],
            "Score": signal["score"],
            "VWAP": latest["VWAP"],
            "Price vs VWAP": signal["price_vs_vwap"],
            "EMA Alignment": signal["ema_alignment"],
            "Crossover": signal["crossover"],
            "Bars": signal["bars"],
            "Last Bar (EST)": latest["timestamp"].tz_convert(EASTERN),
        }

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

    def color_signal(val):
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
        width=True,
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", pinned=True),
            "Last Price": st.column_config.NumberColumn("Last Price", format="%.2f"),
            "VWAP": st.column_config.NumberColumn("VWAP", format="%.2f"),
            "Score": st.column_config.NumberColumn("Score", format="%d"),
            "Bars": st.column_config.NumberColumn("Bars", format="%d"),
            "Last Bar (EST)": st.column_config.DatetimeColumn(
                "Last Bar (EST)",
                format="HH:mm:ss",
            ),
            **{
                f"{p}m": st.column_config.TextColumn(f"{p}m\nSMA | EMA")
                for p in PERIODS
            },
        },
    )

    st.caption(
        "All prices are in USD ($). SMA/EMA values are based on completed one-minute bars. "
        "Session VWAP resets at the start of each calendar day (US/Eastern). "
        "The dashboard refreshes every two seconds; new bars normally arrive once per minute."
    )

    st.divider()

    # ---- Individual stock details ----
    st.subheader("Individual Stock Details")

    for symbol in SYMBOLS:
        df = db.get_bars(symbol)
        if df.empty:
            continue

        df = indicators.calculate_indicators(df)
        latest = df.iloc[-1]
        signal = indicators.calculate_signal(df)

        st.markdown(f"### {symbol}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Signal", signal["signal"])
        col2.metric("Score", signal["score"] if signal["score"] is not None else "—")
        col3.metric("Latest Price", f"{latest['close']:,.2f}")
        col4.metric(
            "Session VWAP",
            f"{latest['VWAP']:,.2f}" if pd.notna(latest["VWAP"]) else "N/A",
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "5-minute SMA",
            f"{latest['SMA_5']:,.2f}" if pd.notna(latest["SMA_5"]) else "Warming up",
        )
        col2.metric(
            "10-minute SMA",
            f"{latest['SMA_10']:,.2f}" if pd.notna(latest["SMA_10"]) else "Warming up",
        )
        col3.metric(
            "5-minute EMA",
            f"{latest['EMA_5']:,.2f}" if pd.notna(latest["EMA_5"]) else "Warming up",
        )
        col4.metric(
            "10-minute EMA",
            f"{latest['EMA_10']:,.2f}" if pd.notna(latest["EMA_10"]) else "Warming up",
        )

        # Chart
        chart_data = df.tail(60).copy()
        price_columns = ["close", "VWAP", "EMA_5", "EMA_10"]
        available = [c for c in price_columns if c in chart_data.columns]

        price_min = chart_data[available].min().min()
        price_max = chart_data[available].max().max()
        price_range = price_max - price_min
        padding = max(price_range * 0.20, 0.05)
        y_min = price_min - padding
        y_max = price_max + padding

        plot_data = chart_data[["timestamp"] + available].melt(
            id_vars="timestamp", var_name="Indicator", value_name="Price"
        )

        chart = (
            alt.Chart(plot_data)
            .mark_line()
            .encode(
                x=alt.X("timestamp:T", title="Time"),
                y=alt.Y(
                    "Price:Q", title="Price", scale=alt.Scale(domain=[y_min, y_max])
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
        st.altair_chart(chart, width=True)

        with st.expander(f"{symbol} historical data"):
            st.dataframe(
                df.tail(100).sort_values("timestamp", ascending=False),
                width=True,
                hide_index=True,
            )

        st.divider()


# ============================================================
# DASHBOARD
# ============================================================

st.title("NASDAQ Live Market Monitor")

st.caption(
    "Market data: Alpaca IEX | Moving averages calculated from one-minute bars | "
    f"Session VWAP resets daily (US/Eastern) | Retention: last {RETENTION_DAYS} days"
)

# Start WebSocket (cached across Streamlit reruns)
stream.start_market_stream()
display_market()

# ---- Footer ----
st.caption(
    f"Symbols: {', '.join(SYMBOLS)} | "
    f"Database: {DATABASE} | "
    f"Feed: IEX | "
    f"Retention: {RETENTION_DAYS} days"
)
