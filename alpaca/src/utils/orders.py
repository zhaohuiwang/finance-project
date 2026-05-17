from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

from utils.logger import get_logger

logger = get_logger(__name__)


def calculate_quantity(
    trading_client: TradingClient,
    entry_price: float,
    stop_loss_pct: float,
    risk_per_trade: float,
) -> int:
    """Calculate share quantity based on account equity, risk per trade, and buying power.

    Caps result between 1 and 200 shares. Returns 1 as a safe fallback on API errors.
    """
    try:
        account = trading_client.get_account()
        equity = float(account.equity)
        buying_power = float(account.buying_power)

        risk_amount = equity * risk_per_trade
        stop_distance = entry_price * stop_loss_pct

        shares = int(risk_amount / stop_distance) if stop_distance > 0 else 1
        shares = max(1, min(shares, 200))
        max_by_bp = int(buying_power / (entry_price * 1.02))

        final_qty = max(1, min(shares, max_by_bp))
        logger.info(f"Equity: ${equity:,.2f} | Risk: ${risk_amount:.2f} | Qty: {final_qty}")
        return final_qty
    except Exception as e:
        logger.warning(f"calculate_quantity failed ({e}), defaulting to 1")
        return 1


def cancel_open_orders(trading_client: TradingClient, symbol: str) -> int:
    """Cancel all open orders for the symbol. Returns the number of orders cancelled."""
    try:
        open_orders = trading_client.get_orders(
            GetOrdersRequest(symbol=symbol, status=QueryOrderStatus.OPEN)
        )
        for order in open_orders:
            trading_client.cancel_order_by_id(order.id)
        return len(open_orders)
    except Exception as e:
        logger.warning(f"cancel_open_orders failed ({e})")
        return 0


def get_account_info(trading_client: TradingClient, risk_per_trade: float) -> str:
    """Fetch account equity and return a formatted startup summary string."""
    account = trading_client.get_account()
    return (
        f"🤖 *Bot Started*\n"
        f"Equity: `${float(account.equity):.2f}`\n"
        f"Risk per Trade: {risk_per_trade * 100}%"
    )


def get_position(trading_client: TradingClient, symbol: str):
    """Return the open position for the given symbol, or None if no position exists."""
    try:
        return trading_client.get_open_position(symbol)
    except Exception:
        return None
