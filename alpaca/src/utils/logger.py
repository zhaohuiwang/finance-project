import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger. Call once per module with __name__."""
    return logging.getLogger(name)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger. Call once at application startup."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
