

#===============================================================================
# FILE: alpaca momentum trader

# python3 scripts/momentum_bot.py
# $ ps aux | grep momentum_bot
# $ kill -9 54121

# One line to kill all momentun bot processes:
# $ pkill -f momentum_bot.py
# $ pkill -9 -f momentum_bot.py
# $ ps aux | grep -E 'momentum_bot.py|uv run' | grep -v grep | awk '{print $2}' | xargs -r kill -9
#===============================================================================

import asyncio
import datetime as dt
import logging
import csv
import os
import time
from collections import deque
from pathlib import Path
from typing import Optional

import pytz
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed

from config import load_config  
from utils.logger import setup_logging, get_logger
from utils.market import is_market_hours
from utils.notify import notify
from utils.trade_log import init_trade_log, log_trade

# Optional: Reuse DailyLossGuard if it exists in utils/risk.py
try:
    from utils.risk import DailyLossGuard
except ImportError:
    class DailyLossGuard:
        def __init__(self, trading_client, daily_max_loss_pct: float):
            self.trading_client = trading_client
            self.daily_max_loss_pct = daily_max_loss_pct
            self.daily_start_equity = None
            self.daily_start_date = None

        def is_halted(self) -> bool:
            try:
                today = dt.date.today()
                if self.daily_start_date != today or self.daily_start_equity is None:
                    account = self.trading_client.get_account()
                    self.daily_start_equity = float(account.equity)
                    self.daily_start_date = today
                account = self.trading_client.get_account()
                current_equity = float(account.equity)
                loss_pct = (self.daily_start_equity - current_equity) / self.daily_start_equity * 100
                if loss_pct >= self.daily_max_loss_pct:
                    logger.warning(f"🚨 DAILY LOSS LIMIT REACHED: {loss_pct:.1f}%")
                    return True
                return False
            except:
                return False

setup_logging()
logger = get_logger(__name__)

load_dotenv()

NY_TZ = pytz.timezone("America/New_York")

# ========================= PYDANTIC CONFIG =========================
class TelegramConfig(BaseModel):
    enabled: bool = False
    token: Optional[str] = None
    chat_id: Optional[str] = None


class TradingConfig(BaseModel):
    symbol: str = "APLD"
    # Strategy
    stop_price_link_type_sell: str = "PERCENT"
    up_value: float = Field(0.2, gt=0)
    up_window_min: int = Field(5, gt=0)
    down_value: float = Field(0.2, gt=0)
    down_window_min: int = Field(5, gt=0)
    buy_quantity: int = Field(50, gt=0)
    stop_price_offset_sell: float = Field(0.1, gt=0)
    stop_price_offset_buy: float = Field(0.1, gt=0)

    # Risk Management
    daily_max_loss_pct: float = Field(3.0, gt=0, le=20)
    max_position_shares: int = Field(200, gt=0)

    # Trading Hours
    trade_only_regular_hours: bool = True
    trade_pre_market: bool = False
    trade_after_hours: bool = False

    market_open_time: str = "09:30"
    market_close_time: str = "16:00"

    # Operation
    check_interval_sec: int = Field(5, gt=0)

    # Logging
    log_file: str = "logs/nbis_trades.csv"

    # Telegram (handled via utils.notify or direct)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)

    paper_trading: bool = True

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("market_open_time", "market_close_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        try:
            dt.datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            raise ValueError(f"Invalid time format '{v}'. Use HH:MM")

    @model_validator(mode="after")
    def validate_config(self):
        if self.daily_max_loss_pct > 10:
            raise ValueError("daily_max_loss_pct should be reasonable (≤10%)")
        to_time = lambda t: dt.datetime.strptime(t, "%H:%M").time()
        if to_time(self.market_open_time) >= to_time(self.market_close_time):
            raise ValueError("market_open_time must be before market_close_time")
        return self


# Load config (adapt load_config from your MA example or use this)
def load_momentum_config() -> TradingConfig:
    # Assuming config.yaml or similar in root
    config_path = Path("conf/momentum_config.yaml")
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return TradingConfig(**data)
    else:
        logger.warning("Config file not found, using defaults")
        return TradingConfig()


cfg = load_momentum_config()

# ==================== ALPACA CLIENTS ====================
if cfg.paper_trading:
    API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_PAPER_SECRET_KEY")
    logger.info("🚀 Running in PAPER TRADING mode")
else:
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    logger.warning("⚠️ RUNNING IN LIVE REAL MONEY MODE")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=cfg.paper_trading)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
stream = StockDataStream(API_KEY, SECRET_KEY, feed=DataFeed.IEX)  # or SIP for paid

price_window = deque(maxlen=2000)


def get_position_qty(symbol: str) -> int:
    try:
        position = trading_client.get_position(symbol)
        return int(float(position.qty))
    except Exception:
        return 0


def get_current_price(symbol: str) -> Optional[float]:
    try:
        quote = data_client.get_latest_quote(symbol)
        return float(quote.ask_price) or float(quote.bid_price)
    except:
        return None


# ========================= ORDER FUNCTIONS =========================
def place_trailing_sell(symbol: str, qty: int, current_price: float):
    """Place trailing stop sell order on Alpaca"""
    try:
        order_data = TrailingStopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            trail_percent=cfg.stop_price_offset_sell,  # e.g. 2%
            # Alternatively use trail_price for dollar offset
        )
        order = trading_client.submit_order(order_data)
        log_trade(
            cfg.log_file,
            symbol,
            "TRAILING_SELL",
            qty,
            current_price,
            f"+{cfg.up_value}% surge detected",
            str(order.id)
        )
        notify(f"🔴 *TRAILING SELL* {qty} {symbol} @ ~${current_price:.2f}")
        logger.info(f"✅ Trailing Sell placed for {qty} {symbol}")
        return True
    except Exception as e:
        logger.error(f"Trailing sell failed: {e}")
        return False


def place_trailing_buy(symbol: str, qty: int, current_price: float):
    """Place trailing stop buy order (or fallback market/limit)"""
    try:
        # Alpaca trailing stop for BUY is supported
        order_data = TrailingStopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            trail_percent=cfg.stop_price_offset_buy,
        )
        order = trading_client.submit_order(order_data)
        log_trade(
            cfg.log_file,
            symbol,
            "TRAILING_BUY",
            qty,
            current_price,
            f"-{cfg.down_value}% dip detected",
            str(order.id)
        )
        notify(f"🟢 *TRAILING BUY* {qty} {symbol} @ ~${current_price:.2f}")
        logger.info(f"✅ Trailing Buy placed for {qty} {symbol}")
        return True
    except Exception as e:
        logger.error(f"Trailing buy failed: {e}")
        # Fallback to market buy
        try:
            from alpaca.trading.requests import MarketOrderRequest
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
            )
            order = trading_client.submit_order(order_data)
            log_trade(cfg.log_file, symbol, "MARKET_BUY_FALLBACK", qty, current_price, "Trailing buy fallback")
            return True
        except Exception as fb_e:
            logger.error(f"Fallback buy also failed: {fb_e}")
    return False


# ========================= STREAM CALLBACK =========================
async def on_quote(data):
    try:
        if hasattr(data, 'price'):
            price = float(data.price)
        else:
            price = float(data.close) if hasattr(data, 'close') else None

        if not price:
            return

        now = dt.datetime.now(NY_TZ)
        price_window.append((now, price))

        if not is_market_hours(regular_only=cfg.trade_only_regular_hours):
            return

        loss_guard = DailyLossGuard(trading_client, cfg.daily_max_loss_pct)
        if loss_guard.is_halted():
            return

        position_qty = get_position_qty(cfg.symbol)
        logger.info(f"📡 {cfg.symbol} @ ${price:.2f} | Pos: {position_qty}/{cfg.max_position_shares}")

        # UP MOVE → Trailing Sell
        if len(price_window) >= 10:
            window_start = now - dt.timedelta(minutes=cfg.up_window_min)
            recent = [p for t, p in price_window if t >= window_start]
            if recent:
                min_p = min(recent)
                pct_up = (price - min_p) / min_p * 100
                if pct_up >= cfg.up_value and position_qty > 0:
                    logger.warning(f"🔥 +{pct_up:.1f}% surge in last {cfg.up_window_min} min!")
                    place_trailing_sell(cfg.symbol, position_qty, price)

        # DOWN MOVE → Trailing Buy
        if len(price_window) >= 10:
            window_start = now - dt.timedelta(minutes=cfg.down_window_min)
            recent = [p for t, p in price_window if t >= window_start]
            if recent:
                max_p = max(recent)
                pct_down = (max_p - price) / max_p * 100
                if (pct_down >= cfg.down_value and
                    position_qty == 0 and
                    cfg.buy_quantity <= cfg.max_position_shares):
                    logger.warning(f"📉 -{pct_down:.1f}% dip in last {cfg.down_window_min} min!")
                    place_trailing_buy(cfg.symbol, cfg.buy_quantity, price)

    except Exception as e:
        logger.debug(f"Quote processing error: {e}")


def run_stream():
    """Run the stream (blocking call)"""
    try:
        stream.subscribe_quotes(on_quote, cfg.symbol)
        logger.info(f"✅ Subscribed to real-time quotes for {cfg.symbol}")
        stream.run()          # This is the correct blocking call
    except Exception as e:
        logger.error(f"Stream run failed: {e}")
        notify(f"❌ Stream Error: {e}")
        
        
# ========================= MAIN =========================
async def main():
    mode = "🟦 PAPER TRADING" if cfg.paper_trading else "🔴 LIVE REAL MONEY"
    logger.info(f"🚀 Momentum Bot Started | {cfg.symbol} | {mode}")
    logger.info(f"UP: {cfg.up_value}% in {cfg.up_window_min}min | "
                f"DOWN: {cfg.down_value}% in {cfg.down_window_min}min")

    notify(f"🚀 *Momentum Bot Started*\n"
           f"{cfg.symbol} | {mode}\n"
           f"Surge {cfg.up_value}% | Dip {cfg.down_value}%")

    init_trade_log(cfg.log_file)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_stream)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}")