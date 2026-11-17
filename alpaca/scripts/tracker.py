
"""
This application:
    Connects to Alpaca's IEX WebSocket.
    Subscribes to one-minute bars.
    Processes updated bars.
    Calculates SMA and EMA.
    Stores bars in SQLite.
    Displays the latest prices and indicators.
    Refreshes the dashboard every two seconds.

Run the application:
streamlit run scripts/tracker.py

http://localhost:8501

"""






import os
import sqlite3
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from dotenv import load_dotenv
from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream


# ============================================================
# CONFIGURATION
# ============================================================

SYMBOLS = "QQQ,NVDA,AAPL"
DATABASE = "outputs/market_data.db"
PERIODS = [5, 10, 15, 30, 60]


SYMBOLS = [
    s.strip().upper()
    for s in SYMBOLS.split(",")
    if s.strip()
]

DB_PATH = Path("output/market_data.db")
if not DB_PATH.exists():
    # parents=True creates any missing parent folders; exist_ok=True prevents errors if the folder already exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

if not API_KEY or not API_SECRET:
    st.error("Missing Alpaca API credentials. Check your .env file.")
    st.stop()


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=15)


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


def save_bar(bar):
    """Insert or update a one-minute bar."""

    timestamp = bar.timestamp.astimezone(
        timezone.utc
    ).isoformat()

    with get_connection() as conn:
        conn.execute("""
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
        """, (
            bar.symbol,
            timestamp,
            float(bar.open),
            float(bar.high),
            float(bar.low),
            float(bar.close),
            float(bar.volume),
            int(bar.trade_count or 0),
            float(bar.vwap or 0),
        ))


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
            params=(symbol, limit)
        )

    if df.empty:
        return df

    df = df.sort_values("timestamp").reset_index(drop=True)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True
    )

    return df


# ============================================================
# MOVING AVERAGE CALCULATIONS
# ============================================================

def calculate_indicators(df):
    if df.empty:
        return df

    df = df.copy()

    # Moving averages over one-minute closing prices
    for period in PERIODS:

        df[f"SMA_{period}"] = (
            df["close"].rolling(
                window=period,
                min_periods=period
            ).mean()
        )

        df[f"EMA_{period}"] = (
            df["close"].ewm(
                span=period,
                adjust=False,
                min_periods=period
            ).mean()
        )

    return df


# ============================================================
# ALPACA WEBSOCKET
# ============================================================

async def handle_bar(bar):
    try:
        save_bar(bar)

        logging.info(
            "%s | %s | Close: %.2f | Volume: %s",
            bar.symbol,
            bar.timestamp,
            bar.close,
            bar.volume
        )

    except Exception:
        logging.exception("Error saving market bar")


async def handle_updated_bar(bar):
    """
    Alpaca sends updated bars when late trades
    change a previously emitted minute bar.
    """

    try:
        save_bar(bar)

    except Exception:
        logging.exception("Error updating market bar")


@st.cache_resource
def start_market_stream():
    """
    Start one persistent WebSocket connection.
    Streamlit reruns will reuse this connection.
    """

    initialize_database()

    stream = StockDataStream(
        API_KEY,
        API_SECRET,
        feed=DataFeed.IEX
    )

    stream.subscribe_bars(
        handle_bar,
        *SYMBOLS
    )

    stream.subscribe_updated_bars(
        handle_updated_bar,
        *SYMBOLS
    )

    def run_stream():
        try:
            logging.info("Starting Alpaca WebSocket...")
            stream.run()

        except Exception:
            logging.exception("Market stream stopped unexpectedly")

    thread = threading.Thread(
        target=run_stream,
        daemon=True,
        name="alpaca-market-stream"
    )

    thread.start()

    return stream, thread


# ============================================================
# DASHBOARD
# ============================================================

st.set_page_config(
    page_title="NASDAQ Market Monitor",
    page_icon="📈",
    layout="wide"
)

st.title("NASDAQ Live Market Monitor")

st.caption(
    "Market data: Alpaca IEX | "
    "Moving averages calculated from one-minute bars"
)

# Start WebSocket
stream, stream_thread = start_market_stream()

st.success("Market data stream started")

st.info(
    "This dashboard uses IEX exchange data, not "
    "the consolidated US market feed."
)


# ============================================================
# LIVE DISPLAY
# ============================================================

@st.fragment(run_every="2s")
def display_market():

    summary = []

    for symbol in SYMBOLS:

        df = get_bars(symbol)

        if df.empty:
            continue

        df = calculate_indicators(df)

        latest = df.iloc[-1]

        row = {
            "Symbol": symbol,
            "Last Price": latest["close"],
            "Last Bar (UTC)": latest["timestamp"],
            "Bars Available": len(df),
        }

        for period in PERIODS:
            row[f"SMA {period}m"] = latest[f"SMA_{period}"]
            row[f"EMA {period}m"] = latest[f"EMA_{period}"]

        summary.append(row)

    if not summary:
        st.warning(
            "Waiting for market data. "
            "Indicators will appear as bars accumulate."
        )
        return

    result = pd.DataFrame(summary)

    st.subheader("Current Market Indicators")

    st.dataframe(
        result,
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "SMA/EMA values are based on completed one-minute bars. "
        "The dashboard refreshes every two seconds, but new "
        "market bars normally arrive once per minute."
    )

    st.divider()

    st.subheader("Individual Stock Details")

    for symbol in SYMBOLS:

        df = get_bars(symbol)

        if df.empty:
            continue

        df = calculate_indicators(df)

        st.markdown(f"### {symbol}")

        latest = df.iloc[-1]

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Latest Price",
            f"${latest['close']:,.2f}"
        )

        col2.metric(
            "5-minute SMA",
            f"${latest['SMA_5']:,.2f}"
            if pd.notna(latest["SMA_5"])
            else "Warming up"
        )

        col3.metric(
            "10-minute SMA",
            f"${latest['SMA_10']:,.2f}"
            if pd.notna(latest["SMA_10"])
            else "Warming up"
        )

        chart_data = df.set_index("timestamp")[
            ["close", "SMA_5", "SMA_10", "SMA_15", "SMA_30"]
        ]

        st.line_chart(
            chart_data,
            height=250
        )

        with st.expander(f"{symbol} historical data"):

            st.dataframe(
                df.tail(100).sort_values(
                    "timestamp",
                    ascending=False
                ),
                use_container_width=True,
                hide_index=True
            )

        st.divider()


display_market()


# ============================================================
# FOOTER
# ============================================================

st.caption(
    f"Symbols: {', '.join(SYMBOLS)} | "
    f"Database: {DB_PATH} | "
    f"Feed: IEX"
)
