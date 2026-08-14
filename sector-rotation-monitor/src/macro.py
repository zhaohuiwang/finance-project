"""FRED macro data fetch + simple economic-cycle regime classifier."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)
load_dotenv()

class MacroOverlay:
    """
    Pulls key FRED series and classifies a simple business-cycle regime.

    Requires a free FRED API key:
      export FRED_API_KEY=your_key_here
      or load from .env via dotenv Python library
    Get one at: https://fred.stlouisfed.org/docs/api/api_key.html
    """

    FRED_API_KEY = os.getenv("FRED_API_KEY")

    def __init__(
        self,
        series_config: Dict[str, Dict[str, Any]],
        cache_dir: str | Path,
        lookback_months: int = 36,
        api_key: Optional[str] = None,
    ):
        self.series_config = series_config
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lookback_months = lookback_months
        self.api_key = api_key or os.environ.get("FRED_API_KEY") or os.environ.get("FRED_KEY")
        self._data: Optional[pd.DataFrame] = None
        self._fred = None

    def _get_fred(self):
        if self._fred is not None:
            return self._fred
        if not self.api_key:
            raise RuntimeError(
                "FRED API key not found. Set environment variable FRED_API_KEY.\n"
                "Free key: https://fred.stlouisfed.org/docs/api/api_key.html"
            )
        try:
            from fredapi import Fred
        except ImportError as e:
            raise ImportError(
                "fredapi package required for macro overlay. "
                "Install with: pip install fredapi"
            ) from e
        self._fred = Fred(api_key=self.api_key)
        return self._fred

    def _cache_path(self) -> Path:
        return self.cache_dir / "fred_macro.parquet"

    def _is_cache_valid(self, ttl_hours: float = 24.0) -> bool:
        path = self._cache_path()
        if not path.exists():
            return False
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < timedelta(hours=ttl_hours)

    def fetch(self, force_refresh: bool = False) -> pd.DataFrame:
        """Download (or load cached) FRED series. Columns = series IDs."""
        if not force_refresh and self._is_cache_valid():
            try:
                df = pd.read_parquet(self._cache_path())
                logger.info("Using cached FRED data (%d rows, %d series)", len(df), df.shape[1])
                self._data = df
                return df
            except Exception as exc:
                logger.warning("FRED cache load failed: %s", exc)

        fred = self._get_fred()
        start = (datetime.now() - timedelta(days=self.lookback_months * 31)).strftime("%Y-%m-%d")
        frames = {}
        for series_id in self.series_config:
            try:
                s = fred.get_series(series_id, observation_start=start)
                s.name = series_id
                frames[series_id] = s
                logger.debug("FRED %s: %d obs", series_id, len(s))
                time.sleep(0.25)  # be polite
            except Exception as exc:
                logger.warning("Failed to fetch FRED series %s: %s", series_id, exc)

        if not frames:
            raise RuntimeError("No FRED series could be downloaded.")

        df = pd.DataFrame(frames).sort_index()
        # Forward-fill sparse daily series lightly, keep monthly cadence
        df = df.ffill(limit=5)
        try:
            df.to_parquet(self._cache_path())
            logger.info("Cached FRED data → %s", self._cache_path())
        except Exception as exc:
            logger.warning("Could not cache FRED data: %s", exc)

        self._data = df
        return df

    @property
    def data(self) -> pd.DataFrame:
        if self._data is None:
            return self.fetch()
        return self._data

    def latest_snapshot(self) -> pd.DataFrame:
        """
        One-row-per-series table with latest value, 3m change, 12m change, and YoY where sensible.
        """
        df = self.data
        rows = []
        for sid, meta in self.series_config.items():
            if sid not in df.columns:
                continue
            series = df[sid].dropna()
            if series.empty:
                continue
            latest = series.iloc[-1]
            latest_date = series.index[-1]

            def pct_change_n(n_months: int) -> Optional[float]:
                # Approximate calendar months via 21*n trading-ish; better: shift by date
                target = latest_date - pd.DateOffset(months=n_months)
                past = series[series.index <= target]
                if past.empty:
                    return None
                past_val = past.iloc[-1]
                if past_val == 0 or pd.isna(past_val):
                    return None
                return (latest / past_val - 1.0) * 100.0

            def level_change_n(n_months: int) -> Optional[float]:
                target = latest_date - pd.DateOffset(months=n_months)
                past = series[series.index <= target]
                if past.empty:
                    return None
                return float(latest - past.iloc[-1])

            # Rates & unemployment: level change is more natural; indices: % change
            is_rate_like = sid in ("UNRATE", "DFF", "T10Y2Y", "TCU") or "RATE" in sid
            chg_3m = level_change_n(3) if is_rate_like else pct_change_n(3)
            chg_12m = level_change_n(12) if is_rate_like else pct_change_n(12)

            rows.append({
                "Series": sid,
                "Name": meta.get("name", sid),
                "Category": meta.get("category", ""),
                "Latest": latest,
                "AsOf": latest_date.strftime("%Y-%m-%d") if hasattr(latest_date, "strftime") else str(latest_date),
                "Chg_3M": chg_3m,
                "Chg_12M": chg_12m,
                "HigherIs": meta.get("higher_is", "mixed"),
            })
        return pd.DataFrame(rows).set_index("Series")

    def classify_regime(self) -> Dict[str, Any]:
        """
        Heuristic cycle-phase classifier using a small set of signals.

        Returns dict with:
          - phase: Early Expansion | Mid Expansion | Late Expansion | Slowdown | Recession / Contraction | Unclear
          - signals: supporting evidence
          - score components
        """
        snap = self.latest_snapshot()
        signals: List[str] = []
        score = 0  # positive = expansionary, negative = contractionary

        def get(sid: str) -> Optional[float]:
            if sid not in snap.index:
                return None
            return float(snap.loc[sid, "Latest"])

        def get_chg(sid: str, col: str = "Chg_3M") -> Optional[float]:
            if sid not in snap.index:
                return None
            v = snap.loc[sid, col]
            return float(v) if pd.notna(v) else None

        # --- Yield curve ---
        curve = get("T10Y2Y")
        if curve is not None:
            if curve < -0.25:
                signals.append(f"Yield curve inverted ({curve:.2f}%)")
                score -= 2
            elif curve < 0.25:
                signals.append(f"Yield curve flat ({curve:.2f}%)")
                score -= 1
            else:
                signals.append(f"Yield curve positive ({curve:.2f}%)")
                score += 1

        # --- Unemployment level & direction ---
        unrate = get("UNRATE")
        unrate_chg = get_chg("UNRATE", "Chg_3M")
        if unrate is not None:
            if unrate >= 6.0:
                signals.append(f"High unemployment ({unrate:.1f}%)")
                score -= 2
            elif unrate <= 4.0:
                signals.append(f"Low unemployment ({unrate:.1f}%)")
                score += 1
            if unrate_chg is not None:
                if unrate_chg > 0.3:
                    signals.append(f"Unemployment rising (+{unrate_chg:.2f} pp / 3M)")
                    score -= 2
                elif unrate_chg < -0.2:
                    signals.append(f"Unemployment falling ({unrate_chg:.2f} pp / 3M)")
                    score += 1

        # --- Initial claims direction ---
        claims_chg = get_chg("ICSA", "Chg_3M")
        if claims_chg is not None:
            # ICSA is level; we stored level change for rate-like but ICSA is claims count
            # Recompute % if needed — for simplicity treat large positive level rise as bad
            if claims_chg > 0 and abs(claims_chg) > 20000:  # rough
                signals.append("Initial claims rising")
                score -= 1
            elif claims_chg < 0 and abs(claims_chg) > 20000:
                signals.append("Initial claims falling")
                score += 1

        # --- Industrial production ---
        ip_chg = get_chg("INDPRO", "Chg_3M")
        if ip_chg is not None:
            if ip_chg > 1.0:
                signals.append(f"Industrial production strong (+{ip_chg:.1f}% / 3M)")
                score += 2
            elif ip_chg < -1.0:
                signals.append(f"Industrial production weak ({ip_chg:.1f}% / 3M)")
                score -= 2
            else:
                signals.append(f"Industrial production modest ({ip_chg:+.1f}% / 3M)")

        # --- Capacity utilization ---
        tcu = get("TCU")
        if tcu is not None:
            if tcu >= 82:
                signals.append(f"High capacity utilization ({tcu:.1f}%)")
                score += 1  # late-cycle lean
            elif tcu <= 75:
                signals.append(f"Low capacity utilization ({tcu:.1f}%)")
                score -= 1

        # --- Consumer sentiment ---
        sent = get("UMCSENT")
        sent_chg = get_chg("UMCSENT", "Chg_3M")
        if sent is not None:
            if sent >= 90:
                signals.append(f"Strong consumer sentiment ({sent:.0f})")
                score += 1
            elif sent <= 60:
                signals.append(f"Weak consumer sentiment ({sent:.0f})")
                score -= 1
        if sent_chg is not None and abs(sent_chg) > 5:
            direction = "rising" if sent_chg > 0 else "falling"
            signals.append(f"Sentiment {direction} ({sent_chg:+.1f} / 3M)")

        # --- Inflation pressure (core CPI YoY-ish via 12M) ---
        core_chg = get_chg("CPILFESL", "Chg_12M")
        if core_chg is not None:
            if core_chg > 4.0:
                signals.append(f"Elevated core CPI trend (~{core_chg:.1f}% / 12M)")
                # late-cycle inflation pressure
            elif core_chg < 2.0:
                signals.append(f"Soft core CPI trend (~{core_chg:.1f}% / 12M)")

        # --- Map score → phase ---
        if score <= -4:
            phase = "Recession / Contraction"
        elif score <= -1:
            phase = "Slowdown"
        elif score <= 2:
            # Distinguish early vs mid vs late with capacity + curve
            if tcu is not None and tcu >= 81 and curve is not None and curve < 0.5:
                phase = "Late Expansion"
            elif unrate is not None and unrate_chg is not None and unrate_chg < 0 and unrate > 4.5:
                phase = "Early Expansion"
            else:
                phase = "Mid Expansion"
        else:
            if unrate is not None and unrate > 5.0 and unrate_chg is not None and unrate_chg < 0:
                phase = "Early Expansion"
            else:
                phase = "Mid Expansion"

        return {
            "phase": phase,
            "score": score,
            "signals": signals,
            "snapshot": snap,
            "as_of": str(self.data.index[-1].date()) if len(self.data) else None,
        }

    def preferred_sectors(
        self,
        phase: str,
        preferences: Dict[str, Dict[str, List[str]]],
    ) -> Dict[str, List[str]]:
        """Return favored / avoided sector tickers for the given phase."""
        return preferences.get(phase, {"favored": [], "avoided": []})
