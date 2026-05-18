import asyncio
import os
from collections import deque
from datetime import datetime, timedelta

from alpaca_trade_api.stream import Stream  # Uses WebSockets, not REST

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


SYMBOLS = ["AAPL", "TSLA", "NVDA"]  # expand to 500+

# import pandas as pd
# sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
# SYMBOLS = sp500["Symbol"].tolist()

WINDOW_MINUTES = 20
DROP_THRESHOLD = 2.0

# Store rolling window per symbol
price_data = {}


def init_symbol(symbol):
    price_data[symbol] = deque()  # (timestamp, price)


def update_window(symbol, price, timestamp):
    window = price_data[symbol]
    window.append((timestamp, price))

    cutoff = timestamp - timedelta(minutes=WINDOW_MINUTES)

    while window and window[0][0] < cutoff:
        window.popleft()


def check_drop(symbol):
    window = price_data[symbol]

    if len(window) < 2:
        return

    # simple volatility filter
    if max(prices) - min(prices) < 0.5:
        return

    prices = [p for _, p in window]
    max_price = max(prices)
    current_price = prices[-1]

    drop_pct = (max_price - current_price) / max_price * 100

    if drop_pct >= DROP_THRESHOLD:
        print(f"🚨 {symbol} DROP {drop_pct:.2f}% in 20min")

        # Optional trade hook
        # place_order(symbol)


async def trade_handler(data):
    symbol = data.symbol
    price = data.price
    timestamp = data.timestamp

    if symbol not in price_data:
        init_symbol(symbol)

    update_window(symbol, price, timestamp)
    check_drop(symbol)


async def main():
    stream = Stream(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY"),
        base_url=os.getenv("ALPACA_BASE_URL"),
        data_feed="iex",
    )

    for symbol in SYMBOLS:
        stream.subscribe_trades(trade_handler, symbol)

    print("🚀 Real-time scanner running...")
    await stream._run_forever()


if __name__ == "__main__":
    asyncio.run(main())
