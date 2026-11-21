"""
Configuration for the NASDAQ Live Market Monitor.

All tunables are loaded from ``config.toml`` (next to tracker.py) so operators
can change symbols, periods, retention, etc. without touching Python code.
Environment variables still supply the Alpaca API credentials.
"""

from __future__ import annotations

import os
import logging
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Locate & load config.toml
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"

if not _CONFIG_PATH.exists():
    raise FileNotFoundError(
        f"Configuration file not found: {_CONFIG_PATH}\n"
        "Create config.toml next to tracker.py (see the example in the repo)."
    )

with _CONFIG_PATH.open("rb") as f:
    _raw = tomllib.load(f)

# ---------------------------------------------------------------------------
# Symbols & Indicators
# ---------------------------------------------------------------------------

SYMBOLS: list[str] = list(_raw["symbols"]["equity"])
VIX_SYMBOL: str = str(_raw["symbols"]["vix"])

PERIODS: list[int] = [int(p) for p in _raw["indicators"]["periods"]]

# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

RETENTION_DAYS: int = int(_raw["retention"]["equity_days"])
VIX_RETENTION_DAYS: int = int(_raw["retention"]["vix_days"])

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------

EASTERN = ZoneInfo("America/New_York")

# ---------------------------------------------------------------------------
# Database paths
# ---------------------------------------------------------------------------

DATABASE = Path(_raw["database"]["equity_path"])
VIX_DATABASE = Path(_raw["database"]["vix_path"])

DATABASE.parent.mkdir(parents=True, exist_ok=True)
VIX_DATABASE.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Stream / UI timing
# ---------------------------------------------------------------------------

UI_REFRESH_SECONDS: int = int(_raw["stream"]["ui_refresh_seconds"])
RETENTION_INTERVAL_SECONDS: int = int(_raw["stream"]["retention_interval_seconds"])
IDLE_AFTER_SECONDS: int = int(_raw["stream"].get("idle_after_seconds", 120))

# ---------------------------------------------------------------------------
# Prometheus metrics (optional)
# ---------------------------------------------------------------------------

METRICS_ENABLED: bool = bool(_raw.get("metrics", {}).get("enabled", False))
METRICS_HOST: str = str(_raw.get("metrics", {}).get("host", "0.0.0.0"))
METRICS_PORT: int = int(_raw.get("metrics", {}).get("port", 9100))

# ---------------------------------------------------------------------------
# Alpaca credentials (still from environment / .env)
# ---------------------------------------------------------------------------

load_dotenv()

API_KEY: str | None = os.getenv("ALPACA_API_KEY")
API_SECRET: str | None = os.getenv("ALPACA_API_SECRET_KEY")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("market_monitor")
