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
    max_position_pct: float,
) -> int:
    """Calculate share quantity using three independent caps, taking the smallest.

    - risk_based:     risk_per_trade % of equity / stop distance  (primary sizing)
    - position_based: max_position_pct % of equity / entry_price  (concentration limit)
    - buying_power:   available buying power / entry_price         (liquidity constraint)

    Returns 1 as a safe fallback on API errors.
    """
    try:
        account = trading_client.get_account()
        equity = float(account.equity)
        buying_power = float(account.buying_power)

        stop_distance = entry_price * stop_loss_pct
        risk_based = int((equity * risk_per_trade) / stop_distance) if stop_distance > 0 else 1
        position_based = int((equity * max_position_pct) / entry_price)
        buying_power_based = int(buying_power / (entry_price * 1.02))

        final_qty = max(1, min(risk_based, position_based, buying_power_based))
        logger.info(
            f"Equity: ${equity:,.2f} | "
            f"risk_based={risk_based} | position_based={position_based} | "
            f"bp_based={buying_power_based} | Qty: {final_qty}"
        )
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
