
""""
How the Main Loop Works
Pythonwhile running:
    1. Receive new price quote
    2. Check if within allowed trading hours
    3. Check if daily loss limit is breached → halt if yes
    4. Calculate recent price movement (up/down)
    5. If strong UP + holding shares → Place Trailing Sell
    6. If strong DOWN + no shares → Place Trailing Buy
    7. Log everything + send Telegram alert

Flow Example
Price drops 3.2% in last 20 minutes → Bot places Trailing Buy order
Price later rebounds → Buy order fills
Price then rises 4.1% in 15 minutes → Bot places Trailing Sell order
Price continues rising → Trailing stop eventually sells at a profit

"""


import asyncio
import datetime as dt
import logging
import csv
import os
from collections import deque
from pathlib import Path
from typing import Optional

import requests
import yaml
import pytz
from pydantic import BaseModel, Field, field_validator, model_validator

from schwab_trader.accounts.schwab import client, SchwabAccount
from schwab_trader.orders.equity import buy_trailing_stop_dict, sell_trailing_stop_dict
from schwab_trader.orders.utils import place_order

_NY_TZ = pytz.timezone("America/New_York")

# ========================= PYDANTIC CONFIG =========================
class TelegramConfig(BaseModel):
    enabled: bool = False
    token: Optional[str] = None
    chat_id: Optional[str] = None


class TradingConfig(BaseModel):
    symbol: str = "NBIS"
    account_number: str

    # Strategy
    up_pct: float = Field(3.0, gt=0)
    up_window_min: int = Field(15, gt=0)
    down_pct: float = Field(2.5, gt=0)
    down_window_min: int = Field(20, gt=0)
    buy_quantity: int = Field(50, gt=0)
    trailing_stop_pct: float = Field(2.0, gt=0)

    # Risk Management
    daily_max_loss_pct: float = Field(3.0, gt=0, le=20)
    max_position_shares: int = Field(200, gt=0)

    # Trading Hours
    trade_only_regular_hours: bool = True
    trade_pre_market: bool = False      # 04:00 - 09:30 ET
    trade_after_hours: bool = False     # 16:00 - 20:00 ET

    market_open_time: str = "09:30"
    market_close_time: str = "16:00"

    # Operation
    check_interval_sec: int = Field(5, gt=0)

    # Logging
    log_file: str = "logs/nbis_trades.csv"

    # Telegram
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)

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
        if self.market_open_time >= self.market_close_time:
            raise ValueError("market_open_time must be before market_close_time")
        return self


def load_config() -> TradingConfig:
    config_path = Path("config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return TradingConfig(**data)


cfg = load_config()

# ========================= LOGGING =========================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ========================= MARKET HOURS =========================
def is_market_open() -> bool:
    """Check if current time is within allowed trading sessions."""
    now = dt.datetime.now(_NY_TZ)
    current_time = now.time()

    # Regular Hours
    open_time = dt.datetime.strptime(cfg.market_open_time, "%H:%M").time()
    close_time = dt.datetime.strptime(cfg.market_close_time, "%H:%M").time()

    in_regular_hours = open_time <= current_time < close_time

    if cfg.trade_only_regular_hours:
        return in_regular_hours

    # Pre-Market (typically 4:00 - 9:30)
    if cfg.trade_pre_market and current_time < open_time:
        return True

    # After-Hours (typically 16:00 - 20:00)
    if cfg.trade_after_hours and current_time >= close_time:
        return True

    return in_regular_hours


def send_telegram(message: str):
    if not cfg.telegram.enabled or not cfg.telegram.token or not cfg.telegram.chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{cfg.telegram.token}/sendMessage"
        payload = {"chat_id": cfg.telegram.chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")


# ========================= CSV LOGGER =========================
def init_trade_log():
    if not os.path.exists(cfg.log_file):
        os.makedirs(os.path.dirname(cfg.log_file), exist_ok=True)
        with open(cfg.log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "action", "symbol", "quantity", "price", "reason", "order_id"])


def log_trade(action: str, qty: int, price: float | None, reason: str, order_id: str = ""):
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(cfg.log_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, action, cfg.symbol, qty, f"{price:.4f}" if price else "", reason, order_id])

    logger.info(f"TRADE LOGGED | {action} {qty} {cfg.symbol} | {reason}")
    send_telegram(f"*{action}* {qty} *{cfg.symbol}*\n{reason}\nPrice: ${price:.2f}" if price else f"*{action}* {qty} *{cfg.symbol}*\n{reason}")


# ========================= ACCOUNT & RISK =========================
response = client.linked_accounts()
data = response.json()
hashValue = next((item["hashValue"] for item in data if item["accountNumber"] == cfg.account_number), None)

if not hashValue:
    raise ValueError(f"Account hash not found for {cfg.account_number}!")

account = SchwabAccount(client, hashValue)
price_window = deque(maxlen=2000)

daily_start_equity = None
daily_start_date = None


def get_daily_loss_pct() -> float:
    global daily_start_equity, daily_start_date
    try:
        today = dt.date.today()
        if daily_start_date != today or daily_start_equity is None:
            account.refresh()
            daily_start_equity = float(account.equity)
            daily_start_date = today
        account.refresh()
        current_equity = float(account.equity)
        return (daily_start_equity - current_equity) / daily_start_equity * 100
    except:
        return 0.0


def is_trading_halted() -> bool:
    loss = get_daily_loss_pct()
    if loss >= cfg.daily_max_loss_pct:
        logger.warning(f"🚨 DAILY LOSS LIMIT REACHED: {loss:.1f}%")
        send_telegram(f"⚠️ *Daily Loss Limit Reached* ({loss:.1f}%)")
        return True
    return False


def get_position_qty() -> int:
    try:
        account.refresh()
        pos = account.get_position(cfg.symbol)
        return int(pos.quantity) if pos else 0
    except:
        return 0


# ========================= ORDER FUNCTIONS =========================
def place_trailing_sell(qty: int, current_price: float):
    try:
        order_dict = buy_trailing_stop_dict(
            symbol=cfg.symbol,
            quantity=qty,
            stop_price_link_basis="MARK",
            stop_price_link_type="PERCENT",
            stop_price_offset=cfg.trailing_stop_pct,
            session="NORMAL",
            duration="DAY",
            ) 
        
        status_code, _, order_id = place_order(client=client, accountHash=hashValue, order=order_dict)
        if status_code == 201:
            log_trade("TRAILING_SELL", qty, current_price, f"+{cfg.up_pct}% surge", order_id)
            return True
        return False
    except Exception as e:
        logger.error(f"Trailing sell failed: {e}")
        return False


def place_trailing_buy(qty: int, current_price: float):
    try:
        order_dict = buy_trailing_stop_dict(
            symbol=cfg.symbol,
            quantity=qty,
            stop_price_link_basis="MARK",
            stop_price_link_type="PERCENT",
            stop_price_offset=cfg.trailing_stop_pct,
            session="NORMAL",
            duration="DAY",
            ) 
        
        status_code, _, order_id = place_order(client=client, accountHash=hashValue, order=order_dict)
        if status_code == 201:
            log_trade("TRAILING_BUY", qty, current_price,
                     f"-{cfg.down_pct}% dip → Trailing Buy", order_id)
            return True
    except Exception:
        pass  # fallback

    # Fallback limit buy
    try:
        from schwab_trader.orders.equity import buy_limit_dict
        limit_price = round(current_price * 0.992, 2)
        order_dict = buy_limit_dict(
            symbol=cfg.symbol,
            quantity=qty,
            limit_price=limit_price,
            session="NORMAL",
            duration="DAY"
        )
        status_code, _, order_id = place_order(client=client, accountHash=hashValue, order=order_dict)
        if status_code == 201:
            log_trade("LIMIT_BUY", qty, current_price, f"Fallback @ ${limit_price}", order_id)
            return True
    except Exception as e:
        logger.error(f"Buy order failed: {e}")
    return False


# ========================= STREAMING CALLBACK =========================
async def on_quote(data):
    try:
        price = None
        if isinstance(data, dict):
            price = data.get('lastPrice') or data.get('bidPrice') or data.get('askPrice')
        elif isinstance(data, (int, float)):
            price = float(data)

        if not price:
            return

        now = dt.datetime.now()
        price_window.append((now, price))

        if not is_market_open():
            return

        if is_trading_halted():
            return

        position_qty = get_position_qty()
        logger.info(f"📡 {cfg.symbol} @ ${price:.2f} | Pos: {position_qty}/{cfg.max_position_shares}")

        # UP MOVE → Trailing Sell
        if len(price_window) >= 10:
            window_start = now - dt.timedelta(minutes=cfg.up_window_min)
            recent = [p for t, p in price_window if t >= window_start]
            if recent:
                min_p = min(recent)
                pct_up = (price - min_p) / min_p * 100
                if pct_up >= cfg.up_pct and position_qty > 0:
                    logger.warning(f"🔥 +{pct_up:.1f}% surge!")
                    place_trailing_sell(position_qty, price)

        # DOWN MOVE → Trailing Buy
        if len(price_window) >= 10:
            window_start = now - dt.timedelta(minutes=cfg.down_window_min)
            recent = [p for t, p in price_window if t >= window_start]
            if recent:
                max_p = max(recent)
                pct_down = (max_p - price) / max_p * 100
                if (pct_down >= cfg.down_pct and 
                    position_qty == 0 and 
                    position_qty + cfg.buy_quantity <= cfg.max_position_shares):
                    
                    logger.warning(f"📉 -{pct_down:.1f}% dip!")
                    place_trailing_buy(cfg.buy_quantity, price)

    except Exception as e:
        logger.debug(f"Quote error: {e}")


# ========================= MAIN =========================
async def main():
    hours_info = f"Regular: {cfg.market_open_time}-{cfg.market_close_time}"
    if cfg.trade_pre_market:
        hours_info += " + Pre-market"
    if cfg.trade_after_hours:
        hours_info += " + After-hours"
    
    logger.info(f"🚀 NBIS Bot Started | {cfg.symbol} | {hours_info}")
    send_telegram(f"🚀 *NBIS Bot Started*\n{hours_info} ET")

    try:
        logger.info("Streaming quotes initialized...")
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
        send_telegram("⛔ *Bot Stopped*")
    except Exception as e:
        logger.error(f"Error: {e}")
        send_telegram(f"❌ *Bot Error*: {str(e)[:150]}")


if __name__ == "__main__":
    init_trade_log()
    asyncio.run(main())