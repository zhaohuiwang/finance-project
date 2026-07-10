"""
schwab-trader/scripts/atr_mean_reversion_bot.py

This bot is an ATR-based mean-reversion (Average True Range) system that buys after unusually large declines and sells after unusually large advances, using trailing stop orders to confirm reversals before entering or exiting.

OHLC (Open, High, Low, and Close) candle

Large drop - Wait for rebound - Buy
Large rise - Wait for pullback - Sell


Buy logic:
position_qty == 0
not has_pending_buy
position_qty + buy_quantity <= max_position_shares

atr = calculate_atr(bars, cfg.atr_period)
down_threshold = (cfg.down_atr_multiplier * atr)

# look back over last N minutes and find the highest price, where N is
cfg.down_window_min = 20
move_down = (max(recent_highs) - last_price)
if move_down >= down_threshold:
    place_trailing_buy(cfg.buy_quantity, ask or last_price)
# where ask = quote_cache[cfg.symbol]["ask"] and default buy_quantity = 50
# Trailing Sell Offset
offset = round(cfg.trailing_atr_multiplier_sell * atr, 2)

Sell logic:
position_qty > 0
not has_pending_sell

atr = calculate_atr(bars, cfg.atr_period)
up_threshold = (cfg.up_atr_multiplier * atr)
# look back over last N minutes and find the highest price, where N is
cfg.up_window_min = 15
move_up = (last_price - min(recent_lows))
if move_up >= up_threshold:
    place_trailing_sell(position_qty, bid or last_price)
# where bid = quote_cache[cfg.symbol]["bid"]


# Check and kill runing process:
$ pgrep -af atr_mean_reversion_bot
$ kill -9 261743

"""

import asyncio
import datetime as dt
import json
import logging
import csv
import os
from collections import deque
from pathlib import Path
import time
from typing import Any
from zoneinfo import ZoneInfo

import requests
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

import schwabdev

from schwab_trader.accounts.schwab import client, SchwabAccount
from schwab_trader.orders.equity import (
    buy_trailing_stop_dict,
    sell_trailing_stop_dict,
    buy_limit_dict,
)
from schwab_trader.orders.utils import place_order

_NY_TZ = ZoneInfo("America/New_York")
LOG_INTERVAL_SEC = 300.0  # time gate
PRICE_MOVE_THRESHOLD = 0.02  # $0.02 move gate

last_log_time = {}
last_log_price = {}


# ========================= CONFIG =========================
class TelegramConfig(BaseModel):
    enabled: bool = False
    token: str | None = None
    chat_id: str | None = None


class TradingConfig(BaseModel):
    symbol: str = "APLD"
    account_number: str

    stop_price_link_type: str = "PERCENT"
    up_window_min: int = Field(15, gt=0)
    down_window_min: int = Field(20, gt=0)
    buy_quantity: int = Field(50, gt=0)

    # ATR Settings
    atr_period: int = Field(14, gt=5)
    up_atr_multiplier: float = Field(1.8, gt=0.5)
    down_atr_multiplier: float = Field(2.0, gt=0.5)
    trailing_atr_multiplier_sell: float = Field(2.5, gt=0.5)
    trailing_atr_multiplier_buy: float = Field(2.0, gt=0.5)
    buy_fallback_offset_pct: float = Field(0.8, gt=0, le=5.0)

    daily_max_loss_pct: float = Field(3.0, gt=0, le=20)
    max_position_shares: int = Field(200, gt=0)

    trade_only_regular_hours: bool = True
    trade_pre_market: bool = False
    trade_after_hours: bool = False

    market_open_time: str = "09:30"
    market_close_time: str = "16:00"

    log_file: str = "logs/momentum_bot_trades.csv"

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


def load_config(path="conf/config.yaml") -> TradingConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return TradingConfig(**data)


cfg = load_config(path="conf/atr_mean_reversion_config.yaml")


# ========================= SETUP =========================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ========================= HELPERS =========================
def is_market_open() -> bool:
    now = dt.datetime.now(_NY_TZ)
    current_time = now.time()
    open_time = dt.datetime.strptime(cfg.market_open_time, "%H:%M").time()
    close_time = dt.datetime.strptime(cfg.market_close_time, "%H:%M").time()
    in_regular = open_time <= current_time < close_time

    if cfg.trade_only_regular_hours:
        return in_regular
    if cfg.trade_pre_market and current_time < open_time:
        return True
    if cfg.trade_after_hours and current_time >= close_time:
        return True
    return in_regular


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


def init_trade_log():
    if not os.path.exists(cfg.log_file):
        os.makedirs(os.path.dirname(cfg.log_file), exist_ok=True)
        with open(cfg.log_file, "w", newline="") as f:
            csv.writer(f).writerow(
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
        csv.writer(f).writerow(
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
    msg = f"*{action}* {qty} *{cfg.symbol}*\n{reason}"
    if price:
        msg += f"\nPrice: ${price:.2f}"
    send_telegram(msg)


def should_log(symbol: str, price: float) -> bool:
    now = time.time()

    last_t = last_log_time.get(symbol, 0)
    last_p = last_log_price.get(symbol)

    time_ok = (now - last_t) >= LOG_INTERVAL_SEC
    price_ok = (last_p is None) or (
        abs((price - last_p) / last_p) >= PRICE_MOVE_THRESHOLD
    )

    return time_ok or price_ok


# ========================= ACCOUNT & GLOBALS =========================
response = client.linked_accounts()
data = response.json()
hashValue = next(
    (item["hashValue"] for item in data if item["accountNumber"] == cfg.account_number),
    None,
)
if not hashValue:
    raise ValueError(f"Account hash not found for {cfg.account_number}!")

account = SchwabAccount(client, hashValue)

#
bars = deque(maxlen=500)

active_orders: dict[str, dict] = {}

# To reduce API calls we cache position and specify a refresh interval.
cached_position_qty = 0
last_position_refresh = 0.0

POSITION_REFRESH_SEC = 30

cached_daily_loss_pct = 0.0
last_daily_loss_refresh = 0.0

DAILY_LOSS_REFRESH_SEC = 300
ORDER_STALE_SEC = 1800  # 30 minutes

quote_cache = {
    cfg.symbol: {
        "bid": None,
        "ask": None,
        "last": None,
        "mark": None,
    }
}

last_signal_bar = {
    "BUY": None,
    "SELL": None,
}


def get_daily_loss_pct() -> float:
    global daily_start_equity
    global daily_start_date
    global cached_daily_loss_pct
    global last_daily_loss_refresh
    now = time.time()
    if now - last_daily_loss_refresh < DAILY_LOSS_REFRESH_SEC:
        return cached_daily_loss_pct
    try:
        today = dt.date.today()
        if daily_start_date != today or daily_start_equity is None:
            account.refresh()
            daily_start_equity = float(account.equity)
            daily_start_date = today
        else:
            account.refresh()
        cached_daily_loss_pct = (
            (daily_start_equity - float(account.equity)) / daily_start_equity * 100
        )
        last_daily_loss_refresh = now
        return cached_daily_loss_pct
    except Exception:
        return cached_daily_loss_pct


def is_trading_halted() -> bool:
    if get_daily_loss_pct() >= cfg.daily_max_loss_pct:
        logger.warning("🚨 DAILY LOSS LIMIT REACHED")
        send_telegram("⚠️ *Daily Loss Limit Reached*")
        return True
    return False


def get_position_qty(force_refresh: bool = False) -> int:

    global cached_position_qty
    global last_position_refresh
    now = time.time()
    if not force_refresh and (now - last_position_refresh) < POSITION_REFRESH_SEC:
        return cached_position_qty
    try:
        account.refresh()
        pos = account.get_position(cfg.symbol)
        cached_position_qty = int(pos.quantity) if pos else 0
        last_position_refresh = now
        return cached_position_qty
    except Exception:
        return cached_position_qty


# ========================= ATR =========================
def calculate_atr(bars, period=14):

    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1][4]
        high_ = bars[i][2]
        low_ = bars[i][3]
        tr = max(
            high_ - low_,
            abs(high_ - prev_close),
            abs(low_ - prev_close),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


# ========================= ORDER FUNCTIONS =========================
def place_trailing_sell(qty: int, current_price: float) -> bool:
    try:
        atr = calculate_atr(list(bars)[:-1], cfg.atr_period) or 0.5
        offset = round(cfg.trailing_atr_multiplier_sell * atr, 2)

        order_dict = sell_trailing_stop_dict(
            symbol=cfg.symbol,
            quantity=qty,
            stop_price_link_basis="MARK",
            stop_price_link_type=cfg.stop_price_link_type,
            stop_price_offset=offset,
            session="NORMAL",
            duration="DAY",
        )

        status_code, _, order_id = place_order(
            client=client, accountHash=hashValue, order=order_dict
        )

        if status_code == 201 and order_id:
            active_orders[order_id] = {
                "type": "SELL",
                "qty": qty,
                "entry_price": current_price,
                "timestamp": dt.datetime.now(),
            }
            log_trade(
                "TRAILING_SELL",
                qty,
                current_price,
                f"ATR trailing sell (offset {offset})",
                order_id,
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Trailing sell failed: {e}")
        return False


def place_trailing_buy(qty: int, current_price: float) -> bool:
    """Place trailing stop buy + configurable fallback limit buy."""
    try:
        atr = calculate_atr(list(bars)[:-1], cfg.atr_period) or 0.5
        offset = round(cfg.trailing_atr_multiplier_buy * atr, 2)
        order_dict = buy_trailing_stop_dict(
            symbol=cfg.symbol,
            quantity=qty,
            stop_price_link_basis="MARK",
            stop_price_link_type="PERCENT",
            stop_price_offset=offset,
            session="NORMAL",
            duration="DAY",
        )

        status_code, _, order_id = place_order(
            client=client, accountHash=hashValue, order=order_dict
        )

        if status_code == 201 and order_id:
            active_orders[order_id] = {
                "type": "BUY",
                "qty": qty,
                "entry_price": current_price,
                "timestamp": dt.datetime.now(),
            }
            log_trade(
                "TRAILING_BUY",
                qty,
                current_price,
                f"ATR trailing buy (offset {offset})",
                order_id,
            )
            return True

    except Exception as e:
        logger.warning(f"Trailing buy failed: {e}")

    # ==================== FALLBACK LIMIT BUY ====================
    try:
        offset_pct = cfg.buy_fallback_offset_pct / 100.0
        limit_price = round(current_price * (1 - offset_pct), 2)

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

        if status_code == 201 and order_id:
            active_orders[order_id] = {
                "type": "BUY",
                "qty": qty,
                "entry_price": current_price,
                "timestamp": dt.datetime.now(),
            }
            log_trade(
                "LIMIT_BUY_FALLBACK",
                qty,
                current_price,
                f"Fallback limit buy @ ${limit_price} (-{cfg.buy_fallback_offset_pct}%)",
                order_id,
            )
            logger.info(f"✅ Fallback limit buy placed @ ${limit_price}")
            return True
        else:
            logger.warning(f"Fallback limit buy rejected. Status: {status_code}")

    except Exception as e:
        logger.error(f"Fallback limit buy failed: {e}")

    return False


# ========================= STREAM HANDLER =========================
# https://tylerebowers.github.io/Schwabdev/?source=pages%2Fstream.html # Level one equities > Data Example
# streamer.level_one_equities(
#     cfg.symbol,
#     "0,1,2,3,10,11,33"
# ) # Purpose: latest price, bid/ask, trade execution

# streamer.chart_equity(
#     cfg.symbol,
#     "0,1,2,3,4,5,6,7,8"
# ) # Purpose: ATR, momentum, volatility


def on_quote(message: Any):
    global last_log_time

    try:
        # schwabdev often delivers JSON strings
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except Exception:
                return
        if not isinstance(message, dict):
            return
        if "data" not in message:
            return

        for packet in message["data"]:
            # CHART_EQUITY only
            service = packet.get("service")
            if service == "LEVELONE_EQUITIES":
                for content in packet.get("content", []):
                    if content.get("key") != cfg.symbol:
                        continue
                    handle_level1(content)
                continue

            if service != "CHART_EQUITY":
                continue

            for content in packet.get("content", []):

                if content.get("key") != cfg.symbol:
                    continue

                try:
                    open_price = float(content["2"])
                    high_price = float(content["3"])
                    low_price = float(content["4"])
                    close_price = float(content["5"])

                    ts_ms = int(content["7"])

                except (KeyError, TypeError, ValueError):
                    continue

                # candle timestamp from Schwab
                candle_time = dt.datetime.fromtimestamp(ts_ms / 1000.0, tz=_NY_TZ)

                # avoid duplicate candles
                if len(bars) > 0 and bars[-1][0] == candle_time:
                    bars[-1] = (
                        candle_time,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                    )
                else:
                    bars.append(
                        (
                            candle_time,
                            open_price,
                            high_price,
                            low_price,
                            close_price,
                        )
                    )

                # current market price
                last_price = close_price
                # market checks
                if not is_market_open():
                    continue
                if is_trading_halted():
                    continue
                # need enough candles
                atr = calculate_atr(list(bars)[:-1], cfg.atr_period)
                if atr is None or atr <= 0:
                    continue
                # position
                position_qty = get_position_qty()
                # thresholds
                up_threshold = cfg.up_atr_multiplier * atr
                down_threshold = cfg.down_atr_multiplier * atr

                has_pending_buy = any(
                    info["type"] == "BUY" for info in active_orders.values()
                )
                has_pending_sell = any(
                    info["type"] == "SELL" for info in active_orders.values()
                )
                # SELL SIGNAL
                if position_qty > 0 and not has_pending_sell:
                    if last_signal_bar["SELL"] == candle_time:
                        continue

                    window_start = candle_time - dt.timedelta(minutes=cfg.up_window_min)
                    recent_lows = [
                        low_ for ts, _, _, low_, _ in bars if ts >= window_start
                    ]
                    if recent_lows:
                        move_up = last_price - min(recent_lows)

                        if move_up >= up_threshold:
                            logger.warning(
                                f"🔥 SURGE {move_up:.2f} "
                                f"{up_threshold:.2f} "
                                f"(ATR={atr:.2f})"
                            )
                            place_trailing_sell(
                                position_qty,
                                quote_cache[cfg.symbol]["bid"] or last_price,
                            )
                            last_signal_bar["SELL"] = candle_time
                # BUY SIGNAL
                if position_qty == 0 and not has_pending_buy:
                    if last_signal_bar["BUY"] == candle_time:
                        continue
                    window_start = candle_time - dt.timedelta(
                        minutes=cfg.down_window_min
                    )
                    recent_highs = [
                        high_ for ts, _, high_, _, _ in bars if ts >= window_start
                    ]
                    if recent_highs:
                        move_down = max(recent_highs) - last_price
                        if move_down >= down_threshold:
                            projected_position = position_qty + cfg.buy_quantity
                            if projected_position > cfg.max_position_shares:

                                logger.warning(
                                    f"📉 BUY signal ignored: "
                                    f"position limit reached "
                                    f"({position_qty}/"
                                    f"{cfg.max_position_shares})"
                                )
                                continue
                            logger.warning(
                                f"📉 DIP {move_down:.2f} "
                                f"move_down={move_down:.2f} "
                                f"threshold={down_threshold:.2f} "
                                f"(ATR={atr:.2f})"
                            )
                            place_trailing_buy(
                                cfg.buy_quantity,
                                quote_cache[cfg.symbol]["ask"] or last_price,
                            )
                            last_signal_bar["BUY"] = candle_time
    except Exception as e:
        logger.exception(f"on_quote failed: {e}")


def handle_level1(content):
    cache = quote_cache[cfg.symbol]
    # Bid Price
    if "1" in content:
        cache["bid"] = float(content["1"])
    # Ask Price
    if "2" in content:
        cache["ask"] = float(content["2"])
    # Last Price
    if "3" in content:
        cache["last"] = float(content["3"])
    # Mark Price
    if "33" in content:
        cache["mark"] = float(content["33"])
    if should_log(cfg.symbol, cache["last"] or 0):
        logger.info(
            f"{cfg.symbol} "
            f"BID={cache['bid']} "
            f"ASK={cache['ask']} "
            f"LAST={cache['last']} "
            f"MARK={cache['mark']}"
        )
        last_log_time[cfg.symbol] = time.time()
        last_log_price[cfg.symbol] = cache["last"]


# ========================= ORDER MONITOR =========================


async def monitor_orders():
    while True:
        try:
            await asyncio.sleep(15)
            # Remove stale local orders
            if active_orders:
                now = dt.datetime.now()
                stale_order_ids = []

                for order_id, info in active_orders.items():
                    age_sec = (now - info["timestamp"]).total_seconds()
                    if age_sec > ORDER_STALE_SEC:
                        stale_order_ids.append(order_id)

                for order_id in stale_order_ids:
                    logger.warning(f"Removing stale order {order_id}")
                    active_orders.pop(order_id, None)

            if not active_orders:
                continue

            orders_response = client.get_orders_for_account(hashValue, max_results=100)
            orders = (
                orders_response
                if isinstance(orders_response, list)
                else orders_response.get("orders", [])
            )
            for order in orders:
                order_id = str(order.get("orderId") or order.get("id"))
                if order_id not in active_orders:
                    continue
                status = str(order.get("status", "")).upper()
                # Fully filled
                if status in ["FILLED", "EXECUTED"]:
                    info = active_orders.pop(order_id, None)

                    if info:
                        get_position_qty(force_refresh=True)
                        log_trade(
                            "FILL", info["qty"], None, f"Order {status}", order_id
                        )
                        logger.info(f"✅ Order FILLED: {order_id}")
                # Partial fill
                elif status == "PARTIALLY_FILLED":
                    get_position_qty(force_refresh=True)
                    logger.info(f"⏳ Order PARTIALLY_FILLED: " f"{order_id}")
                # Dead orders
                elif status in ["CANCELLED", "REJECTED", "EXPIRED", "DEAD"]:
                    active_orders.pop(order_id, None)
                    logger.warning(f"❌ Order {status}: {order_id}")
        except Exception as e:
            logger.debug(f"Order monitor error: {e}")


# ========================= MAIN WITH AUTO-RECONNECT =========================
async def run_bot():
    while True:
        try:
            logger.info("Starting streamer with auto-reconnect...")

            # One Schwab streaming connection can subscribe to multiple services, so we use a single streamer for both level one and chart data.
            streamer = schwabdev.Stream(client)

            streamer.start_auto(
                receiver=on_quote,  # print,
                start_time=dt.time(9, 29, 0),
                stop_time=dt.time(16, 0, 0),
                on_days=(0, 1, 2, 3, 4),
                now_timezone=_NY_TZ,
                daemon=True,
            )  # or streamer.start(on_quote)

            logger.info("Streamer started")

            time.sleep(1.5)

            # Subscribe that single connection to two services for the same symbol. This way we get both real-time quotes and chart data (for ATR/momentum) without needing multiple connections.
            streamer.send(streamer.level_one_equities(cfg.symbol, "0,1,2,3,10,11,33"))
            streamer.send(streamer.chart_equity(cfg.symbol, "0,1,2,3,4,5,6,7,8"))
            logger.info(f"Subscribed to {cfg.symbol}")
            while True:
                await asyncio.sleep(30)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"Streamer crashed: {e}. Restarting in 10s...")
            send_telegram(f"⚠️ Streamer disconnected. Reconnecting...")
            await asyncio.sleep(10)


async def main():
    logger.info(f"🚀 Momentum Bot Started | {cfg.symbol}")
    send_telegram(f"🚀 *Bot Started* | {cfg.symbol}")
    init_trade_log()

    asyncio.create_task(monitor_orders())

    try:
        await run_bot()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        send_telegram(f"❌ *Fatal Error*: {str(e)[:150]}")
    finally:
        send_telegram("⛔ *Bot Stopped*")


if __name__ == "__main__":
    asyncio.run(main())
