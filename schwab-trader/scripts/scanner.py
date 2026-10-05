from __future__ import annotations

import json
import os
import threading
import time

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo

import schwabdev
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

APP_KEY = os.environ["APP_KEY"]
APP_SECRET = os.environ["APP_SECRET"]
CALLBACK_URL = os.getenv(
    "callback_url",
    "https://127.0.0.1:8182",
)

ET = ZoneInfo("America/New_York")

# Market screener interval.
# Schwab supports 0, 1, 5, 10, 30, 60.
SCREENER_MINUTES = 5

# Historical RVOL lookback.
HISTORY_DAYS = 10

# Number of screener candidates retained per screen.
TOP_N_PER_SCREEN = 10

# Scanner display.
DISPLAY_ROWS = 20
DISPLAY_INTERVAL = 2

# Candidate filters.
MIN_PRICE = 2.00
MIN_DAY_VOLUME = 100_000

# Don't calculate RVOL until we have enough history.
MIN_HISTORY_BARS = 3

# Score weights.
MOMENTUM_WEIGHT = 35
RVOL_WEIGHT = 40
LIQUIDITY_WEIGHT = 15
ACTIVITY_WEIGHT = 10


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Candidate:

    symbol: str
    description: str = ""

    price: float = 0.0
    change_percent: float = 0.0

    day_volume: int = 0
    five_min_volume: int = 0
    trades: int = 0

    # Historical average volume for this exact
    # time-of-day 5-minute slot.
    expected_volume: float = 0.0

    rvol: float = 0.0

    score: float = 0.0

    # Which screener(s) discovered it.
    winner_rank: int | None = None
    loser_rank: int | None = None
    volume_rank: int | None = None
    trades_rank: int | None = None


# ============================================================
# HELPERS
# ============================================================

def safe_float(value, default=0.0):

    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):

    try:
        if value is None:
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


def epoch_to_et(timestamp_ms: int):

    return datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc,
    ).astimezone(ET)


def is_regular_session(timestamp_ms: int):

    dt = epoch_to_et(timestamp_ms)

    return (
        dt.weekday() < 5
        and dt_time(9, 30)
        <= dt.time()
        < dt_time(16, 0)
    )


def slot_key(timestamp_ms: int):

    dt = epoch_to_et(timestamp_ms)

    return (
        dt.hour,
        dt.minute // 5
    )


# ============================================================
# MARKET SCANNER
# ============================================================

class MarketScanner:

    def __init__(self):

        self.client = schwabdev.Client(
            APP_KEY,
            APP_SECRET,
            CALLBACK_URL,
        )

        self.stream = schwabdev.Stream(
            self.client
        )

        self.lock = threading.RLock()

        self.candidates: dict[str, Candidate] = {}

        # symbol -> {slot -> average historical volume}
        self.historical_volume = {}

        # symbol -> latest live candle
        self.live_candles: dict[
            str,
            Candle
        ] = {}

        self.last_message = None

        self.running = True

    # ========================================================
    # SCREENER
    # ========================================================

    def screener_keys(self):

        return [

            f"EQUITY_ALL_PERCENT_CHANGE_UP_"
            f"{SCREENER_MINUTES}",

            f"EQUITY_ALL_PERCENT_CHANGE_DOWN_"
            f"{SCREENER_MINUTES}",

            f"EQUITY_ALL_VOLUME_"
            f"{SCREENER_MINUTES}",

            f"EQUITY_ALL_TRADES_"
            f"{SCREENER_MINUTES}",
        ]

    def subscribe_screeners(self):

        keys = self.screener_keys()

        request = self.stream.screener_equity(
            keys,
            "0,1,2,3,4",
            command="ADD",
        )

        self.stream.send(request)

        print("Subscribed to market screeners:")

        for key in keys:
            print(f"  {key}")

    # ========================================================
    # STREAM CALLBACK
    # ========================================================

    def on_message(self, raw):

        try:

            if isinstance(raw, str):
                message = json.loads(raw)
            else:
                message = raw

            self.process_message(message)

        except Exception as exc:

            print(
                f"\n[STREAM ERROR] {exc}"
            )

    # ========================================================
    # MESSAGE ROUTER
    # ========================================================

    def process_message(self, message):

        data = message.get(
            "data",
            [],
        )

        for service in data:

            service_name = service.get(
                "service"
            )

            if service_name == "SCREENER_EQUITY":

                self.process_screener(
                    service
                )

            elif service_name == "CHART_EQUITY":

                self.process_chart(
                    service
                )

    # ========================================================
    # SCREENER PROCESSING
    # ========================================================

    def process_screener(self, service):

        content = service.get(
            "content",
            [],
        )

        new_symbols = set()

        for payload in content:

            sort_field = str(
                payload.get("2", "")
            )

            rows = payload.get(
                "4",
                [],
            )

            for rank, row in enumerate(
                rows,
                start=1,
            ):

                symbol = row.get(
                    "symbol"
                )

                if not symbol:
                    continue

                symbol = symbol.upper()

                new_symbols.add(symbol)

                with self.lock:

                    candidate = (
                        self.candidates.get(
                            symbol
                        )
                    )

                    if candidate is None:

                        candidate = Candidate(
                            symbol=symbol,
                            description=(
                                row.get(
                                    "description",
                                    ""
                                )
                            ),
                        )

                        self.candidates[
                            symbol
                        ] = candidate

                    self.update_candidate(
                        candidate,
                        row,
                        sort_field,
                        rank,
                    )

        # Whenever new symbols appear,
        # load their historical RVOL baseline.
        for symbol in new_symbols:

            self.prepare_history(
                symbol
            )

        # Subscribe to live 5-minute chart data.
        self.subscribe_chart_symbols(
            new_symbols
        )

    # ========================================================
    # UPDATE SCREENER CANDIDATE
    # ========================================================

    @staticmethod
    def update_candidate(
        candidate,
        row,
        sort_field,
        rank,
    ):

        candidate.description = (
            row.get("description")
            or candidate.description
        )

        candidate.price = safe_float(
            row.get("lastPrice"),
            candidate.price,
        )

        # IMPORTANT:
        #
        # Schwab's returned netPercentChange
        # is fractional.
        #
        # 0.531532 -> 53.1532%
        #
        candidate.change_percent = (
            safe_float(
                row.get(
                    "netPercentChange"
                ),
                candidate.change_percent,
            )
            * 100
        )

        candidate.day_volume = safe_int(
            row.get("totalVolume"),
            candidate.day_volume,
        )

        candidate.five_min_volume = safe_int(
            row.get("volume"),
            candidate.five_min_volume,
        )

        candidate.trades = safe_int(
            row.get("trades"),
            candidate.trades,
        )

        if sort_field == "PERCENT_CHANGE_UP":

            candidate.winner_rank = rank

        elif sort_field == "PERCENT_CHANGE_DOWN":

            candidate.loser_rank = rank

        elif sort_field == "VOLUME":

            candidate.volume_rank = rank

        elif sort_field == "TRADES":

            candidate.trades_rank = rank

    # ========================================================
    # HISTORICAL RVOL
    # ========================================================

    def prepare_history(self, symbol):

        with self.lock:

            if symbol in self.historical_volume:
                return

        print(
            f"\nLoading RVOL history: {symbol}"
        )

        try:

            response = self.client.price_history(
                symbol,
                periodType="day",
                period=HISTORY_DAYS,
                frequencyType="minute",
                frequency=5,
                needExtendedHoursData=False,
            )

            if not response.ok:

                print(
                    f"History failed for "
                    f"{symbol}: "
                    f"{response.status_code}"
                )

                return

            payload = response.json()

            candles = payload.get(
                "candles",
                [],
            )

            history = defaultdict(list)

            for candle in candles:

                timestamp = safe_int(
                    candle.get("datetime")
                )

                if not timestamp:
                    continue

                if not is_regular_session(
                    timestamp
                ):
                    continue

                volume = safe_int(
                    candle.get("volume")
                )

                if volume <= 0:
                    continue

                key = slot_key(
                    timestamp
                )

                history[key].append(
                    volume
                )

            averages = {}

            for key, volumes in history.items():

                if not volumes:
                    continue

                averages[key] = (
                    sum(volumes)
                    / len(volumes)
                )

            with self.lock:

                self.historical_volume[
                    symbol
                ] = averages

            print(
                f"  {symbol}: "
                f"{len(averages)} time slots"
            )

        except Exception as exc:

            print(
                f"History error "
                f"{symbol}: {exc}"
            )

    # ========================================================
    # CHART STREAM
    # ========================================================

    def subscribe_chart_symbols(
        self,
        symbols,
    ):

        if not symbols:
            return

        symbols = list(symbols)

        # Only subscribe to symbols we know.
        with self.lock:

            symbols = [
                symbol
                for symbol in symbols
                if symbol in self.candidates
            ]

        if not symbols:
            return

        request = self.stream.chart_equity(
            symbols,
            "0,1,2,3,4,5,6,7,8",
            command="ADD",
        )

        self.stream.send(request)

    # ========================================================
    # CHART PROCESSING
    # ========================================================

    def process_chart(self, service):

        content = service.get(
            "content",
            [],
        )

        for row in content:

            symbol = row.get(
                "key"
            )

            if not symbol:
                continue

            timestamp = safe_int(
                row.get("7")
            )

            if not timestamp:
                continue

            candle = Candle(
                timestamp=timestamp,

                open=safe_float(
                    row.get("2")
                ),

                high=safe_float(
                    row.get("3")
                ),

                low=safe_float(
                    row.get("4")
                ),

                close=safe_float(
                    row.get("5")
                ),

                volume=safe_int(
                    row.get("6")
                ),
            )

            with self.lock:

                self.live_candles[
                    symbol
                ] = candle

                candidate = (
                    self.candidates.get(
                        symbol
                    )
                )

                if candidate:

                    candidate.price = (
                        candle.close
                    )

                    candidate.five_min_volume = (
                        candle.volume
                    )

                    self.update_rvol(
                        candidate,
                        candle,
                    )

    # ========================================================
    # RVOL
    # ========================================================

    def update_rvol(
        self,
        candidate,
        candle,
    ):

        if not is_regular_session(
            candle.timestamp
        ):

            return

        historical = (
            self.historical_volume.get(
                candidate.symbol
            )
        )

        if not historical:
            return

        key = slot_key(
            candle.timestamp
        )

        expected = historical.get(
            key
        )

        if not expected or expected <= 0:

            return

        candidate.expected_volume = (
            expected
        )

        candidate.rvol = (
            candle.volume
            / expected
        )

    # ========================================================
    # FILTER
    # ========================================================

    @staticmethod
    def qualifies(candidate):

        if candidate.price < MIN_PRICE:
            return False

        if candidate.day_volume < MIN_DAY_VOLUME:
            return False

        return True

    # ========================================================
    # SCORE
    # ========================================================

    @staticmethod
    def calculate_score(candidate):

        #
        # Momentum:
        #
        # 10% or greater = max.
        #

        momentum = min(
            abs(
                candidate.change_percent
            ) / 10,
            1,
        )

        #
        # RVOL:
        #
        # 5x or greater = max.
        #

        rvol = min(
            candidate.rvol / 5,
            1,
        )

        #
        # Dollar liquidity:
        #
        # $100M/day = max.
        #

        dollar_volume = (
            candidate.price
            * candidate.day_volume
        )

        liquidity = min(
            dollar_volume
            / 100_000_000,
            1,
        )

        #
        # Activity:
        #
        # Reward appearance in multiple
        # market screeners.
        #

        appearances = sum(
            rank is not None
            for rank in [
                candidate.winner_rank,
                candidate.loser_rank,
                candidate.volume_rank,
                candidate.trades_rank,
            ]
        )

        activity = min(
            appearances / 3,
            1,
        )

        score = (
            momentum * MOMENTUM_WEIGHT
            + rvol * RVOL_WEIGHT
            + liquidity * LIQUIDITY_WEIGHT
            + activity * ACTIVITY_WEIGHT
        )

        return round(
            score,
            1,
        )

    # ========================================================
    # RESULTS
    # ========================================================

    def get_candidates(self):

        with self.lock:

            rows = list(
                self.candidates.values()
            )

            for candidate in rows:

                candidate.score = (
                    self.calculate_score(
                        candidate
                    )
                )

            return rows

    # ========================================================
    # DISPLAY
    # ========================================================

    def render(self):

        rows = self.get_candidates()

        qualified = [
            row
            for row in rows
            if self.qualifies(row)
        ]

        winners = sorted(
            [
                row
                for row in qualified
                if row.change_percent > 0
            ],
            key=lambda x:
                x.change_percent,
            reverse=True,
        )

        losers = sorted(
            [
                row
                for row in qualified
                if row.change_percent < 0
            ],
            key=lambda x:
                x.change_percent,
        )

        high_rvol = sorted(
            qualified,
            key=lambda x:
                x.rvol,
            reverse=True,
        )

        overall = sorted(
            qualified,
            key=lambda x:
                x.score,
            reverse=True,
        )

        print(
            "\033[2J\033[H"
        )

        print(
            "=============================================================="
        )

        print(
            "             SCHWAB MARKET MOVER SCANNER"
        )

        print(
            "=============================================================="
        )

        print(
            f"Candidates: {len(rows)} | "
            f"5m RVOL baseline: {HISTORY_DAYS} days"
        )

        self.print_table(
            "TOP WINNERS",
            winners,
        )

        self.print_table(
            "TOP LOSERS",
            losers,
        )

        self.print_table(
            "HIGHEST RVOL",
            high_rvol,
        )

        self.print_table(
            "OVERALL SCORE",
            overall,
        )

    # ========================================================
    # TABLE
    # ========================================================

    @staticmethod
    def print_table(
        title,
        rows,
    ):

        print()
        print(
            f"--- {title} ---"
        )

        print(
            f"{'SYM':<7}"
            f"{'PRICE':>9}"
            f"{'CHG%':>10}"
            f"{'RVOL':>9}"
            f"{'5M VOL':>12}"
            f"{'DAY VOL':>13}"
            f"{'TRADES':>10}"
            f"{'SCORE':>8}"
        )

        print(
            "-" * 88
        )

        for row in rows[
            :DISPLAY_ROWS
        ]:

            print(
                f"{row.symbol:<7}"
                f"{row.price:>9.2f}"
                f"{row.change_percent:>9.2f}%"
                f"{row.rvol:>8.2f}x"
                f"{row.five_min_volume:>12,}"
                f"{row.day_volume:>13,}"
                f"{row.trades:>10,}"
                f"{row.score:>8.1f}"
            )

    # ========================================================
    # RUN
    # ========================================================

    def run(self):

        print(
            "Creating Schwab connection..."
        )

        self.stream.start(
            receiver=self.on_message
        )

        self.subscribe_screeners()

        print()
        print(
            "Waiting for market-wide candidates..."
        )

        try:

            while True:

                time.sleep(
                    DISPLAY_INTERVAL
                )

                self.render()

        except KeyboardInterrupt:

            print(
                "\nStopping..."
            )

        finally:

            self.running = False

            self.stream.stop()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    scanner = MarketScanner()

    scanner.run()
