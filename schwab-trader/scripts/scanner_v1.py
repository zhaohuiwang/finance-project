#!/usr/bin/env python3
"""
Schwab Market-Wide Equity Scanner
Real-time screener using schwabdev 4.x streaming.

Requirements:
  pip install schwabdev python-dotenv rich pyyaml

Credentials live in .env (APP_KEY / APP_SECRET).
Optional non-secret settings can live in config.yaml.

# Make sure these are installed
pip install schwabdev python-dotenv rich pyyaml

# Your existing .env already has the credentials
python3 scanner.py

"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from rich.console import Console, Group
from rich.live import Live
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import schwabdev

# Optional YAML support
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
log = logging.getLogger("scanner")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()


@dataclass(slots=True, frozen=True)
class Settings:
    """Validated runtime configuration.

    Priority (highest → lowest):
      1. Environment variables / .env
      2. config.yaml (if present)
      3. Hard-coded defaults
    """

    app_key: str
    app_secret: str
    callback_url: str = "https://127.0.0.1:8182"

    universes: tuple[str, ...] = ("EQUITY_ALL",)
    frequency: int = 5                    # minutes (0 = full day)
    display_count: int = 15

    min_price: float = 2.0
    min_volume: int = 100_000
    min_percent_change: float = 2.0

    # Scoring weights (roughly sum to 100)
    w_momentum: float = 35.0
    w_rvol: float = 40.0
    w_liquidity: float = 15.0
    w_breadth: float = 10.0

    refresh_hz: float = 2.0
    eastern: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/New_York"))

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        config_path: str | Path = "config.yaml",
    ) -> Settings:
        """Load from optional YAML + environment variables."""
        file_cfg = cls._load_yaml(config_path)

        def get(key: str, default: Any = None) -> Any:
            # Environment always wins
            env_val = os.getenv(key.upper()) or os.getenv(key.lower())
            if env_val is not None:
                return env_val
            return file_cfg.get(key, default)

        app_key = get("app_key") or get("APP_KEY")
        app_secret = get("app_secret") or get("APP_SECRET")

        if not app_key or not app_secret:
            raise SystemExit(
                "Missing credentials.\n"
                "Set APP_KEY / APP_SECRET in the environment (or .env)\n"
                "or put them in config.yaml"
            )

        def as_float(v: Any, default: float) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        def as_int(v: Any, default: int) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        universes_raw = get("universes", ("EQUITY_ALL",))
        if isinstance(universes_raw, str):
            universes = tuple(u.strip() for u in universes_raw.split(",") if u.strip())
        else:
            universes = tuple(universes_raw)

        return cls(
            app_key=str(app_key),
            app_secret=str(app_secret),
            callback_url=str(
                get("callback_url")
                or get("CALLBACK_URL")
                or "https://127.0.0.1:8182"
            ),
            universes=universes,
            frequency=as_int(get("frequency"), 5),
            display_count=as_int(get("display_count"), 15),
            min_price=as_float(get("min_price"), 2.0),
            min_volume=as_int(get("min_volume"), 100_000),
            min_percent_change=as_float(get("min_percent_change"), 2.0),
            w_momentum=as_float(get("w_momentum"), 35.0),
            w_rvol=as_float(get("w_rvol"), 40.0),
            w_liquidity=as_float(get("w_liquidity"), 15.0),
            w_breadth=as_float(get("w_breadth"), 10.0),
            refresh_hz=as_float(get("refresh_hz"), 2.0),
        )

    @staticmethod
    def _load_yaml(path: str | Path) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            return {}
        if not HAS_YAML:
            log.warning("config.yaml found but PyYAML is not installed – ignoring file")
            return {}
        try:
            with path.open() as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                log.warning("config.yaml root must be a mapping – ignoring")
                return {}
            return data
        except Exception as exc:
            log.warning("Failed to read config.yaml: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Candidate:
    symbol: str
    description: str = ""

    price: float = 0.0
    net_change: float = 0.0
    percent_change: float = 0.0

    total_volume: int = 0
    interval_volume: int = 0
    trades: int = 0
    average_percent_volume: float = 0.0   # 100 ≈ normal, 200 ≈ 2×

    winner_rank: int | None = None
    loser_rank: int | None = None
    rvol_rank: int | None = None
    volume_rank: int | None = None
    trades_rank: int | None = None

    score: float = 0.0
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class MarketScanner:
    """Thread-safe market-wide equity scanner driven by Schwab SCREENER_EQUITY."""

    def __init__(self, settings: Settings) -> None:
        self.cfg = settings
        self.client = schwabdev.Client(
            settings.app_key,
            settings.app_secret,
            settings.callback_url,
        )
        self.stream = schwabdev.Stream(self.client)

        self._lock = threading.RLock()
        self.candidates: dict[str, Candidate] = {}
        self.last_update: datetime | None = None
        self.message_count = 0
        self._running = False

    # ------------------------------------------------------------------
    # Subscription keys
    # ------------------------------------------------------------------

    def build_screener_keys(self) -> list[str]:
        freq = self.cfg.frequency
        keys: list[str] = []
        for universe in self.cfg.universes:
            for sort in (
                "PERCENT_CHANGE_UP",
                "PERCENT_CHANGE_DOWN",
                "AVERAGE_PERCENT_VOLUME",
                "VOLUME",
                "TRADES",
            ):
                keys.append(f"{universe}_{sort}_{freq}")
        return keys

    # ------------------------------------------------------------------
    # Stream callback (must stay extremely light)
    # ------------------------------------------------------------------

    def on_message(self, raw: Any) -> None:
        """Called on every websocket frame. Never raise; keep it fast."""
        try:
            message = json.loads(raw) if isinstance(raw, str) else raw
            self._process_message(message)
        except Exception:
            log.exception("Failed to process stream message")

    def _process_message(self, message: dict[str, Any]) -> None:
        data = message.get("data") or []
        for svc in data:
            if svc.get("service") != "SCREENER_EQUITY":
                continue
            for payload in svc.get("content") or []:
                self._ingest_payload(payload)

        with self._lock:
            self.last_update = datetime.now(self.cfg.eastern)
            self.message_count += 1

    def _ingest_payload(self, payload: dict[str, Any]) -> None:
        sort_field = str(payload.get("2", ""))
        rows = payload.get("4")
        if not isinstance(rows, list):
            return

        now = datetime.now(self.cfg.eastern)
        with self._lock:
            for rank, row in enumerate(rows, start=1):
                symbol = (row.get("symbol") or "").upper()
                if not symbol:
                    continue

                cand = self.candidates.get(symbol)
                if cand is None:
                    cand = Candidate(symbol=symbol)
                    self.candidates[symbol] = cand

                self._update_candidate(cand, row, sort_field, rank, now)

    @staticmethod
    def _update_candidate(
        cand: Candidate,
        row: dict[str, Any],
        sort_field: str,
        rank: int,
        now: datetime,
    ) -> None:
        cand.description = row.get("description") or cand.description
        cand.price = _to_float(row.get("lastPrice"), cand.price)
        cand.net_change = _to_float(row.get("netChange"), cand.net_change)
        raw_pct = _to_float(row.get("netPercentChange"), None)
        if raw_pct is not None:
            cand.percent_change = raw_pct * 100.0
        cand.total_volume = _to_int(row.get("totalVolume"), cand.total_volume)
        cand.interval_volume = _to_int(row.get("volume"), cand.interval_volume)
        cand.trades = _to_int(row.get("trades"), cand.trades)
        cand.average_percent_volume = _to_float(
            row.get("averagePercentVolume"), cand.average_percent_volume
        )
        cand.updated_at = now

        if sort_field == "PERCENT_CHANGE_UP":
            cand.winner_rank = rank
        elif sort_field == "PERCENT_CHANGE_DOWN":
            cand.loser_rank = rank
        elif sort_field == "AVERAGE_PERCENT_VOLUME":
            cand.rvol_rank = rank
        elif sort_field == "VOLUME":
            cand.volume_rank = rank
        elif sort_field == "TRADES":
            cand.trades_rank = rank

    # ------------------------------------------------------------------
    # Filtering & scoring
    # ------------------------------------------------------------------

    def qualifies(self, c: Candidate) -> bool:
        cfg = self.cfg
        return (
            c.price >= cfg.min_price
            and c.total_volume >= cfg.min_volume
            and abs(c.percent_change) >= cfg.min_percent_change
        )

    def score(self, c: Candidate) -> float:
        cfg = self.cfg
        momentum = min(abs(c.percent_change) / 10.0, 1.0)
        rvol = min(c.average_percent_volume / 500.0, 1.0)  # 500 % ≈ 5×
        dollar_vol = c.price * c.total_volume
        liquidity = min(dollar_vol / 100_000_000.0, 1.0)
        appearances = sum(
            x is not None
            for x in (
                c.winner_rank,
                c.loser_rank,
                c.rvol_rank,
                c.volume_rank,
                c.trades_rank,
            )
        )
        breadth = min(appearances / 3.0, 1.0)

        return round(
            momentum * cfg.w_momentum
            + rvol * cfg.w_rvol
            + liquidity * cfg.w_liquidity
            + breadth * cfg.w_breadth,
            1,
        )

    # ------------------------------------------------------------------
    # Snapshot for the UI (called from main thread only)
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            all_cands = list(self.candidates.values())
            last = self.last_update
            msg_cnt = self.message_count

        for c in all_cands:
            c.score = self.score(c)

        winners = sorted(
            (c for c in all_cands if self.qualifies(c) and c.percent_change > 0),
            key=lambda x: x.percent_change,
            reverse=True,
        )[: self.cfg.display_count]

        losers = sorted(
            (c for c in all_cands if self.qualifies(c) and c.percent_change < 0),
            key=lambda x: x.percent_change,
        )[: self.cfg.display_count]

        rvol = sorted(
            (
                c
                for c in all_cands
                if c.price >= self.cfg.min_price and c.total_volume >= self.cfg.min_volume
            ),
            key=lambda x: x.average_percent_volume,
            reverse=True,
        )[: self.cfg.display_count]

        overall = sorted(
            (c for c in all_cands if self.qualifies(c)),
            key=lambda x: x.score,
            reverse=True,
        )[: self.cfg.display_count]

        return {
            "winners": winners,
            "losers": losers,
            "rvol": rvol,
            "overall": overall,
            "total": len(all_cands),
            "last_update": last,
            "messages": msg_cnt,
        }

    # ------------------------------------------------------------------
    # Rich UI helpers
    # ------------------------------------------------------------------

    def _make_table(self, title: str, rows: list[Candidate], color: str) -> Table:
        table = Table(
            title=f"[{color}]{title}[/{color}]",
            title_style="bold",
            show_header=True,
            header_style="bold cyan",
            box=None,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("SYM", style="bold", width=8)
        table.add_column("PRICE", justify="right", width=9)
        table.add_column("CHG%", justify="right", width=8)
        table.add_column("RVOL", justify="right", width=7)
        table.add_column("VOLUME", justify="right", width=12)
        table.add_column("TRADES", justify="right", width=8)
        table.add_column("SCORE", justify="right", width=7)

        for r in rows:
            chg_style = "green" if r.percent_change >= 0 else "red"
            rvol_x = r.average_percent_volume / 100.0
            table.add_row(
                r.symbol,
                f"{r.price:,.2f}",
                f"[{chg_style}]{r.percent_change:+.2f}%[/{chg_style}]",
                f"{rvol_x:.1f}x",
                f"{r.total_volume:,}",
                f"{r.trades:,}",
                f"{r.score:.1f}",
            )
        return table

    def render(self) -> Group:
        snap = self.snapshot()
        header = Text.assemble(
            ("SCHWAB MARKET SCANNER", "bold white"),
            "  │  ",
            (f"Universe: {', '.join(self.cfg.universes)}", "dim"),
            "  │  ",
            (f"{self.cfg.frequency} min", "dim"),
            "  │  ",
            (f"Candidates: {snap['total']}", "cyan"),
        )
        if snap["last_update"]:
            header.append(
                f"  │  Last: {snap['last_update']:%H:%M:%S}  msgs={snap['messages']}",
                style="dim",
            )

        return Group(
            Panel(header, style="bold blue"),
            self._make_table("TOP WINNERS", snap["winners"], "green"),
            self._make_table("TOP LOSERS", snap["losers"], "red"),
            self._make_table("HIGHEST RELATIVE VOLUME", snap["rvol"], "yellow"),
            self._make_table("OVERALL MOVER SCORE", snap["overall"], "magenta"),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, use_auto: bool = True) -> None:
        keys = self.build_screener_keys()
        log.info("Subscriptions: %s", ", ".join(keys))

        if use_auto:
            self.stream.start_auto(
                receiver=self.on_message,
                start_time=dt_time(9, 28),
                stop_time=dt_time(16, 5),
                on_days=(0, 1, 2, 3, 4),
                now_timezone=self.cfg.eastern,
            )
            log.info("Stream scheduled for regular market hours (ET)")
        else:
            self.stream.start(receiver=self.on_message)

        # Subscribe once; schwabdev records the request and re-sends on reconnect
        req = self.stream.screener_equity(keys, ["0", "1", "2", "3", "4"])
        self.stream.send(req)
        log.info("Waiting for SCREENER_EQUITY data…")

        self._running = True
        console = Console()

        def _shutdown(signum: int, frame: Any) -> None:
            log.info("Signal %s received – shutting down", signum)
            self._running = False

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        try:
            with Live(
                self.render(),
                console=console,
                refresh_per_second=self.cfg.refresh_hz,
                screen=True,
                vertical_overflow="visible",
            ) as live:
                while self._running:
                    live.update(self.render())
                    time.sleep(1.0 / self.cfg.refresh_hz)
        finally:
            log.info("Stopping stream…")
            self.stream.stop()
            log.info("Scanner stopped cleanly")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    settings = Settings.from_env()          # reads .env + optional config.yaml
    scanner = MarketScanner(settings)

    # use_auto=True → only runs during regular market hours (recommended)
    # use_auto=False → runs immediately (useful for testing outside RTH)
    scanner.start(use_auto=True)


if __name__ == "__main__":
    main()

