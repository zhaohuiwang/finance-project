"""
Alpaca IEX WebSocket client that feeds one-minute bars into the databases.

A single persistent connection is started once (via Streamlit's
@st.cache_resource) and kept alive for the lifetime of the process.

The WebSocket connection itself stays open continuously.  Alpaca only
publishes one-minute bars during regular US equity market hours (and
sometimes during extended hours depending on the symbol/feed).  Outside
those windows the connection is idle but still alive – no bars arrive,
so the dashboard simply shows the last known data.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream

from .config import (
    API_KEY,
    API_SECRET,
    SYMBOLS,
    VIX_SYMBOL,
    RETENTION_INTERVAL_SECONDS,
    METRICS_ENABLED,
    METRICS_HOST,
    METRICS_PORT,
)
from .database import BarDatabase
from .status import StatusManager

logger = logging.getLogger("market_monitor.stream")

# Optional Prometheus metrics
_metrics_available = False
if METRICS_ENABLED:
    try:
        from prometheus_client import (
            Counter,
            Gauge,
            start_http_server,
        )

        BARS_RECEIVED = Counter(
            "market_monitor_bars_received_total",
            "Total number of bars received from Alpaca",
            ["symbol"],
        )
        LAST_BAR_AGE = Gauge(
            "market_monitor_last_bar_age_seconds",
            "Seconds since the most recent bar was received",
        )
        STREAM_UP = Gauge(
            "market_monitor_stream_up",
            "1 if the WebSocket thread is alive, 0 otherwise",
        )
        ERRORS = Counter(
            "market_monitor_errors_total",
            "Total number of errors while handling bars",
        )
        _metrics_available = True
    except ImportError:
        logger.warning(
            "prometheus_client not installed – metrics endpoint disabled. "
            "Install with: pip install prometheus_client"
        )


class MarketDataStream:
    """
    Manages the Alpaca StockDataStream, bar handlers, background
    retention cleanup, optional Prometheus metrics, and clean shutdown.
    """

    def __init__(
        self,
        equity_db: BarDatabase,
        vix_db: BarDatabase,
        status: StatusManager,
        symbols: list[str] | None = None,
        vix_symbol: str = VIX_SYMBOL,
    ) -> None:
        if not API_KEY or not API_SECRET:
            raise RuntimeError("Missing Alpaca API credentials. Check your .env file.")

        self.equity_db = equity_db
        self.vix_db = vix_db
        self.status = status
        self.symbols = symbols if symbols is not None else SYMBOLS
        self.vix_symbol = vix_symbol
        self.all_symbols = self.symbols + [self.vix_symbol]

        self._stream: StockDataStream | None = None
        self._stream_thread: threading.Thread | None = None
        self._retention_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started = False

    # ------------------------------------------------------------------
    # Bar handlers
    # ------------------------------------------------------------------

    async def _handle_bar(self, bar) -> None:
        """
        Normal minute bar (subject to later updates) containing
        symbol, open, high, low, close, volume, and timestamp.
        """
        try:
            if bar.symbol == self.vix_symbol:
                self.vix_db.save_bar(bar)
            else:
                self.equity_db.save_bar(bar)

            # Update shared status under the lock
            self.status.update(
                increment_bars=True,
                last_bar_time=bar.timestamp.astimezone(timezone.utc),
                last_error=None,
            )

            if _metrics_available:
                BARS_RECEIVED.labels(symbol=bar.symbol).inc()
                LAST_BAR_AGE.set(0)

        except Exception as e:
            logger.exception("Error saving market bar")
            self.status.update(
                last_error=str(e),
                last_error_time=datetime.now(timezone.utc),
            )
            if _metrics_available:
                ERRORS.inc()

    # Note: Alpaca sends updated bars when late trades change a previously
    # emitted minute bar.  The SDK treats these as a separate WebSocket
    # message type ('updatedBars').  Because the save logic is identical
    # we simply reuse the same handler for both subscriptions.

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> tuple[StockDataStream, threading.Thread]:
        """
        Initialise databases, start the WebSocket thread, the periodic
        retention thread, and (optionally) the Prometheus metrics server.
        Returns the stream object and the main stream thread so the UI
        can check liveness.
        """
        if self._started:
            logger.warning("MarketDataStream.start() called more than once")
            return self._stream, self._stream_thread  # type: ignore

        # Schema + one-shot cleanup
        self.equity_db.initialize()
        self.vix_db.initialize()
        self.equity_db.cleanup_old_bars()
        self.vix_db.cleanup_old_bars()

        self._stream = StockDataStream(API_KEY, API_SECRET, feed=DataFeed.IEX)
        self._stream.subscribe_bars(self._handle_bar, *self.all_symbols)
        self._stream.subscribe_updated_bars(self._handle_bar, *self.all_symbols)

        def run_stream() -> None:
            try:
                logger.info("Starting Alpaca WebSocket...")
                if _metrics_available:
                    STREAM_UP.set(1)
                self._stream.run()
            except Exception as e:
                logger.exception("Market stream stopped unexpectedly")
                self.status.update(
                    last_error=str(e),
                    last_error_time=datetime.now(timezone.utc),
                )
            finally:
                if _metrics_available:
                    STREAM_UP.set(0)

        def run_retention() -> None:
            """
            Delete bars older than the configured retention on a schedule.
            The loop exits cleanly when stop() is called.
            """
            while not self._stop_event.is_set():
                try:
                    self.equity_db.cleanup_old_bars()
                    self.vix_db.cleanup_old_bars()
                except Exception:
                    logger.exception("Periodic retention cleanup failed")
                # Wait in small increments so we can react to stop() quickly
                self._stop_event.wait(RETENTION_INTERVAL_SECONDS)

        def run_metrics_updater() -> None:
            """Keep the last-bar-age gauge up to date."""
            while not self._stop_event.is_set():
                last = self.status.last_bar_time
                if last is not None and _metrics_available:
                    age = (datetime.now(timezone.utc) - last).total_seconds()
                    LAST_BAR_AGE.set(age)
                self._stop_event.wait(5)

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

        if _metrics_available:
            try:
                start_http_server(METRICS_PORT, addr=METRICS_HOST)
                logger.info(
                    "Prometheus metrics available at http://%s:%s/metrics",
                    METRICS_HOST,
                    METRICS_PORT,
                )
                metrics_thread = threading.Thread(
                    target=run_metrics_updater,
                    daemon=True,
                    name="metrics-updater",
                )
                metrics_thread.start()
            except OSError as e:
                logger.warning("Could not start metrics server: %s", e)

        # Register clean shutdown for normal process exit
        atexit.register(self.stop)
        self._started = True

        return self._stream, self._stream_thread

    def stop(self) -> None:
        """
        Request a clean shutdown of background threads and the Alpaca stream.

        Safe to call multiple times.  Because the Alpaca SDK's run() method
        is blocking and does not expose a public close() that works from
        another thread in all versions, we rely on daemon threads + the
        stop event for retention/metrics.  The process exit will terminate
        the WebSocket thread.
        """
        if not self._started:
            return
        logger.info("Shutting down MarketDataStream...")
        self._stop_event.set()
        if _metrics_available:
            STREAM_UP.set(0)
        self._started = False

    @property
    def stream_thread(self) -> Optional[threading.Thread]:
        return self._stream_thread

    @property
    def is_running(self) -> bool:
        return (
            self._stream_thread is not None
            and self._stream_thread.is_alive()
            and not self._stop_event.is_set()
        )
