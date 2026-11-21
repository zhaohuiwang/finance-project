
"""Alpaca WebSocket stream and shared status."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import streamlit as st
from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream

from .config import API_KEY, API_SECRET, SYMBOLS, RETENTION_DAYS
from . import db

logger = logging.getLogger(__name__)


class MarketStream:
    """
    Manages the Alpaca IEX WebSocket connection, bar handlers,
    shared status, and background retention cleanup.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbols: list[str],
        feed: DataFeed = DataFeed.IEX,
    ):
        if not api_key or not api_secret:
            raise ValueError("Alpaca API key and secret are required")

        self.api_key = api_key
        self.api_secret = api_secret
        self.symbols = symbols
        self.feed = feed

        self._stream: Optional[StockDataStream] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._retention_thread: Optional[threading.Thread] = None

        # Shared status (protected by lock)
        self._status = {
            "last_bar_time": None,
            "last_error": None,
            "last_error_time": None,
            "bars_received": 0,
        }
        self._status_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def update_status(self, *, increment_bars: bool = False, **kwargs) -> None:
        with self._status_lock:
            if increment_bars:
                self._status["bars_received"] += 1
            self._status.update(kwargs)

    def get_status(self) -> dict:
        with self._status_lock:
            return dict(self._status)

    def is_alive(self) -> bool:
        return self._stream_thread is not None and self._stream_thread.is_alive()

    # ------------------------------------------------------------------
    # Bar handler
    # ------------------------------------------------------------------
    async def _handle_bar(self, bar) -> None:
        """Handles both original minute bars and updated bars."""
        try:
            db.save_bar(bar)
            self.update_status(
                last_bar_time=bar.timestamp.astimezone(timezone.utc),
                last_error=None,
                increment_bars=True,
            )
        except Exception as e:
            logger.exception("Error saving/updating market bar")
            self.update_status(
                last_error=str(e),
                last_error_time=datetime.now(timezone.utc),
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """
        Initialize database, subscribe, and start background threads.
        Safe to call multiple times; subsequent calls are no-ops if already running.
        """
        if self.is_alive():
            logger.info("MarketStream already running")
            return

        db.initialize_database()
        db.cleanup_old_bars(RETENTION_DAYS)

        self._stream = StockDataStream(
            self.api_key,
            self.api_secret,
            feed=self.feed,
        )

        # Both original and updated bars share the same handler
        self._stream.subscribe_bars(self._handle_bar, *self.symbols)
        self._stream.subscribe_updated_bars(self._handle_bar, *self.symbols)

        def run_stream():
            try:
                logger.info("Starting Alpaca WebSocket...")
                self._stream.run()
            except Exception as e:
                logger.exception("Market stream stopped unexpectedly")
                self.update_status(
                    last_error=str(e),
                    last_error_time=datetime.now(timezone.utc),
                )

        def run_retention():
            """Delete bars older than RETENTION_DAYS every hour. `while True:` ensures the block run repeatedly, for as long as the program is running. try/except block ensures no exception termination. """
            while True:
                try:
                    db.cleanup_old_bars(RETENTION_DAYS)
                except Exception as e:
                    logger.exception(f"Periodic retention cleanup failed: {e}")

                time.sleep(60 * 60)  # every hour

        self._stream_thread = threading.Thread(
            target=run_stream,
            daemon=True,
            name="alpaca-market-stream",
        )
        self._stream_thread.start()

        self._retention_thread = threading.Thread(
            target=run_retention,
            daemon=True,
            name="retention-cleanup",
        )
        self._retention_thread.start()

        logger.info("MarketStream started for symbols: %s", ", ".join(self.symbols))


# ------------------------------------------------------------------
# Streamlit-friendly singleton
# ------------------------------------------------------------------
@st.cache_resource
def get_market_stream() -> MarketStream:
    """
    Return a cached MarketStream instance.
    Streamlit reruns will reuse the same object and its background threads.
    """
    stream = MarketStream(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbols=SYMBOLS,
        feed=DataFeed.IEX,
    )
    stream.start()
    return stream
