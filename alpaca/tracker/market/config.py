"""Configuration and constants."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# ---- Symbols & indicators ----
SYMBOLS = [
    "QQQ",
    "AAPL",
    "INTC",
    "NBIS",
    "NVDA",
    "SNDK",
]

PERIODS = [5, 10, 15, 30, 60]
RETENTION_DAYS = 7
EASTERN = ZoneInfo("America/New_York")

# ---- Paths ----
DATABASE = Path("outputs/market_data.db")
DATABASE.parent.mkdir(parents=True, exist_ok=True)

# ---- Alpaca credentials ----
API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")
