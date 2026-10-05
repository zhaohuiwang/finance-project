from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from rich.console import Console
from typing import Any

import schwabdev
from dotenv import load_dotenv

console = Console()

# ============================================================
# Configuration
# ============================================================

load_dotenv()

APP_KEY = os.environ["APP_KEY"]
APP_SECRET = os.environ["APP_SECRET"]
CALLBACK_URL = os.getenv(
    "CALLBACK_URL",
    "https://127.0.0.1:8182",
)

# Market universe.
#
# EQUITY_ALL is the important one for a market-wide scanner.
#
# You can add NASDAQ / NYSE if you want separate exchange
# screeners as well.
UNIVERSES = [
    "EQUITY_ALL",
]

# Screener frequencies.
#
# 5-minute is a good starting point for an intraday scanner.
#
# "0" means the whole trading day.
SCREENER_FREQUENCY = 5

# How many rows we display.
DISPLAY_COUNT = 20

# Filters.
MIN_PRICE = 2.00
MIN_VOLUME = 100_000
MIN_PERCENT_CHANGE = 2.0
MIN_RVOL_PERCENT = 150.0

# Refresh the terminal.
DISPLAY_INTERVAL = 2.0


# ============================================================
# Data structures
# ============================================================


@dataclass
class Candidate:
    symbol: str
    description: str = ""

    price: float = 0.0
    net_change: float = 0.0
    percent_change: float = 0.0

    total_volume: int = 0
    interval_volume: int = 0
    trades: int = 0

    # Schwab screener's average-percent-volume value.
    average_percent_volume: float = 0.0

    # Which screeners found this stock.
    winner_rank: int | None = None
    loser_rank: int | None = None
    rvol_rank: int | None = None
    volume_rank: int | None = None
    trades_rank: int | None = None

    score: float = 0.0


# ============================================================
# Scanner
# ============================================================


class MarketScanner:

    def __init__(self) -> None:

        self.client = schwabdev.Client(
            APP_KEY,
            APP_SECRET,
            CALLBACK_URL,
        )

        self.stream = schwabdev.Stream(self.client)

        self.lock = threading.Lock()

        self.candidates: dict[str, Candidate] = {}

        self.last_update: datetime | None = None

        self.message_count = 0

    # --------------------------------------------------------
    # Screener subscriptions
    # --------------------------------------------------------

    def build_screener_keys(self) -> list[str]:

        keys = []

        for universe in UNIVERSES:

            keys.extend(
                [
                    f"{universe}_PERCENT_CHANGE_UP_" f"{SCREENER_FREQUENCY}",
                    f"{universe}_PERCENT_CHANGE_DOWN_" f"{SCREENER_FREQUENCY}",
                    f"{universe}_AVERAGE_PERCENT_VOLUME_" f"{SCREENER_FREQUENCY}",
                    f"{universe}_VOLUME_" f"{SCREENER_FREQUENCY}",
                    f"{universe}_TRADES_" f"{SCREENER_FREQUENCY}",
                ]
            )

        return keys

    # --------------------------------------------------------
    # Stream callback
    # --------------------------------------------------------

    def on_message(self, raw_message: Any) -> None:

        try:

            # schwabdev normally gives us a JSON string here.
            if isinstance(raw_message, str):
                import json

                message = json.loads(raw_message)

            else:
                message = raw_message

            self.process_message(message)

        except Exception as exc:

            print(f"\n[ERROR] " f"Message processing failed: {exc}")

    # --------------------------------------------------------
    # Process stream message
    # --------------------------------------------------------

    def process_message(
        self,
        message: dict[str, Any],
    ) -> None:

        data = message.get("data", [])

        for service_message in data:

            if service_message.get("service") != "SCREENER_EQUITY":
                continue

            content = service_message.get("content", [])

            for payload in content:

                self.process_screener_payload(payload)

        self.last_update = datetime.now()

        self.message_count += 1

    # --------------------------------------------------------
    # Process screener payload
    # --------------------------------------------------------

    def process_screener_payload(
        self,
        payload: dict[str, Any],
    ) -> None:

        #
        # SCREENER_EQUITY returns:
        #
        # {
        #     "1": timestamp,
        #     "2": "PERCENT_CHANGE_UP",
        #     "3": 5,
        #     "4": [
        #         {
        #             "symbol": "...",
        #             ...
        #         }
        #     ]
        # }
        #

        sort_field = str(payload.get("2", ""))

        rows = payload.get("4", [])

        if not isinstance(rows, list):
            return

        with self.lock:

            for rank, row in enumerate(
                rows,
                start=1,
            ):

                symbol = row.get("symbol")

                if not symbol:
                    continue

                symbol = symbol.upper()

                candidate = self.candidates.get(symbol)

                if candidate is None:

                    candidate = Candidate(
                        symbol=symbol,
                        description=(row.get("description", "")),
                    )

                    self.candidates[symbol] = candidate

                self.update_candidate(
                    candidate,
                    row,
                    sort_field,
                    rank,
                )

    # --------------------------------------------------------
    # Update candidate
    # --------------------------------------------------------

    @staticmethod
    def update_candidate(
        candidate: Candidate,
        row: dict[str, Any],
        sort_field: str,
        rank: int,
    ) -> None:

        #
        # Update common quote information.
        #

        candidate.description = row.get("description") or candidate.description

        candidate.price = to_float(
            row.get("lastPrice"),
            candidate.price,
        )

        candidate.net_change = to_float(
            row.get("netChange"),
            candidate.net_change,
        )

        candidate.percent_change = to_float(
            row.get("netPercentChange"),
            candidate.percent_change,
        )

        candidate.total_volume = to_int(
            row.get("totalVolume"),
            candidate.total_volume,
        )

        candidate.interval_volume = to_int(
            row.get("volume"),
            candidate.interval_volume,
        )

        candidate.trades = to_int(
            row.get("trades"),
            candidate.trades,
        )

        candidate.average_percent_volume = to_float(
            row.get("averagePercentVolume"),
            candidate.average_percent_volume,
        )

        #
        # Record which screener produced the
        # candidate and its rank.
        #

        if sort_field == "PERCENT_CHANGE_UP":

            candidate.winner_rank = rank

        elif sort_field == "PERCENT_CHANGE_DOWN":

            candidate.loser_rank = rank

        elif sort_field == "AVERAGE_PERCENT_VOLUME":

            candidate.rvol_rank = rank

        elif sort_field == "VOLUME":

            candidate.volume_rank = rank

        elif sort_field == "TRADES":

            candidate.trades_rank = rank

    # --------------------------------------------------------
    # Filtering
    # --------------------------------------------------------

    @staticmethod
    def qualifies(
        candidate: Candidate,
    ) -> bool:

        if candidate.price < MIN_PRICE:
            return False

        if candidate.total_volume < MIN_VOLUME:
            return False

        if abs(candidate.percent_change) < MIN_PERCENT_CHANGE:
            return False

        return True

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    @staticmethod
    def calculate_score(
        candidate: Candidate,
    ) -> float:

        #
        # Price movement.
        #
        # +10% or -10% = max score.
        #

        momentum_score = min(
            abs(candidate.percent_change) / 10.0,
            1.0,
        )

        #
        # Relative volume.
        #
        #
        # Schwab's screener field is
        # "AVERAGE_PERCENT_VOLUME".
        #
        # 100 = approximately normal.
        # 200 = approximately 2x.
        # 500 = approximately 5x.
        #
        #

        rvol_score = min(
            candidate.average_percent_volume / 500.0,
            1.0,
        )

        #
        # Dollar volume.
        #

        dollar_volume = candidate.price * candidate.total_volume

        liquidity_score = min(
            dollar_volume / 100_000_000.0,
            1.0,
        )

        #
        # Screener diversity.
        #
        # If the stock appears in several screens,
        # it gets a small bonus.
        #

        appearances = sum(
            x is not None
            for x in [
                candidate.winner_rank,
                candidate.loser_rank,
                candidate.rvol_rank,
                candidate.volume_rank,
                candidate.trades_rank,
            ]
        )

        breadth_score = min(
            appearances / 3.0,
            1.0,
        )

        score = (
            momentum_score * 35.0
            + rvol_score * 40.0
            + liquidity_score * 15.0
            + breadth_score * 10.0
        )

        return round(
            score,
            1,
        )

    # --------------------------------------------------------
    # Ranked results
    # --------------------------------------------------------

    def ranked_candidates(
        self,
    ) -> list[Candidate]:

        with self.lock:

            candidates = [
                candidate
                for candidate in self.candidates.values()
                if self.qualifies(candidate)
            ]

            for candidate in candidates:

                candidate.score = self.calculate_score(candidate)

            candidates.sort(
                key=lambda x: x.score,
                reverse=True,
            )

            return candidates

    # --------------------------------------------------------
    # Print tables
    # --------------------------------------------------------

    def render(self) -> None:

        with self.lock:

            all_candidates = list(self.candidates.values())

        #
        # Top winners
        #

        winners = sorted(
            [x for x in all_candidates if self.qualifies(x) and x.percent_change > 0],
            key=lambda x: (x.percent_change),
            reverse=True,
        )[:DISPLAY_COUNT]

        #
        # Top losers
        #

        losers = sorted(
            [x for x in all_candidates if self.qualifies(x) and x.percent_change < 0],
            key=lambda x: (x.percent_change),
        )[:DISPLAY_COUNT]

        #
        # Highest relative volume.
        #

        rvol = sorted(
            [
                x
                for x in all_candidates
                if x.price >= MIN_PRICE and x.total_volume >= MIN_VOLUME
            ],
            key=lambda x: (x.average_percent_volume),
            reverse=True,
        )[:DISPLAY_COUNT]

        #
        # Overall score.
        #

        overall = sorted(
            [x for x in all_candidates if self.qualifies(x)],
            key=lambda x: x.score,
            reverse=True,
        )[:DISPLAY_COUNT]

        #
        # Clear terminal.
        #

        print("\033[2J\033[H")

        print("SCHWAB MARKET-WIDE STOCK SCANNER")

        print(
            f"Universe: EQUITY_ALL | "
            f"Window: {SCREENER_FREQUENCY} min | "
            f"Candidates: {len(all_candidates)}"
        )

        if self.last_update:

            print(f"Last update: " f"{self.last_update:%H:%M:%S}")

        print()

        self.print_table(
            "TOP WINNERS",
            winners,
        )

        self.print_table(
            "TOP LOSERS",
            losers,
        )

        self.print_table(
            "HIGHEST RELATIVE VOLUME",
            rvol,
        )

        self.print_table(
            "OVERALL MOVER SCORE",
            overall,
        )

    # --------------------------------------------------------
    # Table renderer
    # --------------------------------------------------------

    @staticmethod
    def print_table(
        title: str,
        rows: list[Candidate],
    ) -> None:

        print()
        print(f"=== {title} ===")

        print(
            f"{'SYM':<8}"
            f"{'PRICE':>10}"
            f"{'CHANGE':>10}"
            f"{'RVOL':>10}"
            f"{'VOLUME':>14}"
            f"{'TRADES':>10}"
            f"{'SCORE':>9}"
        )

        print("-" * 81)

        for row in rows:

            #
            # Convert Schwab's average-percent-volume
            # into an easier-to-read multiplier.
            #
            # Example:
            #
            # 100% -> 1.0x
            # 250% -> 2.5x
            # 500% -> 5.0x
            #

            rvol = row.average_percent_volume / 100.0

            print(
                f"{row.symbol:<8}"
                f"{row.price:>10.2f}"
                f"{row.percent_change:>9.2f}%"
                f"{rvol:>9.1f}x"
                f"{row.total_volume:>14,}"
                f"{row.trades:>10,}"
                f"{row.score:>9.1f}"
            )

    # --------------------------------------------------------
    # Start
    # --------------------------------------------------------

    def start(self) -> None:

        keys = self.build_screener_keys()

        print("Starting Schwab market scanner...")

        print("Subscriptions:")

        for key in keys:
            print(f"  {key}")

        #
        # Start websocket.
        #

        self.stream.start(receiver=self.on_message)

        #
        # Subscribe to all market screeners.
        #
        # SCREENER_EQUITY streams whole screener
        # snapshots, not incremental quote fields.
        #

        request = self.stream.screener_equity(
            keys,
            [
                "0",
                "1",
                "2",
                "3",
                "4",
            ],
        )

        self.stream.send(request)

        print()
        print("Waiting for market screener data...")

        #
        # Main display loop.
        #

        try:

            while True:

                time.sleep(DISPLAY_INTERVAL)

                self.render()

        except KeyboardInterrupt:

            print("\nStopping scanner...")

        finally:

            self.stream.stop()


# ============================================================
# Helpers
# ============================================================


def to_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:

        if value is None:
            return default

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


def to_int(
    value: Any,
    default: int = 0,
) -> int:

    try:

        if value is None:
            return default

        return int(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    scanner = MarketScanner()

    scanner.start()
