from datetime import datetime, time
import pytz
import pandas as pd

from utils.logger import get_logger
from config import load_config

from alpaca.data.requests import StockBarsRequest
from alpaca.data.requests import StockLatestQuoteRequest

from datetime import timedelta, timezone
    
    
logger = get_logger(__name__)

_NY_TZ = pytz.timezone("America/New_York")


def _parse_time(time_str: str) -> time:
    """Convert HH:MM string to time object."""
    return datetime.strptime(time_str, "%H:%M").time()


def is_market_hours(
    dt: datetime | None = None, 
    regular_only: bool = True,
    cfg = None
) -> bool:
    """Check if timestamp is within allowed trading hours."""
    if dt is None:
        dt = datetime.now(_NY_TZ)
    elif dt.tzinfo is None:
        dt = pytz.utc.localize(dt).astimezone(_NY_TZ)
    else:
        dt = dt.astimezone(_NY_TZ)

    if not regular_only:
        return True

    if cfg is None:
        cfg = load_config()

    open_time = _parse_time(cfg.strategy.market_open_time)
    close_time = _parse_time(cfg.strategy.market_close_time)

    current_time = dt.time()
    return open_time <= current_time < close_time


def filter_regular_hours(df: pd.DataFrame, cfg=None) -> pd.DataFrame:
    """Filter DataFrame to only regular trading hours."""
    if df.empty or "timestamp" not in df.columns:
        return df

    mask = df["timestamp"].apply(
        lambda ts: is_market_hours(ts, regular_only=True, cfg=cfg)
    )
    filtered = df[mask].copy()

    if len(filtered) < len(df):
        logger.debug(f"Filtered regular hours: {len(df)} → {len(filtered)} bars")

    return filtered


def get_latest_ask(data_client, symbol: str) -> float | None:
    """Return the current ask price for a symbol."""
    try:
        # from alpaca.data.requests import StockLatestQuoteRequest
        quote = data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=symbol)
        )
        return float(quote[symbol].ask_price)
    except Exception as e:
        logger.debug(f"Failed to get latest ask for {symbol}: {e}")
        return None


def get_bars(
    data_client,
    symbol: str,
    timeframe,
    limit: int | None = None,
    regular_hours_only: bool | None = None,
    cfg = None
) -> pd.DataFrame:
    """Fetch bars and optionally filter to regular market hours."""
    # from alpaca.data.requests import StockBarsRequest
    # from datetime import timedelta, timezone

    if cfg is None:
        cfg = load_config()

    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=timeframe,
        start=datetime.now(timezone.utc) - timedelta(days=10),
        limit=limit,
    )

    try:
        bars = data_client.get_stock_bars(request_params)
        df = bars.df.reset_index()

        if regular_hours_only is None:
            regular_hours_only = getattr(cfg.strategy, 'use_regular_hours_only', True)

        if regular_hours_only:
            df = filter_regular_hours(df, cfg=cfg)

        if df.empty:
            logger.warning(f"No bars returned for {symbol} after filtering")
            return pd.DataFrame()

        return df

    except Exception as e:
        logger.error(f"Failed to fetch bars for {symbol}: {e}")
        return pd.DataFrame()