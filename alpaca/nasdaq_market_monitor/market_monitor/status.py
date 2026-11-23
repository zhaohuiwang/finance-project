"""
Thread-safe status tracking for the live market stream.

The WebSocket thread and the Streamlit UI thread both need to read / write
the same small set of runtime metrics.  A simple lock-protected dict keeps
everything consistent without introducing heavier concurrency primitives.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any


class StatusManager:
    """
    Holds a handful of shared runtime values that the dashboard displays
    (last bar time, error messages, bar counter, etc.).

    All mutations go through `update()` so the lock is always held.
    """

    def __init__(self) -> None:
        self._status: dict[str, Any] = {
            "last_bar_time": None,      # UTC datetime of most recent bar
            "last_error": None,         # last exception message
            "last_error_time": None,
            "bars_received": 0,
        }
        # Only one thread at a time executes a particular section of code.
        self._lock = threading.Lock()

    def update(self, *, increment_bars: bool = False, **kwargs: Any) -> None:
        """
        Atomically update one or more status fields.

        Parameters
        ----------
        increment_bars :
            When True, the bars_received counter is increased by one under
            the lock.  This avoids the classic "lost update" race that would
            occur if the read-modify-write happened outside the lock.
        **kwargs :
            Any other status keys to overwrite.
        """
        with self._lock:
            if increment_bars:
                self._status["bars_received"] += 1
            self._status.update(kwargs)

    def get(self) -> dict[str, Any]:
        """Return a shallow copy of the current status snapshot."""
        with self._lock:
            return dict(self._status)

    # Convenience accessors -------------------------------------------------

    @property
    def bars_received(self) -> int:
        with self._lock:
            return self._status["bars_received"]

    @property
    def last_bar_time(self) -> datetime | None:
        with self._lock:
            return self._status["last_bar_time"]

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._status["last_error"]
