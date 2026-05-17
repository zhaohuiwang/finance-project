from datetime import date, datetime, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderType
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

from utils.logger import get_logger

logger = get_logger(__name__)


class DailyLossGuard:
    """Halts trading for the rest of the day once equity drops beyond a threshold.

    Resets automatically at the start of each new calendar day.
    """

    def __init__(self, trading_client: TradingClient, max_loss_pct: float) -> None:
        self._client = trading_client
        self._max_loss_pct = max_loss_pct
        self._start_equity: float | None = None
        self._tracking_date: date | None = None

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if self._tracking_date != today:
            equity = float(self._client.get_account().equity)
            self._start_equity = equity
            self._tracking_date = today
            logger.info(f"Daily loss guard reset — start equity: ${equity:,.2f} | Loss limit: {self._max_loss_pct:.1%}")

    def is_halted(self) -> bool:
        """Return True if today's drawdown has exceeded the daily max-loss limit."""
        try:
            self._reset_if_new_day()
            current_equity = float(self._client.get_account().equity)
            daily_loss_pct = (self._start_equity - current_equity) / self._start_equity
            if daily_loss_pct >= self._max_loss_pct:
                logger.warning(
                    f"Daily loss limit breached: {daily_loss_pct:.2%} loss "
                    f"(limit: {self._max_loss_pct:.1%}) — halting trading for today"
                )
                return True
            return False
        except Exception as e:
            logger.warning(f"DailyLossGuard check failed ({e}) — allowing trading to continue")
            return False


class StopLossCooldown:
    """Blocks re-entry for a fixed window after a bracket stop loss fires.

    Distinguishes stop-loss exits from signal-based SELLs by tracking which
    closes were initiated by the bot vs. Alpaca's bracket engine.
    """

    def __init__(self, trading_client: TradingClient, cooldown_minutes: int) -> None:
        self._client = trading_client
        self._cooldown_seconds = cooldown_minutes * 60
        self._had_position: dict[str, bool] = {}
        self._signal_sold: set[str] = set()
        self._cooldown_until: dict[str, datetime] = {}

    def record_signal_sell(self, symbol: str) -> None:
        """Call this before placing a signal-driven SELL so it isn't mistaken for a stop."""
        self._signal_sold.add(symbol)

    def update(self, symbol: str, has_position: bool) -> None:
        """Detect position closures and start cooldown if the exit was a stop loss."""
        prev = self._had_position.get(symbol, has_position)
        if prev and not has_position:
            if symbol in self._signal_sold:
                # We sent this SELL — not a stop loss
                self._signal_sold.discard(symbol)
            elif self._last_exit_was_stop(symbol):
                until = datetime.now() + timedelta(seconds=self._cooldown_seconds)
                self._cooldown_until[symbol] = until
                logger.warning(
                    f"{symbol} stop loss detected — BUY blocked for "
                    f"{self._cooldown_seconds // 60}m (until {until.strftime('%H:%M:%S')})"
                )
        self._had_position[symbol] = has_position

    def is_cooling_down(self, symbol: str) -> bool:
        """Return True if the symbol is still within the post-stop-loss cooldown window."""
        until = self._cooldown_until.get(symbol)
        if until and datetime.now() < until:
            remaining = int((until - datetime.now()).total_seconds() / 60)
            logger.info(f"{symbol} in stop-loss cooldown — {remaining}m remaining, skipping BUY")
            return True
        return False

    def _last_exit_was_stop(self, symbol: str) -> bool:
        """Query recent closed orders to check if the last filled sell was a stop order."""
        try:
            orders = self._client.get_orders(
                GetOrdersRequest(symbol=symbol, status=QueryOrderStatus.CLOSED, limit=10)
            )
            filled_sells = [
                o for o in orders
                if o.side == o.side.SELL and o.filled_at is not None
            ]
            if not filled_sells:
                return False
            most_recent = max(filled_sells, key=lambda o: o.filled_at)
            return most_recent.order_type in (OrderType.STOP, OrderType.STOP_LIMIT)
        except Exception as e:
            logger.warning(f"{symbol} could not determine exit type ({e}) — skipping cooldown")
            return False
