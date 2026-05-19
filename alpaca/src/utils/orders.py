# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/src/utils/orders.py
# ================================================================================

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest
from alpaca.trading.enums import QueryOrderStatus, OrderSide, TimeInForce, OrderType

from utils.logger import get_logger
from utils.atr import calculate_atr
from utils.market import get_bars

logger = get_logger(__name__)


def calculate_quantity(
    trading_client: TradingClient,
    entry_price: float,
    stop_loss_pct: float,
    risk_per_trade: float,
    max_position_pct: float,
) -> int:
    """Calculate share quantity using risk, position, and buying power limits."""
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
            f"Equity: ${equity:,.2f} | RiskQty={risk_based} | PosQty={position_based} | "
            f"BPQty={buying_power_based} → Final Qty: {final_qty}"
        )
        return final_qty
    except Exception as e:
        logger.warning(f"calculate_quantity failed: {e}, defaulting to 1")
        return 1


def cancel_open_orders(trading_client: TradingClient, symbol: str) -> int:
    """Cancel all open orders for a symbol. Returns number cancelled."""
    try:
        open_orders = trading_client.get_orders(
            GetOrdersRequest(symbol=symbol, status=QueryOrderStatus.OPEN)
        )
        for order in open_orders:
            trading_client.cancel_order_by_id(order.id)
        return len(open_orders)
    except Exception as e:
        logger.warning(f"cancel_open_orders failed for {symbol}: {e}")
        return 0


def get_account_info(trading_client: TradingClient, risk_per_trade: float) -> str:
    """Return startup account summary."""
    account = trading_client.get_account()
    return (
        f"🤖 *Bot Started*\n"
        f"Equity: `${float(account.equity):,.2f}`\n"
        f"Risk per Trade: {risk_per_trade * 100}%"
    )


def get_position(trading_client: TradingClient, symbol: str):
    """Return open position or None."""
    try:
        return trading_client.get_open_position(symbol)
    except Exception:
        return None


def get_atr_trailing_stop_price(current_price: float, atr: float, multiplier: float) -> float:
    """Calculate trailing stop price for a long position."""
    distance = atr * multiplier
    return round(current_price - distance, 2)


def update_atr_trailing_stop(
    trading_client: TradingClient,
    data_client,
    symbol: str,
    cfg
) -> bool:
    """Update trailing stop using ATR (Wilder's or Simple)."""
    if not getattr(cfg.risk, 'trailing_stop_enabled', False):
        return False

    try:
        position = get_position(trading_client, symbol)
        if not position:
            return False

        df = get_bars(data_client, symbol, cfg.trading.alpaca_timeframe, limit=150)

        # Use config toggle for Wilder’s method
        atr = calculate_atr(
            df, 
            period=cfg.risk.atr_period,
            wilder=cfg.risk.use_wilder_atr
        )

        if atr is None:
            return False

        current_price = float(position.current_price)
        trail_price = get_atr_trailing_stop_price(
            current_price, atr, cfg.risk.atr_multiplier
        )

        cancel_open_orders(trading_client, symbol)

        order = MarketOrderRequest(
            symbol=symbol,
            qty=float(position.qty),
            side=OrderSide.SELL,
            type=OrderType.STOP,
            time_in_force=TimeInForce.GTC,
            stop_price=trail_price,
        )

        trading_client.submit_order(order)

        method = "Wilder's" if cfg.risk.use_wilder_atr else "Simple"
        logger.info(
            f"✅ {method} ATR Trailing Stop updated → {symbol} @ ${trail_price:.2f} "
            f"(ATR=${atr:.3f} × {cfg.risk.atr_multiplier})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to update ATR trailing stop for {symbol}: {e}")
        return False
    
    
def manage_trailing_stops(trading_client, data_client, cfg) -> None:
    """
    Update ATR trailing stops for all open positions.
    Shared across ma_trader.py, smart_ma_trader.py, and agent_trader.py.
    """
    if not getattr(cfg.risk, 'trailing_stop_enabled', False):
        return

    method = "Wilder's Smoothed" if getattr(cfg.risk, 'use_wilder_atr', True) else "Simple"

    for symbol in cfg.trading.symbols:
        try:
            if get_position(trading_client, symbol):
                success = update_atr_trailing_stop(trading_client, data_client, symbol, cfg)
                if success:
                    logger.debug(f"[{method} ATR] Trailing stop updated for {symbol}")
        except Exception as e:
            logger.error(f"Trailing stop update failed for {symbol}: {e}")