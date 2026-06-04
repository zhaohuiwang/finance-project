
""""
The bot trades one stock (default: NBIS) using:
Short Moving Average - SHORT_MA (e.g. 9 periods)
Long Moving Average - LONG_MA (e.g. 21 periods)
Candle interval - INTERVAL_MIN (e.g. 5 minutes)
It checks the stock every Candle interval and:
When the SHORT_MA crosses above the LONG_MA, the bot buy QUANTITY shares.
When the SHORT_MA crosses below the LONG_MA, the bot sells all shares.
The bot only trades during market hours (8:30 AM - 3:00 PM CT) and logs all actions and signals for transparency.


"""


import os
import time
import datetime
import pandas as pd
import logging
from dotenv import load_dotenv
import schwabdev
import schedule

# ========================= CONFIG =========================
load_dotenv()

SYMBOL = "NBIS"
MAX_POSITION = 100  # max shares to hold for risk management

SHORT_MA = 9
LONG_MA = 21
QUANTITY = 10  # shares per trade
INTERVAL_MIN = 5  # 5 or 15 recommended

STOP_LOSS_PCT = 0.05  # 5%

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ========================= CLIENT =========================
client = schwabdev.Client(
    os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
)

# Get account hash
if not os.getenv("ACCOUNT_HASH"):
    accounts = client.linked_accounts().json()
    ACCOUNT_HASH = accounts[0]["hashValue"]
    logger.info(f"Using account hash: {ACCOUNT_HASH}")
else:
    ACCOUNT_HASH = os.getenv("ACCOUNT_HASH")


# ========================= HELPERS =========================
def is_market_open():
    """Simple and reliable market hours check in Central Time (CT)"""
    now = datetime.datetime.now(datetime.timezone.utc)

    # Convert UTC to Central Time (CT = UTC-5)
    now_ct = now - datetime.timedelta(hours=5)

    weekday = now_ct.weekday()  # 0=Monday, 4=Friday
    hour = now_ct.hour
    minute = now_ct.minute

    # Only trade Monday to Friday
    if weekday >= 5:  # Saturday or Sunday
        logger.info("Weekend - Market Closed")
        return False

    # Market Open: 8:30 AM - 3:00 PM CT
    current_time_in_minutes = hour * 60 + minute
    open_time = 8 * 60 + 30  # 8:30 AM
    close_time = 15 * 60  # 3:00 PM

    is_open = open_time <= current_time_in_minutes < close_time

    if is_open:
        logger.info(f"🟢 Market OPEN (CT: {now_ct.strftime('%H:%M')})")
    else:
        logger.info(f"🔴 Market CLOSED (CT: {now_ct.strftime('%H:%M')})")

    return is_open


def get_price_data():
    """Fetch price history"""
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=10)

    resp = client.price_history(
        SYMBOL,
        periodType="day",
        frequencyType="minute",
        frequency=INTERVAL_MIN,
        startDate=start,
        endDate=end,
        needExtendedHoursData=False,
    )

    if resp.status_code != 200:
        logger.error(f"Price history failed: {resp.status_code} - {resp.text[:200]}")
        return None

    data = resp.json()
    candles = data.get("candles", [])

    if not candles:
        logger.warning("No candle data returned")
        return None

    df = pd.DataFrame(candles)
    df["datetime"] = pd.to_datetime(df["datetime"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[["open", "high", "low", "close", "volume"]]

    logger.info(f"✅ Fetched {len(df)} candles | Latest: {df.index[-1]}")
    return df


def get_position():
    """Get current position"""
    try:
        resp = client.account_details(ACCOUNT_HASH, fields="positions")
        if resp.status_code != 200:
            return 0.0

        positions = resp.json().get("securitiesAccount", {}).get("positions", [])
        for pos in positions:
            if pos["instrument"]["symbol"] == SYMBOL:
                return float(pos.get("longQuantity", 0)) - float(
                    pos.get("shortQuantity", 0)
                )
        return 0.0
    except:
        return 0.0


def place_order(instruction: str, quantity: int):
    """Place market order"""
    order = {
        "orderType": "MARKET",
        "session": "NORMAL",
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": instruction,
                "quantity": quantity,
                "instrument": {"symbol": SYMBOL, "assetType": "EQUITY"},
            }
        ],
    }

    resp = client.place_order(ACCOUNT_HASH, order)
    logger.info(f"Order {instruction} {quantity} {SYMBOL} → Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        logger.info("✅ Order accepted by Schwab")
    else:
        logger.error(f"Order failed: {resp.text}")


def calculate_signals(df):
    """Improved Moving Average Signals"""
    if len(df) < LONG_MA:
        return None, None

    df["short_ma"] = df["close"].rolling(window=SHORT_MA).mean()
    df["long_ma"] = df["close"].rolling(window=LONG_MA).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None

    # Classic Crossover
    if prev["short_ma"] <= prev["long_ma"] and latest["short_ma"] > latest["long_ma"]:
        signal = "BUY"
    elif prev["short_ma"] >= prev["long_ma"] and latest["short_ma"] < latest["long_ma"]:
        signal = "SELL"
    # Trend Following Exit: Sell while short MA is below long MA
    elif latest["short_ma"] < latest["long_ma"]:
        signal = "SELL"

    return signal, latest["close"]


# ========================= MAIN TRADING LOGIC =========================
def trading_logic():
    logger.info(f"Running strategy for {SYMBOL}...")

    if not is_market_open():
        return

    df = get_price_data()
    if df is None or len(df) < LONG_MA:
        logger.warning("Not enough data")
        return

    position = get_position()
    signal, current_price = calculate_signals(df)

    logger.info(
        f"Price: ${current_price:.2f} | "
        f"Short MA: {df['short_ma'].iloc[-1]:.2f} | "
        f"Long MA: {df['long_ma'].iloc[-1]:.2f} | "
        f"Position: {position:.0f} | Signal: {signal}"
    )

    # === EXECUTION ===
    if signal == "BUY" and position < MAX_POSITION:  # safety cap
        logger.info("🚀 BUY SIGNAL - Placing order")
        place_order("BUY", QUANTITY)

    elif signal == "SELL" and position > 0:
        # sell_qty = min(QUANTITY, int(position))
        logger.info(f"🔻 SELL SIGNAL - Selling {position} shares")
        place_order("SELL", position)


# ========================= RUN BOT =========================
if __name__ == "__main__":
    logger.info("=== Schwab Moving Average Bot Started ===")
    logger.info(f"Trading {SYMBOL} | MA({SHORT_MA},{LONG_MA}) | Qty={QUANTITY}")

    # First run
    trading_logic()

    # Schedule every INTERVAL_MIN minutes
    schedule.every(INTERVAL_MIN).minutes.do(trading_logic)

    while True:
        schedule.run_pending()
        time.sleep(10)
