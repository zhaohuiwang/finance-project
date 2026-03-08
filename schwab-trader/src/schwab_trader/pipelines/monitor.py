# src/schwab_bot/pipelines/monitor.py

import os
import asyncio
import csv
from datetime import datetime
import yaml
from pydantic import ValidationError
from dotenv import load_dotenv  # import dotenv
import schwabdev
from schwabdev.stream import StreamClient
from ...config.config_model import BotConfig  # relative import

# Load environment variables from .env file
load_dotenv()  # This loads the variables into environment


class SchwabBot:
    def __init__(self, config_path="conf/config.yaml"):
        self.config = self.load_config(config_path)
        self.client = schwabdev.Client(
            os.getenv("APP_KEY"),  # Use the env variables
            os.getenv("APP_SECRET"),
            os.getenv("CALLBACK_URL"),
        )
        self.stream_client = StreamClient(os.getenv("APP_KEY"), os.getenv("APP_SECRET"))
        self.positions = {}
        self.log_file = self.config.log_file
        self.setup_logging()

    def load_config(self, path):
        """Load and validate the YAML config."""
        with open(path) as f:
            config_data = yaml.safe_load(f)
        try:
            return BotConfig(**config_data)
        except ValidationError as e:
            print("Config validation error:", e)
            raise

    def setup_logging(self):
        """Set up CSV logging."""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "symbol", "action", "price"])

    def log_alert(self, symbol, action, price):
        """Log alerts to a CSV file."""
        timestamp = datetime.now()
        with open(self.log_file, mode="a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, symbol, action, price])
        print(f"[ALERT] {timestamp} - {symbol}: {action} at {price}")

    def trading_rule(self, symbol, price):
        """Trading logic based on price and position."""
        action = None
        rule = self.config.tickers.get(symbol)

        if not rule:
            return

        current_position = self.positions.get(symbol, 0)

        if price < rule.buy_below and current_position == 0:
            action = "BUY"
            self.positions[symbol] = 1
        elif price > rule.sell_above and current_position > 0:
            action = "SELL"
            self.positions[symbol] = 0

        if action:
            self.log_alert(symbol, action, price)

    async def handle_quote(self, data):
        """Handle streaming quotes."""
        symbol = data["symbol"]
        price = data["lastPrice"]
        self.trading_rule(symbol, price)

    async def poll_quotes(self, symbols):
        """Fallback polling for quotes."""
        while True:
            quotes = self.client.quotes(symbols).json()
            for symbol, quote in quotes.items():
                self.trading_rule(symbol, quote["lastPrice"])
            await asyncio.sleep(self.config.polling_interval)

    async def run(self):
        """Run the bot with streaming and polling."""
        tickers = list(self.config.tickers.keys())
        self.stream_client.subscribe_quotes(tickers, self.handle_quote)
        await asyncio.gather(self.stream_client.run(), self.poll_quotes(tickers))
