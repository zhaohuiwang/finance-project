"""
This application:
    Connects to Alpaca's IEX WebSocket.
    Subscribes to one-minute bars.
    Processes updated bars.
    Calculates SMA and EMA.
    Stores bars in SQLite (with retention).
    Displays the latest prices and indicators.
    Refreshes the dashboard every two seconds.

SMA:    Simple Moving Average (arithmetic mean).
EMA:    Simple Moving Average (weighted arithmetic mean).
VWAP:   Volume-Weighted Average Price (volume-weighted arithmetic mean). 

Run the application:
streamlit run scripts/tracker.py

http://localhost:8501
"""

import os
import sqlite3
import threading
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import altair as alt

from dotenv import load_dotenv
from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream

# ============================================================
# CONFIGURATION
# ============================================================

SYMBOLS = [
    "QQQ", # ← this is the Nasdaq-100 proxy
    "AAPL",
    "INTC",
    "NBIS",
    "NVDA",
]

DATABASE = Path("outputs/market_data.db")
PERIODS = [5, 10, 15, 30, 60]
RETENTION_DAYS = 7                    # keep only this many calendar days
EASTERN = ZoneInfo("America/New_York")

DATABASE.parent.mkdir(parents=True, exist_ok=True)

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if not API_KEY or not API_SECRET:
    st.error("Missing Alpaca API credentials. Check your .env file.")
    st.stop()


# Shared status visible to both the WebSocket thread and the UI
_status = {
    "last_bar_time": None,       # UTC datetime of most recent bar
    "last_error": None,          # last exception message
    "last_error_time": None,
    "bars_received": 0,
}
_status_lock = threading.Lock()


def update_status(**kwargs):
    with _status_lock:
        _status.update(kwargs)


def get_status():
    with _status_lock:
        return dict(_status)


# ============================================================
# DATABASE
# ============================================================


def get_connection():
    """
    WAL mode is particularly useful here because the dashboard is
    continuously reading while the WebSocket is writing.
    """
    conn = sqlite3.connect(DATABASE, timeout=15, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_bars (
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                trade_count INTEGER,
                vwap REAL,
                PRIMARY KEY (symbol, timestamp)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_symbol_time
            ON market_bars(symbol, timestamp)
        """)


def cleanup_old_bars(days: int = RETENTION_DAYS):
    """Delete bars older than `days` calendar days (UTC)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM market_bars WHERE timestamp < ?",
            (cutoff,),
        )
        deleted = cur.rowcount
    if deleted:
        logging.info("Retention cleanup: removed %s old bars (older than %s days)", deleted, days)
    return deleted


def save_bar(bar):
    """Insert or update a one-minute bar."""
    timestamp = bar.timestamp.astimezone(timezone.utc).isoformat()

    trade_count = int(bar.trade_count) if bar.trade_count is not None else None
    vwap = float(bar.vwap) if bar.vwap is not None else None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO market_bars (
                symbol, timestamp, open, high, low,
                close, volume, trade_count, vwap
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timestamp)
            DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                trade_count = excluded.trade_count,
                vwap = excluded.vwap
            """,
            (
                bar.symbol,
                timestamp,
                float(bar.open),
                float(bar.high),
                float(bar.low),
                float(bar.close),
                float(bar.volume),
                trade_count,
                vwap,
            ),
        )

    # Update shared status
    update_status(
        last_bar_time=bar.timestamp.astimezone(timezone.utc),
        bars_received=_status["bars_received"] + 1,
        last_error=None,
    )


def get_bars(symbol, limit=500):
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM market_bars
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            conn,
            params=(symbol, limit),
        )

    if df.empty:
        return df

    df = df.sort_values("timestamp").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


# ============================================================
# MOVING AVERAGE + SESSION VWAP CALCULATIONS
# ============================================================


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    # ----------- Moving averages -----------
    for period in PERIODS:
        df[f"SMA_{period}"] = (
            df["close"].rolling(window=period, min_periods=period).mean()
        )
        df[f"EMA_{period}"] = (
            df["close"].ewm(span=period, adjust=False, min_periods=period).mean()
        )

    # ----------- Session VWAP (resets each calendar day in US/Eastern) -----------
    # Convert to Eastern so the daily boundary matches the regular trading session
    eastern_ts = df["timestamp"].dt.tz_convert(EASTERN)
    df["_session_date"] = eastern_ts.dt.date

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0

    # Cumulative volume and cumulative (typical_price * volume) within each session day
    df["_cum_vol"] = df.groupby("_session_date")["volume"].cumsum()
    df["_cum_tp_vol"] = (
        (typical_price * df["volume"])
        .groupby(df["_session_date"])
        .cumsum()
    )

    df["VWAP"] = df["_cum_tp_vol"] / df["_cum_vol"]

    # Clean up helper columns
    df = df.drop(columns=["_session_date", "_cum_vol", "_cum_tp_vol"])

    return df


# ============================================================
# SIGNAL CALCULATIONS
# ============================================================


def calculate_signal(df: pd.DataFrame) -> dict:
    """
    Calculate a simple bullish / neutral / bearish signal.

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


# ============================================================
# ALPACA WEBSOCKET
# ============================================================

async def handle_bar(bar):
    try:
        save_bar(bar)
    except Exception as e:
        logging.exception("Error saving market bar")
        update_status(
            last_error=str(e),
            last_error_time=datetime.now(timezone.utc),
        )


async def handle_updated_bar(bar):
    """Alpaca sends updated bars when late trades change a previously emitted minute bar."""
    try:
        save_bar(bar)
    except Exception as e:
        logging.exception("Error updating market bar")
        update_status(
            last_error=str(e),
            last_error_time=datetime.now(timezone.utc),
        )


@st.cache_resource
def start_market_stream():
    """
    Start one persistent WebSocket connection.
    Streamlit reruns will reuse this connection.
    """
    initialize_database()
    cleanup_old_bars(RETENTION_DAYS)          # run retention on startup

    stream = StockDataStream(API_KEY, API_SECRET, feed=DataFeed.IEX)

    stream.subscribe_bars(handle_bar, *SYMBOLS)
    stream.subscribe_updated_bars(handle_updated_bar, *SYMBOLS)

    def run_stream():
        try:
            logging.info("Starting Alpaca WebSocket...")
            stream.run()
        except Exception as e:
            logging.exception("Market stream stopped unexpectedly")
            update_status(
                last_error=str(e),
                last_error_time=datetime.now(timezone.utc),
            )

    thread = threading.Thread(
        target=run_stream, daemon=True, name="alpaca-market-stream"
    )
    thread.start()

    return stream, thread



# ============================================================
# LIVE DISPLAY
# ============================================================
@st.fragment(run_every=timedelta(seconds=2))
def display_market():

    # ---- Status bar ----
    status = get_status()
    col_a, col_b, col_c = st.columns([2, 2, 3])

    with col_a:
        if stream_thread.is_alive():
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

    st.info("This dashboard uses IEX exchange data, not the consolidated US market feed.")

    # ---- Summary table and individual stock details ----
    summary = []

    for symbol in SYMBOLS:
        df = get_bars(symbol)
        if df.empty:
            continue

        df = calculate_indicators(df)
        latest = df.iloc[-1]
        signal = calculate_signal(df)

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
            "Last Bar (UTC)": latest["timestamp"],
        }

        for period in PERIODS:
            row[f"SMA {period}m"] = latest[f"SMA_{period}"]
            row[f"EMA {period}m"] = latest[f"EMA_{period}"]

        summary.append(row)

    if not summary:
        st.warning("Waiting for market data. Indicators will appear as bars accumulate.")
        return

    result = pd.DataFrame(summary)

    preferred_order = [
        "Symbol", "Last Price", "Signal", "Score", "VWAP",
        "Price vs VWAP", "EMA Alignment", "Crossover", "Bars", "Last Bar (UTC)",
    ] + [c for c in result.columns if c not in {
        "Symbol", "Last Price", "Signal", "Score", "VWAP",
        "Price vs VWAP", "EMA Alignment", "Crossover", "Bars", "Last Bar (UTC)"
    }]

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
        width="stretch",
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", pinned=True, width="small"),
            "Last Price": st.column_config.NumberColumn("Last Price", format="$%.2f"),
            "VWAP": st.column_config.NumberColumn("VWAP", format="$%.2f"),
            "Score": st.column_config.NumberColumn("Score", format="%d"),
            "Bars": st.column_config.NumberColumn("Bars", format="%d"),
            "Last Bar (UTC)": st.column_config.DatetimeColumn("Last Bar (UTC)", format="HH:mm:ss"),
            **{f"SMA {p}m": st.column_config.NumberColumn(f"SMA {p}m", format="$%.2f") for p in PERIODS},
            **{f"EMA {p}m": st.column_config.NumberColumn(f"EMA {p}m", format="$%.2f") for p in PERIODS},
        },
    )

    st.caption(
        "SMA/EMA values are based on completed one-minute bars. "
        "Session VWAP resets at the start of each calendar day (US/Eastern). "
        "The dashboard refreshes every two seconds; new bars normally arrive once per minute."
    )

    st.divider()

    # Individual stock details
    st.subheader("Individual Stock Details")

    for symbol in SYMBOLS:
        df = get_bars(symbol)
        if df.empty:
            continue

        df = calculate_indicators(df)
        latest = df.iloc[-1]
        signal = calculate_signal(df)

        st.markdown(f"### {symbol}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Signal", signal["signal"])
        col2.metric("Score", signal["score"] if signal["score"] is not None else "—")
        col3.metric("Latest Price", f"${latest['close']:,.2f}")
        col4.metric(
            "Session VWAP",
            f"${latest['VWAP']:,.2f}" if pd.notna(latest["VWAP"]) else "N/A",
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("5-minute SMA", f"${latest['SMA_5']:,.2f}" if pd.notna(latest["SMA_5"]) else "Warming up")
        col2.metric("10-minute SMA", f"${latest['SMA_10']:,.2f}" if pd.notna(latest["SMA_10"]) else "Warming up")
        col3.metric("5-minute EMA", f"${latest['EMA_5']:,.2f}" if pd.notna(latest["EMA_5"]) else "Warming up")
        col4.metric("10-minute EMA", f"${latest['EMA_10']:,.2f}" if pd.notna(latest["EMA_10"]) else "Warming up")

        # Chart
        chart_data = df.tail(60).copy()
        price_columns = ["close", "VWAP", "SMA_5", "SMA_10", "EMA_5", "EMA_10"]
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
                y=alt.Y("Price:Q", title="Price", scale=alt.Scale(domain=[y_min, y_max])),
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


# ============================================================
# DASHBOARD
# ============================================================

st.set_page_config(page_title="NASDAQ Market Monitor", page_icon="📈", layout="wide")

st.title("NASDAQ Live Market Monitor")

st.caption(
    "Market data: Alpaca IEX | Moving averages calculated from one-minute bars | "
    f"Session VWAP resets daily (US/Eastern) | Retention: last {RETENTION_DAYS} days"
)

# Start WebSocket
stream, stream_thread = start_market_stream()
display_market()


# ============================================================
# FOOTER
# ============================================================

st.caption(
    f"Symbols: {', '.join(SYMBOLS)} | "
    f"Database: {DATABASE} | "
    f"Feed: IEX | "
    f"Retention: {RETENTION_DAYS} days"
)