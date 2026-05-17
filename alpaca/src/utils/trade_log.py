import csv
import os
from datetime import datetime

import pytz

from utils.logger import get_logger

logger = get_logger(__name__)

_NY_TZ = pytz.timezone("America/New_York")


def init_trade_log(log_file: str) -> None:
    """Create the CSV trade log file with headers if it doesn't already exist."""
    if not os.path.exists(log_file):
        with open(log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "symbol", "action", "qty", "price", "reason", "note"])


def log_trade(
    log_file: str,
    symbol: str,
    action: str,
    qty: float,
    price: float,
    reason: str,
    note: str = "",
) -> None:
    """Append a trade record to the CSV log file with a NY-timezone timestamp."""
    timestamp = datetime.now(_NY_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, symbol, action, qty, f"{price:.2f}", reason, note])
    logger.info(f"Logged: {action} {qty} {symbol} @ ${price:.2f}")
