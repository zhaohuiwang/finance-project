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
EMA:    Exponential Moving Average (weighted arithmetic mean).
VWAP:   Volume-Weighted Average Price (volume-weighted arithmetic mean).

Run the application:
streamlit run scripts/tracker.py

http://localhost:8501
"""

import os
import sqlite3
import threading
import logging
import time
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
    "QQQ",  # ← Nasdaq 100 Index ETF (QQQ)
    "AAPL",
    "INTC",
    "NBIS",
    "NVDA",
    "SNDK",
]

DATABASE = Path("outputs/market_data.db")
PERIODS = [5, 10, 15, 30, 60]
RETENTION_DAYS = 7  # keep only this many calendar days
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
    "last_bar_time": None,  # UTC datetime of most recent bar
    "last_error": None,  # last exception message
    "last_error_time": None,
    "bars_received": 0,
}
# Only one thread at a time executes a particular section of code.
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
        logging.info(
            "Retention cleanup: removed %s old bars (older than %s days)", deleted, days
        )
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
        last_error=None,
    )

    with _status_lock:
        _status["bars_received"] += 1

    # Note: `bars_received=_status["bars_received"] + 1,` Do not simply put this statement inside the update_status(). It can lose increments under concurrent bar arrivals, as _status["bars_received"] read outside the lock. You start a dedicated background thread:
    # stream = StockDataStream(API_KEY, API_SECRET, feed=DataFeed.IEX)
    # stream.subscribe_bars(handle_bar, *SYMBOLS)
    # stream.subscribe_updated_bars(handle_updated_bar, *SYMBOLS)
    # stream.run() # --->>>  as in  def run_stream():
    # thread = threading.Thread(target=run_stream, daemon=True, name="alpaca-market-stream")
    # Inside that thread the Alpaca StockDataStream receives messages and calls your handlers:
    # async def handle_bar(bar): ...
    # async def handle_updated_bar(bar): ...
    # Those handlers both call save_bar → update_status(...). Even though the handlers are marked async, the underlying WebSocket library can deliver multiple bars (or an original bar + an updated bar) in rapid succession. When that happens, two (or more) calls to save_bar can be in flight at the same time and both try to do:
    # bars_received = _status["bars_received"] + 1
    # Because the read happens before the lock is acquired, both can see the same value, both compute the same new value, and one of the increments is lost.That’s the classic “lost update” race.


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
        (typical_price * df["volume"]).groupby(df["_session_date"]).cumsum()
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
    """Normal miniute bar which is subject to change or update, containing symbol, open, high, low, close, volume, and timestamp."""
    try:
        save_bar(bar)
    except Exception as e:
        logging.exception("Error saving market bar")
        update_status(
            last_error=str(e),
            last_error_time=datetime.now(timezone.utc),
        )


async def handle_updated_bar(bar):
    """Alpaca sends updated bars when late trades change a previously emitted minute bar. Alpaca's SDK internally treats these as separate WebSocket message types: 'bars' versus 'updatedBars'"""
    try:
        save_bar(bar)
    except Exception as e:
        logging.exception("Error updating market bar")
        update_status(
            last_error=str(e),
            last_error_time=datetime.now(timezone.utc),
        )


# Note: You can collapse the above two functions as they have the idential logic here. Keeping two separate functions is only useful if you later want different logic (logging, metrics, etc.) for original vs. updated bars.


@st.cache_resource
def start_market_stream():
    """
    Start one persistent WebSocket connection.
    Streamlit reruns will reuse this connection.
    """
    initialize_database()
    cleanup_old_bars(RETENTION_DAYS)  # run retention on startup

    stream = StockDataStream(API_KEY, API_SECRET, feed=DataFeed.IEX)

    # Receive the normal minute bars
    stream.subscribe_bars(handle_bar, *SYMBOLS)

    # Receive updates/corrections to previously emitted minute bars
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

    def run_retention():
        """Delete bars older than RETENTION_DAYS every hour. `while True:` ensures the block run repeatedly, for as long as the program is running. try/except block ensures no exception termination. """
        while True:
            try:
                cleanup_old_bars(RETENTION_DAYS)
            except Exception as e:
                logging.exception(f"Periodic retention cleanup failed: {e}")
            
            time.sleep(60 * 60)  # every 60 minutes

    thread = threading.Thread(
        target=run_stream, daemon=True, name="alpaca-market-stream"
    )
    thread.start()

    retention_thread = threading.Thread(
        target=run_retention, daemon=True, name="retention-cleanup"
    )
    retention_thread.start()

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

    st.info(
        "This dashboard uses IEX exchange data, not the consolidated US market feed."
    )

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
        # If separate cells
        #     for period in PERIODS:
        #         row[f"SMA {period}m"] = latest[f"SMA_{period}"]
        #         row[f"EMA {period}m"] = latest[f"EMA_{period}"]

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
        width="stretch",  # makes the whole table use the available page width
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn(
                "Symbol",
                pinned=True,  # stay even when you move the slide bar
                # width="small" # config individual column widths
            ),
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
