# scripts/main.py

# import asyncio
# from src.schwab_bot.pipelines.monitor import SchwabBot

# if __name__ == "__main__":
#     bot = SchwabBot(config_path="conf/config.yaml")
#     asyncio.run(bot.run())
"""
ATR - Average True Range is a popular technical analysis indicator that measures market volatility. It is commonly used by traders to set stop-loss levels, take-profit targets, and position sizing based on current market conditions. \(\text{TR} = \max[(\text{High} - \text{Low}), | \text{High} - \text{Previous Close} |, | \text{Low} - \text{Previous Close} |]\)


"""

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
ATR_PERIOD = 14     # standard ATR period for volatility measurement
ATR_MULTIPLIER = 1.5        # ATR-based stop loss distance (e.g., 1.5x ATR)
REWARD_MULTIPLIER = 2.5       # ATR-based take profit distance (e.g., 2.5x ATR) 

RISK_PER_TRADE = 0.002      # 2% of equity
STARTING_EQUITY = 25000
MAX_DAILY_LOSS = 10

MAX_ORDERS_PER_SECOND = 1       # Schwab API rate limit (adjust as needed)
RECONCILE_INTERVAL = 60  # seconds for position polling



# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ==========================================================
# CLIENT + STREAM
# ==========================================================

client = schwabdev.Client(
    os.getenv("APP_KEY"), 
    os.getenv("APP_SECRET"), 
    os.getenv("CALLBACK_URL")
)

stream = schwabdev.Stream(client)

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

# Volume tracking (used for calculating volume delta in bars)
last_cumulative_volume = {s: 0 for s in SYMBOLS}

# Log throttling timestamps
last_price_log_time = {s: 0 for s in SYMBOLS}
last_equity_log_time = 0

last_equity_print = 0


# ==========================================================
# STREAM HANDLERS
# ==========================================================

def quote_handler(message: str):
    try:
        data = json.loads(message)
        if "data" not in data:
            return
        for item in data.get("data", []):
            for quote in item.get("content", []):
                symbol = quote.get("key")
                if symbol not in SYMBOLS:
                    continue
                price = quote.get("8")
                timestamp_ms = quote.get("3")
                volume = quote.get("7") or 0
                if price and timestamp_ms:
                    asyncio.get_event_loop().call_soon_threadsafe(
                        event_queue.put_nowait,
                        {
                            "type": "quote",
                            "symbol": symbol,
                            "price": float(price),
                            "timestamp": timestamp_ms / 1000,
                            "volume": float(volume),
                        }
                    )
    except Exception as e:
        logger.error(f"Quote handler error: {e}")


def activity_handler(message: str):
    try:
        data = json.loads(message)
        if "data" not in data:
            return
        for item in data.get("data", []):
            for activity in item.get("content", []):
                msg_type = activity.get("MessageType")
                if msg_type not in ["ORDER_FILL", "ORDER_PARTIAL_FILL"]:
                    continue
                symbol = activity.get("Symbol")
                if symbol not in SYMBOLS:
                    continue
                asyncio.get_event_loop().call_soon_threadsafe(
                    event_queue.put_nowait,
                    {
                        "type": "fill",
                        "symbol": symbol,
                        "shares": float(activity.get("ExecutedShares", 0)),
                        "price": float(activity.get("ExecutionPrice", 0)),
                        "side": activity.get("Side"),
                    }
                )
    except Exception as e:
        logger.error(f"Activity handler error: {e}")

# ==========================================================
# BAR AGGREGATION
# ==========================================================

def update_ohlc(symbol: str, price: float, timestamp: float, volume_delta: float):
    bar_start = (int(timestamp) // BAR_INTERVAL) * BAR_INTERVAL
    current = current_bars[symbol]
    new_bar = False

    if current is None or current["time"] != bar_start:
        if current:
            ohlc[symbol].append(current)
            if len(ohlc[symbol]) > ATR_PERIOD + 50:
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

def calculate_atr(symbol: str):
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
# ENTRY CONDITION (Improved)
# ==========================================================

def entry_condition(symbol: str) -> bool:
    data = ohlc[symbol]
    if len(data) < 50:
        return False

    current = data[-1]
    prev = data[-2]

    # Momentum
    if current["close"] <= prev["close"]:
        return False

    # Volume surge
    avg_volume = sum(b["volume"] for b in data[-ATR_PERIOD:]) / ATR_PERIOD
    if current["volume"] <= avg_volume * 1.3:
        return False

    # Trend filter
    sma_50 = sum(b["close"] for b in data[-50:]) / 50
    if current["close"] <= sma_50:
        return False

    return True

# ==========================================================
# POSITION SIZING & RISK
# ==========================================================

def calculate_position_size(entry_price: float, stop_price: float) -> int:
    global equity
    if equity <= 0:
        return 0
    risk_dollars = equity * RISK_PER_TRADE
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk < 0.01:
        return 0
    shares = int(risk_dollars / per_share_risk)
    return max(shares, 0)


def risk_check() -> bool:
    global kill_switch, daily_pnl
    if kill_switch:
        return False
    if daily_pnl <= -MAX_DAILY_LOSS:
        logger.critical("🚨 MAX DAILY LOSS HIT — KILL SWITCH ACTIVATED")
        kill_switch = True
        return False
    return True

# ==========================================================
# BUILD BRACKET ORDER
# ==========================================================

def build_bracket(symbol: str, entry_price: float):
    atr = calculate_atr(symbol)
    if not atr:
        return None

    stop_price = round(entry_price - (atr * ATR_MULTIPLIER), 2)
    take_profit = round(entry_price + (atr * REWARD_MULTIPLIER), 2)
    shares = calculate_position_size(entry_price, stop_price)

    if shares <= 0:
        return None

    return {
        "orderStrategyType": "SINGLE",
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": "DAY",
        "price": round(entry_price, 2),
        "orderLegCollection": [
            {"instruction": "BUY", "quantity": shares, "instrument": {"symbol": symbol, "assetType": "EQUITY"}}
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
                            {"instruction": "SELL", "quantity": shares, "instrument": {"symbol": symbol, "assetType": "EQUITY"}}
                        ]
                    },
                    # Stop Loss
                    {
                        "orderType": "STOP",
                        "session": "NORMAL",
                        "duration": "DAY",
                        "stopPrice": stop_price,
                        "orderLegCollection": [
                            {"instruction": "SELL", "quantity": shares, "instrument": {"symbol": symbol, "assetType": "EQUITY"}}
                        ]
                    }
                ]
            }
        ]
    }

# ==========================================================
# FILL HANDLING
# ==========================================================

def handle_fill(symbol: str, shares: float, price: float, side: str):
    global equity, daily_pnl
    pos = positions[symbol]

    if side == "B":  # Buy
        if pos["shares"] == 0:
            pos["entry_price"] = price
        pos["shares"] += shares
        equity -= shares * price
        logger.info(f"🟢 BOUGHT {shares:.0f} {symbol} @ ${price:.2f} | Pos: {pos['shares']}")

    elif side == "S":  # Sell
        pos["shares"] -= shares
        if pos["entry_price"]:
            realized = (price - pos["entry_price"]) * shares
            daily_pnl += realized
            equity += shares * price
            logger.info(f"🔴 SOLD {shares:.0f} {symbol} @ ${price:.2f} | Realized: ${realized:.2f}")

    if pos["shares"] <= 0:
        pos["shares"] = 0
        pos["entry_price"] = None

    if pos["shares"] > 0 and ohlc[symbol]:
        pos["unrealized_pnl"] = (ohlc[symbol][-1]["close"] - pos["entry_price"]) * pos["shares"]


async def handle_fill_async(symbol: str, shares: float, price: float, side: str):
    try:
        handle_fill(symbol, shares, price, side)
    except Exception as e:
        logger.error(f"Fill handling error for {symbol}: {e}")


# ==========================================================
# PRICE MONITORING (for visibility)
# ==========================================================

def log_price_update(symbol: str, price: float, volume: float):
    """Print live price updates every 10 seconds per symbol"""
    now = datetime.now().timestamp()
    
    if now - last_price_log_time.get(symbol, 0) > 10:   # Every 10 seconds
        last_price_log_time[symbol] = now
        
        bar_info = ""
        if ohlc[symbol] and len(ohlc[symbol]) > 0:
            bar = ohlc[symbol][-1]
            bar_info = f" | Bar: O{bar['open']:.2f} H{bar['high']:.2f} L{bar['low']:.2f} C{bar['close']:.2f}"
        
        logger.info(f"📈 {symbol} @ ${price:.2f} | Vol: {volume:,.0f}{bar_info}")


# ==========================================================
# ORDER PLACEMENT
# ==========================================================

async def place_bracket(symbol: str, price: float):
    async with order_semaphore:
        order = build_bracket(symbol, price)
        if not order:
            return
        try:
            response = await asyncio.to_thread(client.order_place, account_hash, order)
            logger.info(f"📤 Order placed for {symbol}: {response.status_code}")
        except Exception as e:
            logger.error(f"Order placement failed for {symbol}: {e}")

# ==========================================================
# POSITION RECONCILER
# ==========================================================

async def position_reconciler():
    global equity, daily_pnl, start_equity, last_equity_print   # ← Global first
    
    while not shutdown_event.is_set():
        if not account_hash:
            await asyncio.sleep(RECONCILE_INTERVAL)
            continue

        try:
            response = await asyncio.to_thread(
                client.account_details, 
                account_hash, 
                fields="positions"
            )

            if response.ok:
                data = response.json()["securitiesAccount"]
                equity = data["currentBalances"]["equity"]
                daily_pnl = equity - start_equity

                # Update positions
                for pos in data.get("positions", []):
                    sym = pos["instrument"]["symbol"]
                    if sym in SYMBOLS:
                        positions[sym]["shares"] = pos["longQuantity"] - pos["shortQuantity"]
                        positions[sym]["entry_price"] = pos.get("averagePrice")
                        positions[sym]["unrealized_pnl"] = pos.get("currentDayProfitLoss", 0)

                # Print equity summary every 5 minutes
                now = datetime.now().timestamp()
                if now - last_equity_print > 300:
                    last_equity_print = now
                    logger.info(
                        f"📊 Equity: ${equity:,.2f} | "
                        f"Daily PnL: ${daily_pnl:,.2f} | "
                        f"Positions: AAPL={positions['AAPL']['shares']}, "
                        f"MSFT={positions['MSFT']['shares']}"
                    )

        except Exception as e:
            logger.error(f"Reconciler error: {e}")

        await asyncio.sleep(RECONCILE_INTERVAL)

# ==========================================================
# MARKET HOURS
# ==========================================================

def is_market_open() -> bool:
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))  # ET
    if now.weekday() >= 5:
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
            logger.info("🔌 Starting Schwab Stream...")
            stream.start(quote_handler)
            stream.account_activity(activity_handler)
            stream.level_one_equities(keys=SYMBOLS, fields="0,1,2,3,4,5,6,7,8")

            while not shutdown_event.is_set():
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Stream error: {e}")
            await asyncio.sleep(5)

# ==========================================================
# BOT LOOP
# ==========================================================
async def bot_loop():
    """Main event processing loop"""
    while not shutdown_event.is_set():
        try:
            event = await event_queue.get()
            symbol = event["symbol"]

            if event["type"] == "quote":
                # Calculate volume delta
                volume_delta = max(0, event["volume"] - last_cumulative_volume[symbol])
                last_cumulative_volume[symbol] = event["volume"]

                # Update OHLC bars
                new_bar = update_ohlc(
                    symbol, 
                    event["price"], 
                    event["timestamp"], 
                    volume_delta
                )

                # === LIVE PRICE MONITORING ===
                log_price_update(symbol, event["price"], event["volume"])

                # === ENTRY SIGNAL CHECK ===
                if (
                    new_bar 
                    and risk_check()
                    and positions[symbol]["shares"] == 0
                    and entry_condition(symbol)
                    and is_market_open()
                ):
                    logger.info(f"🚀 ENTRY SIGNAL → {symbol} @ ${event['price']:.2f}")
                    asyncio.create_task(
                        place_bracket(symbol, ohlc[symbol][-1]["close"])
                    )

            elif event["type"] == "fill":
                await handle_fill_async(symbol, event["shares"], event["price"], event["side"])

        except Exception as e:
            logger.error(f"Bot loop error: {e}")
            await asyncio.sleep(0.1)
            

# ==========================================================
# MAIN
# ==========================================================

async def main():
    global start_equity, account_hash

    # Account Initialization
    try:
        linked_resp = await asyncio.to_thread(client.linked_accounts)
        if not linked_resp.ok:
            logger.error("Failed to get linked accounts")
            return

        for acc in linked_resp.json():
            if str(acc.get("accountNumber")) == ACCOUNT_NUMBER:
                account_hash = acc.get("hashValue")
                break

        if not account_hash:
            logger.error(f"Account {ACCOUNT_NUMBER} not found")
            return

        acc_resp = await asyncio.to_thread(client.account_details, account_hash, fields="positions")
        if acc_resp.ok:
            data = acc_resp.json()["securitiesAccount"]
            start_equity = data["currentBalances"]["equity"]
            equity = start_equity
            logger.info(f"✅ Account initialized | Starting Equity: ${start_equity:,.2f}")
    except Exception as e:
        logger.error(f"Account init failed: {e}")
        return

    # Start tasks
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: shutdown_event.set())
    loop.add_signal_handler(signal.SIGTERM, lambda: shutdown_event.set())

    await asyncio.gather(
        stream_task(),
        bot_loop(),
        position_reconciler(),
        return_exceptions=True
    )


if __name__ == "__main__":
    asyncio.run(main())