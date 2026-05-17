import csv
import os
from datetime import datetime

import pytz

from utils.logger import get_logger

logger = get_logger(__name__)

_NY_TZ = pytz.timezone("America/New_York")


def init_trade_log(log_file: str) -> str:
    """Create the CSV trade log file with a date suffix if it doesn't already exist."""
    
    # Add YYYYMMDD suffix before file extension
    date_suffix = datetime.now().strftime("%Y%m%d")
    base, ext = os.path.splitext(log_file)
    dated_log_file = f"{base}_{date_suffix}{ext}"

    if not os.path.exists(dated_log_file):
        with open(dated_log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "symbol",
                "action",
                "qty",
                "price",
                "reason",
                "note"
            ])

    return dated_log_file


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
