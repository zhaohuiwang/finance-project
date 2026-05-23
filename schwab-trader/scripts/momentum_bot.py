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
from pydantic import BaseModel, Field, field_validator, model_validator

from schwab_trader.accounts.schwab import client, SchwabAccount
from schwab_trader.orders.equity import sell_trailing_stop_dict, buy_market_dict
from schwab_trader.orders.utils import place_order


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

    @model_validator(mode="after")
    def validate_config(self):
        if self.daily_max_loss_pct > 10:
            raise ValueError("daily_max_loss_pct should be reasonable (≤10%)")
        return self


def load_config() -> TradingConfig:
    config_path = Path("config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return TradingConfig(**data)


# Load config
cfg = load_config()

# ========================= LOGGING =========================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ========================= TELEGRAM =========================
def send_telegram(message: str):
    if not cfg.telegram.enabled or not cfg.telegram.token or not cfg.telegram.chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{cfg.telegram.token}/sendMessage"
        payload = {
            "chat_id": cfg.telegram.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")


# ========================= CSV LOGGER =========================
def init_trade_log():
    if not os.path.exists(cfg.log_file):
        os.makedirs(os.path.dirname(cfg.log_file), exist_ok=True)
        with open(cfg.log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "timestamp",
                    "action",
                    "symbol",
                    "quantity",
                    "price",
                    "reason",
                    "order_id",
                ]
            )


def log_trade(
    action: str, qty: int, price: float | None, reason: str, order_id: str = ""
):
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(cfg.log_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                timestamp,
                action,
                cfg.symbol,
                qty,
                f"{price:.4f}" if price else "",
                reason,
                order_id,
            ]
        )

    logger.info(f"TRADE LOGGED | {action} {qty} {cfg.symbol} | {reason}")
    send_telegram(
        f"*{action}* {qty} *{cfg.symbol}*\n{reason}\nPrice: ${price:.2f}"
        if price
        else f"*{action}* {qty} *{cfg.symbol}*\n{reason}"
    )


# ========================= ACCOUNT SETUP =========================
response = client.linked_accounts()
data = response.json()
hashValue = next(
    (item["hashValue"] for item in data if item["accountNumber"] == cfg.account_number),
    None,
)

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
            logger.info(
                f"Daily loss tracking reset. Start Equity: ${daily_start_equity:,.2f}"
            )

        account.refresh()
        current_equity = float(account.equity)
        loss_pct = (daily_start_equity - current_equity) / daily_start_equity * 100
        return loss_pct
    except:
        return 0.0


def is_trading_halted() -> bool:
    loss = get_daily_loss_pct()
    if loss >= cfg.daily_max_loss_pct:
        logger.warning(f"🚨 DAILY LOSS LIMIT REACHED: {loss:.1f}%")
        send_telegram(
            f"⚠️ *Daily Loss Limit Reached* ({loss:.1f}%) - Trading Halted Today"
        )
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
    """Place trailing stop sell order"""
    try:
        order_dict = sell_trailing_stop_dict(
            symbol=cfg.symbol,
            quantity=qty,
            stop_price_offset=cfg.trailing_stop_pct,
            session="NORMAL",
            duration="DAY",
        )
        status_code, _, order_id = place_order(
            client=client, accountHash=hashValue, order=order_dict
        )
        if status_code == 201:
            log_trade(
                "TRAILING_SELL",
                qty,
                current_price,
                f"+{cfg.up_pct}% surge detected",
                order_id,
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Trailing sell failed: {e}")
        return False


def place_trailing_buy(qty: int, current_price: float):
    """Place true Trailing Buy order (preferred) with fallback"""
    try:
        # Try true trailing buy first
        from schwab_trader.orders.equity import buy_trailing_stop_dict

        order_dict = buy_trailing_stop_dict(
            symbol=cfg.symbol,
            quantity=qty,
            stop_price_offset=cfg.trailing_stop_pct,  # Triggers buy when price rises by this %
            session="NORMAL",
            duration="DAY",
        )

        status_code, _, order_id = place_order(
            client=client, accountHash=hashValue, order=order_dict
        )
        if status_code == 201:
            log_trade(
                "TRAILING_BUY",
                qty,
                current_price,
                f"-{cfg.down_pct}% dip → Trailing Buy ({cfg.trailing_stop_pct}% trigger)",
                order_id,
            )
            return True

    except ImportError:
        logger.warning(
            "buy_trailing_stop_dict not available. Using limit buy fallback."
        )
    except Exception as e:
        logger.warning(f"Trailing buy failed: {e}. Using fallback.")

    # Fallback: Limit Buy
    return place_limit_buy_fallback(qty, current_price)


def place_limit_buy_fallback(qty: int, current_price: float):
    """Fallback limit buy slightly below current price"""
    try:
        from schwab_trader.orders.equity import buy_limit_dict

        limit_price = round(current_price * 0.992, 2)  # 0.8% below

        order_dict = buy_limit_dict(
            symbol=cfg.symbol,
            quantity=qty,
            limit_price=limit_price,
            session="NORMAL",
            duration="DAY",
        )
        status_code, _, order_id = place_order(
            client=client, accountHash=hashValue, order=order_dict
        )
        if status_code == 201:
            log_trade(
                "LIMIT_BUY",
                qty,
                current_price,
                f"Fallback limit buy @ ${limit_price}",
                order_id,
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Limit buy fallback failed: {e}")
        return False


# ========================= STREAMING CALLBACK =========================
async def on_quote(data):
    try:
        # Adjust this based on actual streaming data structure from your library
        price = None
        if isinstance(data, dict):
            price = (
                data.get("lastPrice") or data.get("bidPrice") or data.get("askPrice")
            )
        elif isinstance(data, (int, float)):
            price = float(data)

        if not price:
            return

        now = dt.datetime.now()
        price_window.append((now, price))

        if is_trading_halted():
            return

        position_qty = get_position_qty()
        logger.info(
            f"📡 {cfg.symbol} @ ${price:.2f} | Position: {position_qty}/{cfg.max_position_shares}"
        )

        # === UP MOVE → Trailing Sell ===
        if len(price_window) >= 10:
            window_start = now - dt.timedelta(minutes=cfg.up_window_min)
            recent = [p for t, p in price_window if t >= window_start]
            if recent:
                min_p = min(recent)
                pct_up = (price - min_p) / min_p * 100
                if pct_up >= cfg.up_pct and position_qty > 0:
                    logger.warning(f"🔥 +{pct_up:.1f}% surge detected!")
                    place_trailing_sell(position_qty, price)

        # === DOWN MOVE → Trailing Buy ===
        if len(price_window) >= 10:
            window_start = now - dt.timedelta(minutes=cfg.down_window_min)
            recent = [p for t, p in price_window if t >= window_start]
            if recent:
                max_p = max(recent)
                pct_down = (max_p - price) / max_p * 100
                if (
                    pct_down >= cfg.down_pct
                    and position_qty == 0
                    and position_qty + cfg.buy_quantity <= cfg.max_position_shares
                ):

                    logger.warning(
                        f"📉 -{pct_down:.1f}% dip detected! Placing trailing buy."
                    )
                    place_trailing_buy(cfg.buy_quantity, price)

    except Exception as e:
        logger.debug(f"Quote processing error: {e}")


# ========================= MAIN =========================
async def main():
    logger.info(f"🚀 NBIS Streaming Momentum Bot Started | {cfg.symbol}")
    logger.info(
        f"Risk: Daily Loss ≤{cfg.daily_max_loss_pct}% | Max Position {cfg.max_position_shares} shares"
    )

    send_telegram(
        f"🚀 *NBIS Momentum Bot Started*\n"
        f"Daily Loss Limit: {cfg.daily_max_loss_pct}% | Max Position: {cfg.max_position_shares} shares"
    )

    try:
        # === Streaming Setup ===
        # Adjust the import and method based on your schwab_trader version
        logger.info("Connecting to streaming quotes...")

        # Example (uncomment and adjust when you know the exact API):
        # from schwab_trader.streaming import StreamerClient
        # streamer = StreamerClient(client)
        # await streamer.connect()
        # await streamer.subscribe_level_one_equities([cfg.symbol], callback=on_quote)

        while True:
            await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        send_telegram("⛔ *NBIS Bot Stopped*")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        send_telegram(f"❌ *Bot Crashed*: {str(e)[:150]}")


if __name__ == "__main__":
    init_trade_log()
    asyncio.run(main())
