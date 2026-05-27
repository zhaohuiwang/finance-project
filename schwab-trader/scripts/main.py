# scripts/main.py

# import asyncio
# from src.schwab_bot.pipelines.monitor import SchwabBot

# if __name__ == "__main__":
#     bot = SchwabBot(config_path="conf/config.yaml")
#     asyncio.run(bot.run())

print("Bot initialized.")

import asyncio
import json
import os
import signal
import logging
from datetime import datetime, time as dt_time, timezone, timedelta
from dotenv import load_dotenv

import schwabdev

# ==========================================================
# CONFIG
# ==========================================================

load_dotenv()

ACCOUNT_NUMBER = "29308909"
SYMBOLS = ["AAPL", "MSFT"]

BAR_INTERVAL = 60  # seconds for 1-min bars
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5
REWARD_MULTIPLIER = 2.5

RISK_PER_TRADE = 0.002  # 2% of equity
STARTING_EQUITY = 25000
MAX_DAILY_LOSS = 10

MAX_ORDERS_PER_SECOND = 1
RECONCILE_INTERVAL = 30  # seconds for position polling


# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==========================================================
# CLIENT
# ==========================================================

client = schwabdev.Client(
    os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
)

# =====================================================
# STREAM
# =====================================================

# stream = schwabdev.Stream(client)
stream = schwabdev.StreamAsync(client)

# ==========================================================
# GLOBAL STATE
# ==========================================================

account_hash = None
event_queue = asyncio.Queue()
shutdown_event = asyncio.Event()

equity = STARTING_EQUITY
start_equity = STARTING_EQUITY
daily_pnl = 0
kill_switch = False

positions = {s: {"shares": 0, "entry_price": None, "unrealized_pnl": 0} for s in SYMBOLS}
ohlc = {s: [] for s in SYMBOLS}
current_bars = {s: None for s in SYMBOLS}

order_semaphore = asyncio.Semaphore(MAX_ORDERS_PER_SECOND)
last_volumes = {s: 0 for s in SYMBOLS}


# ==========================================================
# STREAM HANDLERS
# ==========================================================


def quote_handler(message):
    data = json.loads(message)
    if "data" not in data:
        return
    for item in data["data"]:
        if "content" not in item:
            continue
        for quote in item["content"]:
            symbol = quote.get("key")
            price = quote.get("8")  # lastPrice field is 8 in level one
            timestamp_ms = quote.get("3")  # tradeTimeInLong
            volume = (
                quote.get("7") or 0
            )  # totalVolume, but for tick it's cumulative—handle delta if needed
            if symbol in SYMBOLS and price and timestamp_ms:
                asyncio.get_event_loop().call_soon_threadsafe(
                    event_queue.put_nowait,
                    {
                        "type": "quote",
                        "symbol": symbol,
                        "price": price,
                        "timestamp": timestamp_ms / 1000,
                        "volume": volume,
                    },
                )


def activity_handler(message):
    data = json.loads(message)
    if "data" not in data:
        return
    for item in data["data"]:
        if "content" not in item:
            continue
        for activity in item["content"]:
            msg_type = activity.get("MessageType")
            if msg_type in ["ORDER_FILL", "ORDER_PARTIAL_FILL"]:
                order_id = activity.get("OrderID")
                symbol = activity.get("Symbol")
                filled_shares = float(activity.get("ExecutedShares"))
                fill_price = float(activity.get("ExecutionPrice"))
                side = activity.get("Side")  # 'B' for buy, 'S' for sell
                if symbol in SYMBOLS:
                    asyncio.get_event_loop().call_soon_threadsafe(
                        event_queue.put_nowait,
                        {
                            "type": "fill",
                            "symbol": symbol,
                            "shares": filled_shares,
                            "price": fill_price,
                            "side": side,
                        },
                    )


# ==========================================================
# BAR AGGREGATION
# ==========================================================


def update_ohlc(symbol, price, timestamp, volume_delta):
    bar_start = (int(timestamp) // BAR_INTERVAL) * BAR_INTERVAL
    current = current_bars[symbol]
    new_bar = False
    if current is None or current["time"] != bar_start:
        if current:
            ohlc[symbol].append(current)
            if len(ohlc[symbol]) > ATR_PERIOD + 1:
                ohlc[symbol].pop(0)
            new_bar = True
        current_bars[symbol] = {
            "time": bar_start,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume_delta,
        }
    else:
        current["high"] = max(current["high"], price)
        current["low"] = min(current["low"], price)
        current["close"] = price
        current["volume"] += volume_delta
    return new_bar


# ==========================================================
# ATR CALCULATION
# ==========================================================


def calculate_atr(symbol):
    data = ohlc[symbol]
    if len(data) < ATR_PERIOD:
        return None
    trs = []
    for i in range(1, len(data)):
        high = data[i]["high"]
        low = data[i]["low"]
        prev_close = data[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-ATR_PERIOD:]) / ATR_PERIOD


# ==========================================================
# POSITION SIZING
# ==========================================================


def calculate_position_size(entry_price: float, stop_price: float) -> int:
    global equity
    if equity <= 0:
        return 0

    risk_dollars = equity * RISK_PER_TRADE
    per_share_risk = abs(entry_price - stop_price)

    if per_share_risk < 0.01:   # Avoid division by zero / tiny risk
        return 0

    shares = int(risk_dollars / per_share_risk)
    return max(shares, 0)


# ==========================================================
# BUILD ATR BRACKET - Average True Range, volatility indicators
# TR = max( High − Low,   |High − Previous Close|,   |Low − Previous Close| )
# Current ATR = [(Previous ATR × (n−1)) + Current TR] / n where n is the number of periods (e.g., 14)

# Most Common Uses of ATR in Trading
# Use Case                How ATR is used                     Typical Multiplier
# Stop-loss placement     Stop = entry ± (ATR x 1.5 - 3)          1.5x - 3x
# Trailing stops          Trail by 2-4 x ATR below high (long)    2x - 4x
# Chandelier Exit         Very popular ATR-based trailing stop    3x usually
# Profit targets          Target = entry + (ATR x 2 - 4)          2x - 4x
# Position sizing         Risk $X per trade → shares = $X / (ATR x multiplier) —
# Volatility filter       Only take trades when ATR > certain threshold        —
# Breakout systems        Add/subtract ATR x 0.5-1 from consolidation range     0.5x - 1x
# ==========================================================


def build_bracket(symbol: str, entry_price: float):
    atr = calculate_atr(symbol)
    if not atr:
        logger.warning(f"No ATR available for {symbol}")
        return None

    stop_price = round(entry_price - (atr * ATR_MULTIPLIER), 2)
    take_profit = round(entry_price + (atr * REWARD_MULTIPLIER), 2)
    shares = calculate_position_size(entry_price, stop_price)

    if shares <= 0:
        logger.info(f"Position size too small for {symbol}")
        return None

    # Cleaner bracket structure (Schwab is picky)
    bracket_order = {
        "orderStrategyType": "SINGLE",
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": "DAY",
        "price": round(entry_price, 2),
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": shares,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
            }
        ],
        "childOrderStrategies": [
            {
                "orderStrategyType": "OCO",
                "childOrderStrategies": [
                    # Take Profit
                    {
                        "orderType": "LIMIT",
                        "session": "NORMAL",
                        "duration": "DAY",
                        "price": take_profit,
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity": shares,
                                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                            }
                        ]
                    },
                    # Stop Loss
                    {
                        "orderType": "STOP",
                        "session": "NORMAL",
                        "duration": "DAY",
                        "stopPrice": stop_price,
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity": shares,
                                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                            }
                        ]
                    }
                ]
            }
        ]
    }

    logger.info(f"Built bracket for {symbol}: {shares} shares @ {entry_price} | SL {stop_price} | TP {take_profit}")
    return bracket_order


# ==========================================================
# ENTRY FILTER (Simple Momentum: Close > Prev Close and Volume > Avg)
# ==========================================================


def entry_condition(symbol):
    data = ohlc[symbol]
    if len(data) < 2:
        return False
    current = data[-1]
    prev = data[-2]
    if current["close"] <= prev["close"]:
        return False
    avg_volume = (
        sum(b["volume"] for b in data[-ATR_PERIOD:]) / ATR_PERIOD
        if len(data) >= ATR_PERIOD
        else 0
    )
    if current["volume"] <= avg_volume:
        return False
    return True


# ==========================================================
# RISK ENGINE
# ==========================================================


def risk_check() -> bool:
    global kill_switch, daily_pnl
    if kill_switch:
        return False

    if daily_pnl <= -MAX_DAILY_LOSS:
        logger.critical("🚨 MAX DAILY LOSS HIT — ACTIVATING KILL SWITCH")
        kill_switch = True
        return False

    # Optional: Add max position exposure check
    total_exposure = sum(p["shares"] * (ohlc[s][-1]["close"] if ohlc[s] else 100) 
                        for s, p in positions.items())
    if total_exposure > equity * 0.5:   # e.g. max 50% exposure
        logger.warning("High exposure - skipping new trades")
        return False

    return True


# ==========================================================
# ORDER EXECUTION
# ==========================================================


async def place_bracket(symbol, price):
    async with order_semaphore:
        order = build_bracket(symbol, price)
        if not order:
            return
        response = await asyncio.to_thread(client.order_place, ACCOUNT_NUMBER, order)
        print(f"[ORDER] {symbol} -> {response.status_code}")


# ==========================================================
# HANDLE FILLS
# ==========================================================


def handle_fill(symbol: str, shares: float, price: float, side: str):
    global equity, daily_pnl
    pos = positions[symbol]

    if side == "B":  # Buy
        if pos["shares"] == 0:
            pos["entry_price"] = price
        pos["shares"] += shares
        equity -= shares * price
        logger.info(f"🟢 BOUGHT {shares} {symbol} @ {price}")

    elif side == "S":  # Sell
        pos["shares"] -= shares
        if pos["entry_price"]:
            realized_pnl = (price - pos["entry_price"]) * shares
            daily_pnl += realized_pnl
            equity += shares * price
            logger.info(f"🔴 SOLD {shares} {symbol} @ {price} | PnL: ${realized_pnl:,.2f}")

    # Cleanup
    if pos["shares"] <= 0:
        pos["shares"] = 0
        pos["entry_price"] = None

    # Update unrealized
    if pos["shares"] > 0 and ohlc[symbol]:
        pos["unrealized_pnl"] = (ohlc[symbol][-1]["close"] - pos["entry_price"]) * pos["shares"]


# ==========================================================
# BOT LOOP
# ==========================================================


async def bot_loop():
    last_volumes = {s: 0 for s in SYMBOLS}  # To calculate volume delta
    while not shutdown_event.is_set():
        event = await event_queue.get()
        symbol = event["symbol"]
        if event["type"] == "quote":
            volume_delta = (
                event["volume"] - last_volumes[symbol]
                if event["volume"] > last_volumes[symbol]
                else 0
            )
            last_volumes[symbol] = event["volume"]
            new_bar = update_ohlc(
                symbol, event["price"], event["timestamp"], volume_delta
            )
            if (
                new_bar
                and risk_check()
                and positions[symbol]["shares"] == 0
                and entry_condition(symbol)
            ):
                if is_market_open():
                    asyncio.create_task(
                        place_bracket(symbol, ohlc[symbol][-1]["close"])
                    )
        elif event["type"] == "fill":
            handle_fill(symbol, event["shares"], event["price"], event["side"])


# ==========================================================
# POSITION RECONCILER (Fallback Polling)
# ==========================================================


async def position_reconciler():
    global equity, daily_pnl, start_equity
    while not shutdown_event.is_set():
        try:
            response = await asyncio.to_thread(client.account_positions, ACCOUNT_NUMBER)
            if response.ok:
                data = response.json()["securitiesAccount"]
                equity = data["currentBalances"]["equity"]
                daily_pnl = (
                    equity - start_equity
                )  # Simplified; use actual daily PnL if available
                for pos in data.get("positions", []):
                    sym = pos["instrument"]["symbol"]
                    if sym in SYMBOLS:
                        positions[sym]["shares"] = (
                            pos["longQuantity"] - pos["shortQuantity"]
                        )
                        positions[sym]["entry_price"] = pos["averagePrice"]
                        positions[sym]["unrealized_pnl"] = pos["currentDayProfitLoss"]
        except Exception as e:
            print("Position recon error:", e)
        await asyncio.sleep(RECONCILE_INTERVAL)


# ==========================================================
# MARKET HOURS CHECK
# ==========================================================


def is_market_open():
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))  # ET
    if now.weekday() >= 5:  # Weekend
        return False
    open_time = dt_time(9, 30)
    close_time = dt_time(16, 0)
    return open_time <= now.time() <= close_time


# ==========================================================
# STREAM TASK
# ==========================================================


async def stream_task():
    while not shutdown_event.is_set():
        try:
            stream.start(
                handler=quote_handler
            )  # Note: schwabdev may need custom handler setup; adjust per docs
            stream.level_one_equities(
                symbols=SYMBOLS, fields=[0, 1, 2, 3, 4, 5, 6, 7, 8]
            )
            stream.account_activity()  # Assumes schwabdev supports this; handler=activity_handler
            while not shutdown_event.is_set():
                await asyncio.sleep(1)
        except Exception as e:
            print("STREAM ERROR:", e)
            await asyncio.sleep(5)


# ==========================================================
# SHUTDOWN
# ==========================================================


def shutdown():
    print("Shutting down...")
    shutdown_event.set()


async def main():
    global start_equity
    start_equity = (await asyncio.to_thread(client.account, ACCOUNT_NUMBER)).json()[
        "securitiesAccount"
    ]["currentBalances"]["equity"]
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)
    await asyncio.gather(stream_task(), bot_loop(), position_reconciler())


if __name__ == "__main__":
    asyncio.run(main())
