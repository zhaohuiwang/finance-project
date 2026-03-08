from lumibot.traders import Trader
from lumibot.strategies.strategy import Strategy
from lumibot.entities import Asset

class MyStrategy(Strategy):
    def initialize(self):
        self.sleeptime = "1D"
        self.symbol = "SPY"

    def on_trading_iteration(self):
        last = self.get_last_price(self.symbol)
        self.log_message(f"Last price for {self.symbol}: {last}")
        asset = self.create_asset(self.symbol)
        order = self.create_order(asset, 1, "buy")
        self.submit_order(order)

trader = Trader()
strategy = MyStrategy()
trader.add_strategy(strategy)
trader.run_all()

