"""Fetch and cache OHLCV data via yfinance."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def fetch_ohlcv(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: str = "1y",
    interval: str = "1d",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Download OHLCV data for a ticker.

    Parameters
    ----------
    ticker : str
        Stock symbol (e.g. 'CRWV').
    start, end : str, optional
        YYYY-MM-DD. If provided, override `period`.
    period : str
        yfinance period string when start/end not given.
    interval : str
        '1d', '1h', etc.
    use_cache : bool
        Save / load CSV cache under data/.

    Returns
    -------
    pd.DataFrame with columns Open, High, Low, Close, Volume (DatetimeIndex).
    """
    ticker = ticker.upper().strip()
    cache_name = f"{ticker}_{interval}_{start or period}_{end or 'latest'}.csv"
    cache_path = DATA_DIR / cache_name

    if use_cache and cache_path.exists():
        # Refresh if older than 1 trading day
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=20):
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            if not df.empty:
                return df

    if start or end:
        df = yf.download(
            ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    else:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )

    if df.empty:
        raise ValueError(f"No data returned for {ticker}")

    # Flatten multi-index columns if present (newer yfinance)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    # Keep only essential columns
    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[keep].copy()
    df.dropna(how="any", inplace=True)

    if use_cache:
        df.to_csv(cache_path)

    return df


def fetch_multiple(
    tickers: list[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: str = "1y",
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    """Fetch several tickers and return a dict of DataFrames."""
    results = {}
    for t in tickers:
        try:
            results[t] = fetch_ohlcv(t, start=start, end=end, period=period, interval=interval)
            print(f"[OK] {t}: {len(results[t])} bars")
        except Exception as e:
            print(f"[FAIL] {t}: {e}")
    return results