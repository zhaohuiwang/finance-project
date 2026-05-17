from datetime import date

from alpaca.trading.client import TradingClient

from utils.logger import get_logger

logger = get_logger(__name__)


class DailyLossGuard:
    """Halts trading for the rest of the day once equity drops beyond a threshold.

    Resets automatically at the start of each new calendar day (NY time).
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
            logger.info(f"Daily loss guard reset — start equity: ${equity:,.2f} | limit: {self._max_loss_pct:.1%}")

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
