import os
import asyncio
import csv
from datetime import datetime
from dotenv import load_dotenv
import schwabdev
from schwabdev.stream import StreamClient

load_dotenv()

# Initialize Schwab client
client = schwabdev.Client(
    os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
)

# Streaming client
stream_client = StreamClient(os.getenv("app_key"), os.getenv("app_secret"))

# CSV logging setup
log_file = "trade_log.csv"
with open(log_file, mode="w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "symbol", "action", "price", "quantity", "note"])

# Example positions tracker
positions = {}


# Trading rules
def trading_rule(symbol, price):
    """
    Example rules:
    - Buy if price < 50
    - Sell if price > 100
    """
    global positions
    action = None
    qty = 1  # example quantity

    if price < 50:
        if positions.get(symbol, 0) == 0:
            action = "BUY"
            positions[symbol] = qty
    elif price > 100:
        if positions.get(symbol, 0) > 0:
            action = "SELL"
            positions[symbol] = 0

    if action:
        print(f"[{datetime.now()}] {symbol}: {action} at {price}")
        log_trade(symbol, action, price, qty, "rule triggered")
        place_order(symbol, action, qty)


# Place order function
def place_order(symbol, action, quantity):
    """
    Place an order using Schwabdev.
    ⚠️ Be careful: This will execute live trades if credentials are real.
    """
    try:
        order_response = client.place_order(
            account_id=os.getenv("account_id"),
            symbol=symbol,
            quantity=quantity,
            action=action,
            order_type="MARKET",
            price=None,
        )
        print(f"Order response: {order_response.json()}")
    except Exception as e:
        print(f"Error placing order for {symbol}: {e}")


# Logging function
def log_trade(symbol, action, price, quantity, note):
    with open(log_file, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now(), symbol, action, price, quantity, note])


# Async streaming handler
async def handle_quote(data):
    symbol = data["symbol"]
    price = data["lastPrice"]
    trading_rule(symbol, price)


# Polling fallback
async def poll_quotes(symbols, interval=5):
    while True:
        quotes = client.quotes(symbols).json()
        for symbol, quote in quotes.items():
            trading_rule(symbol, quote["lastPrice"])
        await asyncio.sleep(interval)


# Main async function
async def main():
    tickers = ["AAPL", "AMD", "TSLA"]

    # Subscribe to streaming quotes
    stream_client.subscribe_quotes(tickers, handle_quote)

    # Run both streaming and polling concurrently
    await asyncio.gather(stream_client.run(), poll_quotes(tickers))


# Run the bot
if __name__ == "__main__":
    asyncio.run(main())


import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import schwabdev
from schwabdev.stream import StreamClient

load_dotenv()

# Initialize Schwab client
client = schwabdev.Client(
    os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
)

# Streaming client
stream_client = StreamClient(os.getenv("app_key"), os.getenv("app_secret"))

# Example positions tracker
positions = {}


# Test message notification function
def send_test_message(symbol, action, price):
    print(f"[TEST MESSAGE] {datetime.now()} - {symbol}: {action} at {price}")


# Trading rules
def trading_rule(symbol, price):
    """
    Example rules:
    - Buy if price < 50
    - Sell if price > 100
    """
    global positions
    action = None

    if price < 50:
        if positions.get(symbol, 0) == 0:
            action = "BUY"
            positions[symbol] = 1  # simulate holding
    elif price > 100:
        if positions.get(symbol, 0) > 0:
            action = "SELL"
            positions[symbol] = 0  # simulate selling

    if action:
        send_test_message(symbol, action, price)


# Async streaming handler
async def handle_quote(data):
    symbol = data["symbol"]
    price = data["lastPrice"]
    trading_rule(symbol, price)


# Polling fallback
async def poll_quotes(symbols, interval=5):
    while True:
        quotes = client.quotes(symbols).json()
        for symbol, quote in quotes.items():
            trading_rule(symbol, quote["lastPrice"])
        await asyncio.sleep(interval)


# Main async function
async def main():
    tickers = ["AAPL", "AMD", "TSLA"]

    # Subscribe to streaming quotes
    stream_client.subscribe_quotes(tickers, handle_quote)

    # Run both streaming and polling concurrently
    await asyncio.gather(stream_client.run(), poll_quotes(tickers))


# Run the bot
if __name__ == "__main__":
    asyncio.run(main())


import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import schwabdev
from schwabdev.stream import StreamClient

load_dotenv()

# Initialize Schwab client
client = schwabdev.Client(
    os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
)

# Streaming client
stream_client = StreamClient(os.getenv("app_key"), os.getenv("app_secret"))

# Example positions tracker
positions = {}

# Per-ticker dynamic rules: {symbol: {"buy_below": price, "sell_above": price}}
rules = {
    "AAPL": {"buy_below": 140, "sell_above": 160},
    "AMD": {"buy_below": 50, "sell_above": 100},
    "TSLA": {"buy_below": 600, "sell_above": 750},
}


# Test message notification
def send_alert(symbol, action, price):
    print(f"[ALERT] {datetime.now()} - {symbol}: {action} at {price}")


# Trading rules per symbol
def trading_rule(symbol, price):
    """
    Apply dynamic rules for the given symbol.
    """
    global positions
    action = None
    symbol_rules = rules.get(symbol)

    if not symbol_rules:
        return  # no rules for this symbol

    buy_below = symbol_rules.get("buy_below")
    sell_above = symbol_rules.get("sell_above")

    if buy_below is not None and price < buy_below and positions.get(symbol, 0) == 0:
        action = "BUY"
        positions[symbol] = 1  # simulate position
    elif sell_above is not None and price > sell_above and positions.get(symbol, 0) > 0:
        action = "SELL"
        positions[symbol] = 0  # simulate closing position

    if action:
        send_alert(symbol, action, price)


# Async streaming handler
async def handle_quote(data):
    symbol = data["symbol"]
    price = data["lastPrice"]
    trading_rule(symbol, price)


# Polling fallback
async def poll_quotes(symbols, interval=5):
    while True:
        quotes = client.quotes(symbols).json()
        for symbol, quote in quotes.items():
            trading_rule(symbol, quote["lastPrice"])
        await asyncio.sleep(interval)


# Main async function
async def main():
    tickers = list(rules.keys())

    # Subscribe to streaming quotes
    stream_client.subscribe_quotes(tickers, handle_quote)

    # Run both streaming and polling concurrently
    await asyncio.gather(stream_client.run(), poll_quotes(tickers))


# Run the bot
if __name__ == "__main__":
    asyncio.run(main())


import os
import asyncio
import csv
from datetime import datetime
from dotenv import load_dotenv
import schwabdev
from schwabdev.stream import StreamClient

load_dotenv()

# Initialize Schwab client
client = schwabdev.Client(
    os.getenv("app_key"), os.getenv("app_secret"), os.getenv("callback_url")
)

# Streaming client
stream_client = StreamClient(os.getenv("app_key"), os.getenv("app_secret"))

# CSV logging setup
log_file = "alerts_log.csv"
with open(log_file, mode="w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "symbol", "action", "price"])

# Example positions tracker
positions = {}

# Per-ticker dynamic rules
rules = {
    "AAPL": {"buy_below": 140, "sell_above": 160},
    "AMD": {"buy_below": 50, "sell_above": 100},
    "TSLA": {"buy_below": 600, "sell_above": 750},
}


# Logging function
def log_alert(symbol, action, price):
    timestamp = datetime.now()
    with open(log_file, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, symbol, action, price])
    print(f"[ALERT] {timestamp} - {symbol}: {action} at {price}")


# Trading rules per symbol
def trading_rule(symbol, price):
    global positions
    action = None
    symbol_rules = rules.get(symbol)

    if not symbol_rules:
        return

    buy_below = symbol_rules.get("buy_below")
    sell_above = symbol_rules.get("sell_above")

    if buy_below is not None and price < buy_below and positions.get(symbol, 0) == 0:
        action = "BUY"
        positions[symbol] = 1
    elif sell_above is not None and price > sell_above and positions.get(symbol, 0) > 0:
        action = "SELL"
        positions[symbol] = 0

    if action:
        log_alert(symbol, action, price)


# Async streaming handler
async def handle_quote(data):
    symbol = data["symbol"]
    price = data["lastPrice"]
    trading_rule(symbol, price)


# Polling fallback
async def poll_quotes(symbols, interval=5):
    while True:
        quotes = client.quotes(symbols).json()
        for symbol, quote in quotes.items():
            trading_rule(symbol, quote["lastPrice"])
        await asyncio.sleep(interval)


# Main async function
async def main():
    tickers = list(rules.keys())

    # Subscribe to streaming quotes
    stream_client.subscribe_quotes(tickers, handle_quote)

    # Run both streaming and polling concurrently
    await asyncio.gather(stream_client.run(), poll_quotes(tickers))


if __name__ == "__main__":
    asyncio.run(main())
