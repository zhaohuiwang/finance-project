# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/scripts/ma_trader.py
# There is ~ 10 min latency  for the price quote using free account. ================================================================================

"""
MA Crossover Trading Bot with ATR Trailing Stops

Strategy: EMA(3/8) crossover + RSI filter + Volume filter
Risk Management: Fixed initial stop + Dynamic ATR Trailing Stop
"""

import os
import re
import time
import socket

import pytz
from dotenv import load_dotenv

# ==================== ALPACA IMPORTS ====================
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit  # Added for 5m confirmation

from config import load_config
from utils.logger import setup_logging, get_logger
from utils.market import is_market_hours, get_bars, get_latest_ask
from utils.notify import notify
from utils.trade_log import init_trade_log, log_trade
from utils.signals import calculate_signals, is_uptrend
from utils.orders import (
    calculate_quantity,
    cancel_open_orders,
    get_account_info,
    get_position,
    manage_trailing_stops,
    update_atr_trailing_stop,
)
from utils.risk import DailyLossGuard, StopLossCooldown

setup_logging()
logger = get_logger(__name__)

# Prefer IPv4 to avoid connectivity issues
socket.setdefaulttimeout(15)
_orig_getaddrinfo = socket.getaddrinfo


def _force_ipv4(*args, **kwargs):
    return [r for r in _orig_getaddrinfo(*args, **kwargs) if r[0] == socket.AF_INET]


socket.getaddrinfo = _force_ipv4

load_dotenv()

cfg = load_config()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if cfg.trading.paper_trading:
    API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_PAPER_SECRET_KEY")
    logger.info("Running in PAPER TRADING mode")
else:
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    logger.warning("RUNNING IN LIVE REAL MONEY MODE - BE CAREFUL!")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=cfg.trading.paper_trading)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

NY_TZ = pytz.timezone("America/New_York")


def trade_symbol(symbol: str, cooldown: StopLossCooldown) -> None:
    """Run one iteration of the EMA crossover strategy."""
    df = get_bars(data_client, symbol, cfg.trading.alpaca_timeframe)
    signal, current_rsi = calculate_signals(
        df,
        cfg.strategy.fast_ma,
        cfg.strategy.slow_ma,
        cfg.strategy.rsi_period,
        cfg.strategy.rsi_max_for_buy,
        cfg.strategy.volume_min_ratio,
    )

    # 5-minute uptrend confirmation
    if signal == "BUY" and cfg.strategy.use_5m_confirmation:
        df_5m = get_bars(
            data_client, symbol, TimeFrame(5, TimeFrameUnit.Minute), limit=50
        )
        if not is_uptrend(df_5m, cfg.strategy.fast_ma, cfg.strategy.slow_ma):
            logger.info(f"{symbol} 5-min uptrend not confirmed — suppressing BUY")
            signal = None

    position = get_position(trading_client, symbol)
    has_position = position is not None
    current_price = float(df["close"].iloc[-1])

    cooldown.update(symbol, has_position)

    rsi_display = f"{current_rsi:.1f}" if current_rsi is not None else "N/A"
    logger.info(
        f"{symbol} @ ${current_price:.2f} | RSI: {rsi_display} | Signal: {signal or 'HOLD'}"
    )

    # ==================== BUY ====================
    if signal == "BUY" and not has_position and not cooldown.is_cooling_down(symbol):
        live_ask = get_latest_ask(data_client, symbol)
        base_price = (
            live_ask if live_ask and live_ask > current_price else current_price
        )

        qty = calculate_quantity(
            trading_client,
            base_price,
            cfg.risk.stop_loss_pct,
            cfg.risk.risk_per_trade,
            cfg.risk.max_position_pct,
        )

        initial_stop = round(base_price * (1 - cfg.risk.stop_loss_pct), 2)
        tp_price = (
            round(base_price * (1 + cfg.risk.take_profit_pct), 2)
            if cfg.risk.take_profit_pct
            else None
        )

        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            order_class="bracket",
            take_profit=dict(limit_price=tp_price) if tp_price else None,
            stop_loss=dict(stop_price=initial_stop),
        )

        try:
            trading_client.submit_order(order)
            log_trade(
                cfg.trading.log_file,
                symbol,
                "BUY",
                qty,
                base_price,
                "EMA Crossover + RSI + ATR Trail",
                f"TP={tp_price} | Initial Stop={initial_stop}",
            )
            notify(
                f"🟢 *BUY*\n{symbol} × {qty} @ ~${base_price:.2f} | "
                f"TP=${tp_price} | Stop=${initial_stop}"
            )
        except Exception as e:
            logger.error(f"BUY order failed for {symbol}: {e}", exc_info=True)
            notify(f"❌ BUY failed for {symbol}: {str(e)[:120]}")

    # ==================== SELL ====================
    elif signal == "SELL" and has_position:
        cooldown.record_signal_sell(symbol)
        qty = float(position.qty)
        cancelled = cancel_open_orders(trading_client, symbol)

        if cancelled:
            logger.info(f"{symbol} cancelled {cancelled} open order(s) before selling")

        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )

        try:
            trading_client.submit_order(order)
            log_trade(
                cfg.trading.log_file,
                symbol,
                "SELL",
                qty,
                current_price,
                "EMA Crossover Exit",
            )
            notify(f"🔴 *SELL*\n{symbol} × {qty} @ ~${current_price:.2f}")
        except Exception as e:
            logger.error(f"SELL order failed for {symbol}: {e}", exc_info=True)
            notify(f"❌ SELL failed for {symbol}: {str(e)[:100]}")


def main():
    dated_log_file = init_trade_log(cfg.trading.log_file)
    logger.info(
        f"Starting MA Trader with ATR Trailing Stops — symbols: {cfg.trading.symbols}"
    )
    notify(get_account_info(trading_client, cfg.risk.risk_per_trade))
    loss_guard = DailyLossGuard(trading_client, cfg.risk.daily_max_loss_pct)
    cooldown = StopLossCooldown(trading_client, cfg.risk.stop_loss_cooldown_minutes)

    while True:
        if not is_market_hours(regular_only=cfg.trading.trade_only_market_hours):
            logger.info("Outside market hours — waiting")
            time.sleep(60)
            continue

        if loss_guard.is_halted():
            logger.warning("Daily loss limit reached — trading halted for today")
            notify(f"⚠️ Daily loss limit ({cfg.risk.daily_max_loss_pct:.1%}) reached")
            time.sleep(60)
            continue

        for symbol in cfg.trading.symbols:
            try:
                trade_symbol(symbol, cooldown)
            except Exception as e:
                logger.error(f"{symbol} error: {e}", exc_info=True)
                notify(f"⚠️ {symbol} error: {e}")

        # Update ATR trailing stops
        manage_trailing_stops(trading_client, data_client, cfg)

        time.sleep(cfg.trading.check_interval)


if __name__ == "__main__":

    main()