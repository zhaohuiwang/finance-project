"""
SMA Crossover Trading Bot

Strategy: Fast MA crosses above Slow MA + RSI below threshold → BUY
          Fast MA crosses below Slow MA → SELL (exit position)
"""
import os
import sys
import time
import socket
from pathlib import Path
from datetime import datetime

import pytz
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import load_config
from utils.market import is_market_open, get_bars, get_latest_ask
from utils.notify import send_telegram_message
from utils.trade_log import init_trade_log, log_trade
from utils.signals import calculate_signals
from utils.orders import calculate_quantity, cancel_open_orders, get_account_info, get_position


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
    print("🟢 Running in PAPER TRADING mode")
else:
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    print("🔴 RUNNING IN LIVE REAL MONEY MODE - BE CAREFUL!")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=cfg.trading.paper_trading)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

NY_TZ = pytz.timezone("America/New_York")


def notify(message: str) -> None:
    """Print and forward a message to Telegram."""
    print(message)
    send_telegram_message(message, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)


def main():
    init_trade_log(cfg.trading.log_file)
    print(f"🚀 Starting Enhanced {cfg.trading.symbol} Bot - {datetime.now()}")
    notify(get_account_info(trading_client, cfg.risk.risk_per_trade))

    while True:
        try:
            if not is_market_open(cfg.trading.trade_only_market_hours):
                print(f"{datetime.now(NY_TZ).strftime('%H:%M:%S')} | Outside Market Hours")
                time.sleep(60)
                continue

            df = get_bars(data_client, cfg.trading.symbol, cfg.trading.alpaca_timeframe)
            signal, current_rsi = calculate_signals(
                df,
                cfg.strategy.fast_ma,
                cfg.strategy.slow_ma,
                cfg.strategy.rsi_period,
                cfg.strategy.rsi_max_for_buy,
            )

            position = get_position(trading_client, cfg.trading.symbol)
            has_position = position is not None
            current_price = float(df["close"].iloc[-1])

            rsi_display = f"{current_rsi:.1f}" if current_rsi is not None else "N/A"
            print(
                f"{datetime.now().strftime('%H:%M:%S')} | {cfg.trading.symbol} @ ${current_price:.2f} | "
                f"RSI: {rsi_display} | Signal: {signal or 'HOLD'}"
            )

            if signal == "BUY" and not has_position:
                entry_price = current_price
                # Use the live ask as the reference Alpaca uses for bracket validation (base_price).
                # Bar close can lag behind the real ask, causing tp_price < base_price + 0.01.
                live_ask = get_latest_ask(data_client, cfg.trading.symbol)
                base_price = live_ask if live_ask and live_ask > entry_price else entry_price

                qty = calculate_quantity(trading_client, base_price, cfg.risk.stop_loss_pct, cfg.risk.risk_per_trade)

                tp_price = round(base_price * (1 + cfg.risk.take_profit_pct), 2) if cfg.risk.take_profit_pct else None
                if tp_price and tp_price <= base_price + 0.01:
                    tp_price = round(base_price + 0.02, 2)

                order = MarketOrderRequest(
                    symbol=cfg.trading.symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                    order_class="bracket",
                    take_profit=dict(limit_price=tp_price) if tp_price else None,
                    stop_loss=dict(
                        stop_price=round(base_price * (1 - cfg.risk.stop_loss_pct), 2),
                    ),
                )
                trading_client.submit_order(order)
                log_trade(cfg.trading.log_file, cfg.trading.symbol, "BUY", qty, base_price, "SMA Crossover + RSI", f"TP={tp_price}")
                notify(f"🟢 *BUY + Dynamic Risk*\n{cfg.trading.symbol} × {qty} @ ~${base_price:.2f}")

            elif signal == "SELL" and has_position:
                qty = float(position.qty)
                cancelled = cancel_open_orders(trading_client, cfg.trading.symbol)
                if cancelled:
                    print(f"Cancelled {cancelled} open bracket order(s) before selling")
                order = MarketOrderRequest(
                    symbol=cfg.trading.symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                )
                trading_client.submit_order(order)
                log_trade(cfg.trading.log_file, cfg.trading.symbol, "SELL", qty, current_price, "SMA Crossover Exit")
                notify(f"🔴 *SELL (Exit)*\n{cfg.trading.symbol} × {qty} @ ~${current_price:.2f}")

            time.sleep(cfg.trading.check_interval)

        except Exception as e:
            notify(f"⚠️ Error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
