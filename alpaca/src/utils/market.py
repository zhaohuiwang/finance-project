from datetime import datetime, timedelta, timezone

import pandas as pd
import pytz
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

_NY_TZ = pytz.timezone("America/New_York")


def is_market_open(trade_only_market_hours: bool) -> bool:
    """Return True if the NY market is currently open, or if 24/7 trading is enabled."""
    if not trade_only_market_hours:
        return True
    now = datetime.now(_NY_TZ)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def get_latest_ask(data_client: StockHistoricalDataClient, symbol: str) -> float | None:
    """Return the current ask price for a symbol, or None on failure."""
    try:
        quote = data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=symbol)
        )
        return float(quote[symbol].ask_price)
    except Exception:
        return None


def get_bars(
    data_client: StockHistoricalDataClient,
    symbol: str,
    timeframe: TimeFrame,
    limit: int = 400,
) -> pd.DataFrame:
    """Fetch up to `limit` OHLCV bars for the symbol over the last 10 days."""
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=timeframe,
        start=datetime.now(timezone.utc) - timedelta(days=10),
        limit=limit,
    )
    bars = data_client.get_stock_bars(request_params)
    return bars.df.reset_index()
