"""Market data acquisition with caching for sector ETFs.

Stores both adjusted Close (for returns/RS) and true OHLC (for pivots).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Fetches and caches OHLCV data for sector ETFs and benchmark.

    - `prices` / close cache: adjusted Close panel (columns = tickers)
    - `ohlc` cache: dict of per-ticker DataFrames with Open/High/Low/Close/Volume
      (raw OHLC preferred for pivots; Close still auto-adjusted when available)
    """

    def __init__(
        self,
        tickers: List[str],
        cache_dir: str | Path,
        history_period: str = "2y",
        cache_ttl_hours: float = 6.0,
    ):
        self.tickers = sorted(set(tickers))
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.history_period = history_period
        self.cache_ttl_hours = cache_ttl_hours
        self._prices: Optional[pd.DataFrame] = None
        self._ohlc: Optional[Dict[str, pd.DataFrame]] = None

    def _close_cache_path(self) -> Path:
        return self.cache_dir / "sector_prices.parquet"

    def _ohlc_cache_path(self) -> Path:
        return self.cache_dir / "sector_ohlc.parquet"

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < timedelta(hours=self.cache_ttl_hours)

    def _load_close_cache(self) -> Optional[pd.DataFrame]:
        path = self._close_cache_path()
        try:
            df = pd.read_parquet(path)
            missing = set(self.tickers) - set(df.columns)
            if missing:
                logger.info("Close cache missing tickers: %s — will refresh", missing)
                return None
            return df[self.tickers]
        except Exception as exc:
            logger.warning("Failed to load close cache: %s", exc)
            return None

    def _load_ohlc_cache(self) -> Optional[Dict[str, pd.DataFrame]]:
        path = self._ohlc_cache_path()
        if not path.exists():
            return None
        try:
            # Stored as MultiIndex columns: (ticker, field)
            wide = pd.read_parquet(path)
            if not isinstance(wide.columns, pd.MultiIndex):
                logger.warning("OHLC cache format unexpected — will refresh")
                return None
            out: Dict[str, pd.DataFrame] = {}
            tickers_in = wide.columns.get_level_values(0).unique()
            missing = set(self.tickers) - set(tickers_in)
            if missing:
                logger.info("OHLC cache missing tickers: %s — will refresh", missing)
                return None
            for t in self.tickers:
                if t not in tickers_in:
                    continue
                sub = wide[t].copy()
                # Normalize column names
                sub.columns = [str(c).capitalize() for c in sub.columns]
                out[t] = sub.dropna(how="all")
            return out
        except Exception as exc:
            logger.warning("Failed to load OHLC cache: %s", exc)
            return None

    def _save_close_cache(self, df: pd.DataFrame) -> None:
        try:
            df.to_parquet(self._close_cache_path())
            logger.info("Cached closes → %s", self._close_cache_path())
        except Exception as exc:
            logger.warning("Could not write close cache: %s", exc)

    def _save_ohlc_cache(self, ohlc: Dict[str, pd.DataFrame]) -> None:
        try:
            # Stack into MultiIndex columns (ticker, field)
            pieces = {}
            for t, df in ohlc.items():
                d = df.copy()
                d.columns = pd.MultiIndex.from_product([[t], list(d.columns)])
                pieces[t] = d
            if not pieces:
                return
            wide = pd.concat(pieces.values(), axis=1).sort_index()
            wide.to_parquet(self._ohlc_cache_path())
            logger.info("Cached OHLC → %s (%d tickers)", self._ohlc_cache_path(), len(ohlc))
        except Exception as exc:
            logger.warning("Could not write OHLC cache: %s", exc)

    def _download_one(self, ticker: str) -> Optional[pd.DataFrame]:
        """Download full OHLCV for one ticker with retries."""
        for attempt in range(4):
            try:
                raw = yf.download(
                    ticker,
                    period=self.history_period,
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
                if raw is None or raw.empty:
                    raise RuntimeError("empty response")

                # Flatten possible MultiIndex
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]

                cols = {str(c).capitalize(): c for c in raw.columns}
                # Map to standard names
                mapping = {}
                for std in ("Open", "High", "Low", "Close", "Volume"):
                    for c in raw.columns:
                        if str(c).lower() == std.lower():
                            mapping[c] = std
                            break
                df = raw.rename(columns=mapping)
                keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
                if "Close" not in keep:
                    raise RuntimeError(f"no Close column for {ticker}")
                df = df[keep].dropna(how="all")
                return df
            except Exception as exc:
                logger.warning("%s attempt %d failed: %s", ticker, attempt + 1, exc)
                time.sleep(1.2 + attempt * 0.8)
        return None

    def fetch(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Return adjusted close prices (columns = tickers).

        Also populates `self.ohlc` with true OHLC frames when possible.
        """
        need_close = force_refresh or not self._is_cache_valid(self._close_cache_path())
        need_ohlc = force_refresh or not self._is_cache_valid(self._ohlc_cache_path())

        if not need_close:
            cached = self._load_close_cache()
            if cached is not None:
                self._prices = cached
                # Try load OHLC without re-download
                if not need_ohlc:
                    ohlc = self._load_ohlc_cache()
                    if ohlc is not None:
                        self._ohlc = ohlc
                        logger.info(
                            "Using cached prices (%d rows) + OHLC (%d tickers)",
                            len(cached),
                            len(ohlc),
                        )
                        return cached
                logger.info("Using cached closes (%d rows); OHLC will refresh", len(cached))
                # Fall through to download OHLC only if needed — but simplest is full refresh path
                # when OHLC missing: re-download all
                need_close = True

        logger.info(
            "Downloading OHLC for %s (period=%s)",
            self.tickers,
            self.history_period,
        )
        start = time.time()
        ohlc: Dict[str, pd.DataFrame] = {}
        closes = {}

        for ticker in self.tickers:
            df = self._download_one(ticker)
            if df is not None and not df.empty:
                ohlc[ticker] = df
                closes[ticker] = df["Close"]
                logger.debug("%s: %d bars", ticker, len(df))
            else:
                logger.error("Could not download %s", ticker)
            time.sleep(0.35)

        if not closes:
            raise RuntimeError("No price data could be downloaded.")

        prices = pd.DataFrame(closes).sort_index().dropna(how="all")
        available = [t for t in self.tickers if t in prices.columns]
        missing = set(self.tickers) - set(available)
        if missing:
            logger.warning("Missing data for: %s", missing)
        prices = prices[available]

        elapsed = time.time() - start
        logger.info(
            "Downloaded %d rows × %d tickers in %.1fs (OHLC for %d)",
            len(prices),
            len(prices.columns),
            elapsed,
            len(ohlc),
        )

        self._save_close_cache(prices)
        self._save_ohlc_cache(ohlc)
        self._prices = prices
        self._ohlc = ohlc
        return prices

    @property
    def prices(self) -> pd.DataFrame:
        if self._prices is None:
            return self.fetch()
        return self._prices

    @property
    def ohlc(self) -> Dict[str, pd.DataFrame]:
        """Per-ticker OHLC DataFrames (Open/High/Low/Close[/Volume])."""
        if self._ohlc is None:
            # Ensure fetch ran
            if self._prices is None:
                self.fetch()
            if self._ohlc is None:
                # Try cache once more
                self._ohlc = self._load_ohlc_cache() or {}
        return self._ohlc or {}

    def get_ohlc_dict(self) -> Dict[str, pd.DataFrame]:
        """Explicit accessor for SupportResistanceAnalyzer."""
        return self.ohlc

    def get_latest_prices(self) -> pd.Series:
        return self.prices.iloc[-1]
