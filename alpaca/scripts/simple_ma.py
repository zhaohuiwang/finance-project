"""
SMA Crossover Trading Bot

Strategy: Fast MA crosses above Slow MA + RSI below threshold → BUY
          Fast MA crosses below Slow MA → SELL (exit position)
"""
import os
import re
import sys
import time
import socket
from pathlib import Path

import pytz
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import load_config
from utils.logger import setup_logging, get_logger
from utils.market import is_market_open, get_bars, get_latest_ask
from utils.notify import send_telegram_message
from utils.trade_log import init_trade_log, log_trade
from utils.signals import calculate_signals
from utils.orders import calculate_quantity, cancel_open_orders, get_account_info, get_position
from utils.risk import DailyLossGuard

setup_logging()
logger = get_logger(__name__)

# Prefer IPv4 to avoid connectivity issues on dual-stack systems
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


def notify(message: str) -> None:
    """Log and forward a message to Telegram."""
    logger.info(message)
    send_telegram_message(message, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)


def trade_symbol(symbol: str) -> None:
    """Run one iteration of the SMA crossover strategy for a single symbol."""
    df = get_bars(data_client, symbol, cfg.trading.alpaca_timeframe)
    signal, current_rsi = calculate_signals(
        df,
        cfg.strategy.fast_ma,
        cfg.strategy.slow_ma,
        cfg.strategy.rsi_period,
        cfg.strategy.rsi_max_for_buy,
    )

    position = get_position(trading_client, symbol)
    has_position = position is not None
    current_price = float(df["close"].iloc[-1])

    rsi_display = f"{current_rsi:.1f}" if current_rsi is not None else "N/A"
    logger.info(f"{symbol} @ ${current_price:.2f} | RSI: {rsi_display} | Signal: {signal or 'HOLD'}")

    if signal == "BUY" and not has_position:
        entry_price = current_price
        live_ask = get_latest_ask(data_client, symbol)
        logger.debug(f"{symbol} live_ask={live_ask}, bar_close={entry_price:.2f}")
        base_price = live_ask if live_ask and live_ask > entry_price else entry_price

        qty = calculate_quantity(trading_client, base_price, cfg.risk.stop_loss_pct, cfg.risk.risk_per_trade)

        tp_price = round(base_price * (1 + cfg.risk.take_profit_pct), 2) if cfg.risk.take_profit_pct else None
        if tp_price and tp_price <= base_price + 0.01:
            tp_price = round(base_price + 0.02, 2)

        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            order_class="bracket",
            take_profit=dict(limit_price=tp_price) if tp_price else None,
            stop_loss=dict(stop_price=round(base_price * (1 - cfg.risk.stop_loss_pct), 2)),
        )
        try:
            trading_client.submit_order(order)
        except Exception as order_err:
            # Alpaca returns code 42210000 when tp < base_price + 0.01.
            # Extract its actual base_price from the error and retry once.
            match = re.search(r'"base_price"\s*:\s*"?([\d.]+)"?', str(order_err))
            if not match:
                raise
            alpaca_base = float(match.group(1))
            logger.warning(f"{symbol} TP validation failed — Alpaca base_price={alpaca_base}, retrying")
            tp_price = round(alpaca_base * (1 + cfg.risk.take_profit_pct), 2) if cfg.risk.take_profit_pct else None
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
                order_class="bracket",
                take_profit=dict(limit_price=tp_price) if tp_price else None,
                stop_loss=dict(stop_price=round(alpaca_base * (1 - cfg.risk.stop_loss_pct), 2)),
            )
            trading_client.submit_order(order)

        log_trade(cfg.trading.log_file, symbol, "BUY", qty, base_price, "SMA Crossover + RSI", f"TP={tp_price}")
        notify(f"🟢 *BUY*\n{symbol} x {qty} @ ~${base_price:.2f} | TP=${tp_price}")

    elif signal == "SELL" and has_position:
        qty = float(position.qty)
        cancelled = cancel_open_orders(trading_client, symbol)
        if cancelled:
            logger.info(f"{symbol} cancelled {cancelled} open bracket order(s) before selling")
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
        trading_client.submit_order(order)
        log_trade(cfg.trading.log_file, symbol, "SELL", qty, current_price, "SMA Crossover Exit")
        notify(f"🔴 *SELL*\n{symbol} x {qty} @ ~${current_price:.2f}")


def main():
    init_trade_log(cfg.trading.log_file)
    logger.info(f"Starting bot — symbols: {cfg.trading.symbols}")
    notify(get_account_info(trading_client, cfg.risk.risk_per_trade))

    loss_guard = DailyLossGuard(trading_client, cfg.risk.daily_max_loss_pct)

    while True:
        if not is_market_open(cfg.trading.trade_only_market_hours):
            logger.info("Outside market hours — waiting")
            time.sleep(60)
            continue

        if loss_guard.is_halted():
            logger.warning("Daily loss limit reached — skipping trading until tomorrow")
            notify(f"⚠️ Daily loss limit ({cfg.risk.daily_max_loss_pct:.1%}) reached — trading halted for today")
            time.sleep(60)
            continue

        for symbol in cfg.trading.symbols:
            try:
                trade_symbol(symbol)
            except Exception as e:
                logger.error(f"{symbol} error: {e}", exc_info=True)
                notify(f"⚠️ {symbol} error: {e}")

        time.sleep(cfg.trading.check_interval)


if __name__ == "__main__":
    main()
