# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/scripts/smart_ma_trader.py
# ================================================================================

"""
Smart MA Trading Bot with ATR Trailing Stops

Based on ma_trader.py with the following enhancements:
- Claude (SignalAgent) for signal generation using MA + RSI + Volume + News
- Everything else (risk, execution, trailing stops, logging, etc.) kept consistent
"""

import os
import re
import time
import socket

import pytz
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient, NewsClient
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from config import load_config
from utils.logger import setup_logging, get_logger
from utils.market import is_market_hours, get_latest_ask
from utils.notify import notify
from utils.trade_log import init_trade_log, log_trade
from utils.orders import (
    calculate_quantity,
    cancel_open_orders,
    get_account_info,
    get_position,
    manage_trailing_stops,
    update_atr_trailing_stop,
)
from utils.risk import DailyLossGuard, StopLossCooldown
from agents.signal_agent import SignalAgent

setup_logging()
logger = get_logger(__name__)

# Prefer IPv4
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
    logger.info("Running in PAPER TRADING mode (smart + ATR)")
else:
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    logger.warning("RUNNING IN LIVE REAL MONEY MODE - BE CAREFUL!")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=cfg.trading.paper_trading)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
news_client = NewsClient(API_KEY, SECRET_KEY)

NY_TZ = pytz.timezone("America/New_York")


def trade_symbol(
    symbol: str, signal_agent: SignalAgent, cooldown: StopLossCooldown
) -> None:
    """Signal from Claude + deterministic execution (aligned with ma_trader.py)."""

    # === Claude Signal (the only major difference) ===
    result = signal_agent.analyze(symbol)
    signal = result["signal"]
    confidence = result["confidence"]
    reasoning = result["reasoning"]
    current_price = result["current_price"]

    position = get_position(trading_client, symbol)
    has_position = position is not None
    cooldown.update(symbol, has_position)

    logger.info(
        f"{symbol} @ ${current_price:.2f} | Signal: {signal} ({confidence:.0%}) | {reasoning[:80]}"
    )

    # Skip low-confidence signals
    if signal != "HOLD" and confidence < cfg.strategy.min_signal_confidence:
        logger.info(f"{symbol} low confidence ({confidence:.0%}) — treated as HOLD")
        return

    if signal == "HOLD":
        return

    # ==================== BUY (identical logic to ma_trader) ====================
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
                "Smart: Claude + News + ATR Trail",
                f"TP={tp_price} | InitStop={initial_stop}",
            )
            notify(
                f"🟢 *BUY (smart)*\n{symbol} × {qty} @ ~${base_price:.2f} | "
                f"TP=${tp_price}\n_{reasoning[:140]}_"
            )
        except Exception as e:
            logger.error(f"BUY order failed for {symbol}: {e}", exc_info=True)
            notify(f"❌ BUY failed for {symbol}: {str(e)[:120]}")

    # ==================== SELL (identical logic to ma_trader) ====================
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
                "Smart: Claude Exit",
            )
            notify(f"🔴 *SELL (smart)*\n{symbol} × {qty} @ ~${current_price:.2f}")
        except Exception as e:
            logger.error(f"SELL order failed for {symbol}: {e}", exc_info=True)
            notify(f"❌ SELL failed for {symbol}: {str(e)[:100]}")


def main() -> None:
    init_trade_log(cfg.trading.log_file)  # dated file handled inside
    logger.info(
        f"Starting Smart MA Bot with ATR Trailing Stops — symbols: {cfg.trading.symbols}"
    )
    notify(get_account_info(trading_client, cfg.risk.risk_per_trade))

    loss_guard = DailyLossGuard(trading_client, cfg.risk.daily_max_loss_pct)
    cooldown = StopLossCooldown(trading_client, cfg.risk.stop_loss_cooldown_minutes)
    signal_agent = SignalAgent(data_client, news_client, cfg)

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
                trade_symbol(symbol, signal_agent, cooldown)
            except Exception as e:
                logger.error(f"{symbol} error: {e}", exc_info=True)
                notify(f"⚠️ {symbol} error: {e}")

        # === ATR Trailing Stop Management (same as ma_trader) ===
        manage_trailing_stops(trading_client, data_client, cfg)

        time.sleep(cfg.trading.check_interval)


if __name__ == "__main__":
    main()
