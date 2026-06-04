

import logging
import sys


class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",              # Cyan
        logging.INFO: "\033[32m",               # Green
        logging.WARNING: "\033[1;38;5;208m",    # Orange
        logging.ERROR: "\033[31m",              # Red
        logging.CRITICAL: "\033[1;31m",         # Bold Red
    }

    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger. Call once per module with __name__."""
    return logging.getLogger(name)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger. Call once at application startup."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ColoredFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Prevent duplicate handlers if setup_logging() is called more than once
    root_logger.handlers.clear()
    root_logger.addHandler(handler)