"""
NASDAQ Live Market Monitor – Streamlit entry point.

This application:
    Connects to Alpaca's IEX WebSocket.
    Subscribes to one-minute bars.
    Processes updated bars.
    Calculates SMA and EMA.
    Stores equity bars in one SQLite DB and VIX bars in a separate DB.
    Displays the latest prices and indicators.
    Refreshes the dashboard every two seconds.

SMA:    Simple Moving Average (arithmetic mean).
EMA:    Exponential Moving Average (weighted arithmetic mean).
VWAP:   Volume-Weighted Average Price (volume-weighted arithmetic mean).

Run:
    streamlit run nasdaq_market_monitor/tracker.py

http://localhost:8501
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import timedelta

import streamlit as st

# Ensure the package is importable when the script is launched via
#   streamlit run tracker.py
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from market_monitor.config import (
    SYMBOLS,
    VIX_SYMBOL,
    RETENTION_DAYS,
    VIX_RETENTION_DAYS,
    DATABASE,
    VIX_DATABASE,
    API_KEY,
    API_SECRET,
    UI_REFRESH_SECONDS,
    METRICS_ENABLED,
    METRICS_PORT,
)
from market_monitor.database import BarDatabase
from market_monitor.indicators import IndicatorCalculator
from market_monitor.signals import EquitySignalCalculator, VixSignalCalculator
from market_monitor.status import StatusManager
from market_monitor.stream import MarketDataStream
from market_monitor.ui import display_market

# ---------------------------------------------------------------------------
# Early credential check (fails fast with a clear message)
# ---------------------------------------------------------------------------
if not API_KEY or not API_SECRET:
    st.error("Missing Alpaca API credentials. Check your .env file.")
    st.stop()

# ---------------------------------------------------------------------------
# Page configuration (must be the first Streamlit command)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NASDAQ Market Monitor",
    page_icon="📈",
    layout="wide",
)

st.title("NASDAQ Live Market Monitor")

st.caption(
    "Market data: Alpaca IEX | Moving averages from one-minute bars | "
    f"Session VWAP resets daily (US/Eastern) | "
    f"Equity retention: {RETENTION_DAYS} days | "
    f"VIX retention: {VIX_RETENTION_DAYS} days"
)

# ---------------------------------------------------------------------------
# Dependency wiring – created once and reused across Streamlit reruns
# ---------------------------------------------------------------------------


@st.cache_resource
def _bootstrap() -> tuple[
    BarDatabase,
    BarDatabase,
    StatusManager,
    MarketDataStream,
    IndicatorCalculator,
    EquitySignalCalculator,
    VixSignalCalculator,
]:
    """
    Initialise all long-lived objects.

    Using @st.cache_resource guarantees that the WebSocket connection and
    the background threads are started only once, even though Streamlit
    re-executes the script on every interaction / timer tick.
    """
    equity_db = BarDatabase(DATABASE, RETENTION_DAYS)
    vix_db = BarDatabase(VIX_DATABASE, VIX_RETENTION_DAYS)
    status = StatusManager()

    stream = MarketDataStream(
        equity_db=equity_db,
        vix_db=vix_db,
        status=status,
    )
    stream.start()

    indicator_calc = IndicatorCalculator()
    equity_signal_calc = EquitySignalCalculator()
    vix_signal_calc = VixSignalCalculator()

    return (
        equity_db,
        vix_db,
        status,
        stream,
        indicator_calc,
        equity_signal_calc,
        vix_signal_calc,
    )


(
    equity_db,
    vix_db,
    status,
    stream,
    indicator_calc,
    equity_signal_calc,
    vix_signal_calc,
) = _bootstrap()

# ---------------------------------------------------------------------------
# Live dashboard (auto-refreshes every 2 seconds)
# ---------------------------------------------------------------------------


@st.fragment(run_every=timedelta(seconds=UI_REFRESH_SECONDS))
def _live_dashboard() -> None:
    display_market(
        equity_db=equity_db,
        vix_db=vix_db,
        status=status,
        stream=stream,
        indicator_calc=indicator_calc,
        equity_signal_calc=equity_signal_calc,
        vix_signal_calc=vix_signal_calc,
    )


_live_dashboard()

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
metrics_note = (
    f" | Metrics: http://localhost:{METRICS_PORT}/metrics" if METRICS_ENABLED else ""
)
st.caption(
    f"Symbols: {', '.join(SYMBOLS)} + {VIX_SYMBOL} | "
    f"Equity DB: {DATABASE} | VIX DB: {VIX_DATABASE} | "
    f"Feed: IEX{metrics_note}"
)
