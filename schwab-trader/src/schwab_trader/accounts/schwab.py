
import logging
import os
from dotenv import load_dotenv
from pathlib import Path
import sys

import schwabdev

load_dotenv()

# ========================= LOGGING SETUP =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ========================= SCHWAB AUTH SETUP =========================
def initialize_client(
    tokens_path="~/.schwabdev/tokens.db"
    ):
    """Normal initialization using existing tokens.db"""
    try:        
        tokens_path = str(Path(tokens_path).expanduser())
        APP_KEY = os.getenv("APP_KEY")
        APP_SECRET = os.getenv("APP_SECRET")
        CALLBACK_URL = os.getenv("CALLBACK_URL")
        logger.info(f"Initializing Schwab Client with tokens at: {tokens_path}")
    except Exception as e:
        logger.error(f"Error occurred while initializing tokens path: {e}")
        raise

    return schwabdev.Client(
        APP_KEY,
        APP_SECRET,
        callback_url=CALLBACK_URL,
        tokens_db=tokens_path,
        encryption=None, # the following are defaults.
        timeout=10,
        call_on_auth=None,
        open_browser_for_auth=True
    )



# ========================= SCHWAB ACCOUNT =========================
client = initialize_client()

  
class Position:
    """Represents a single account position"""

    def __init__(self, raw):
        self.raw = raw

        instrument = raw.get("instrument", {})

        self.symbol = instrument.get("symbol")
        self.asset_type = instrument.get("assetType")

        self.quantity = raw.get("longQuantity", 0)
        self.avg_price = raw.get("averagePrice")
        self.market_value = raw.get("marketValue")

        self.day_pl = raw.get("currentDayProfitLoss")
        self.total_pl = raw.get("longOpenProfitLoss")

    def __repr__(self):
        return f"Position(symbol={self.symbol}, qty={self.quantity})"


class SchwabAccount:

    def __init__(self, client, account_hash):
        self.client = client
        self.account_hash = account_hash
        self.refresh()

    def refresh(self):
        """Pull fresh account data"""
        response = self.client.account_details(
            accountHash=self.account_hash, fields="positions"
        )

        self.data = response.json()

        self.account = self.data.get("securitiesAccount", {})
        self.current = self.account.get("currentBalances", {})

        self._positions_raw = self.account.get("positions", [])

    # -------- BASIC INFO --------

    @property
    def account_number(self):
        return self.account.get("accountNumber")

    @property
    def account_type(self):
        return self.account.get("type")

    # -------- BALANCES --------

    @property
    def cash(self):
        return self.current.get("cashBalance")

    @property
    def equity(self):
        return self.current.get("equity")

    @property
    def available_funds(self):
        return self.current.get("availableFunds")

    @property
    def buying_power(self):
        return self.current.get("buyingPower")

    # -------- POSITIONS --------

    @property
    def positions(self):
        """Return Position objects"""
        return [Position(p) for p in self._positions_raw]

    @property
    def symbol_quantity_map(self):
        """Quick lookup dictionary"""
        return {p.symbol: p.quantity for p in self.positions if p.quantity > 0}

    def get_position(self, symbol):
        """Return Position object for a symbol"""
        for p in self.positions:
            if p.symbol == symbol:
                return p
        return None

    # -------- SUMMARY --------

    def summary(self):

        return {
            "account": self.account_number,
            "type": self.account_type,
            "cash": self.cash,
            "equity": self.equity,
            "buying_power": self.buying_power,
            "positions": self.symbol_quantity_map,
        }


# # ========================================================================
# # Example Usage - SchwabAccount
# # ========================================================================

# account = SchwabAccount(client, hashValue)

# print("\nACCOUNT INFO")
# print(account.account_number)
# print(account.account_type)

# print("\nBALANCES")
# print("Cash:", account.cash)
# print("Equity:", account.equity)
# print("Buying Power:", account.buying_power)

# print("\nPOSITIONS")
# for p in account.positions:
#     print(
#         p.symbol,
#         "Qty:", p.quantity,
#         "Avg:", p.avg_price,
#         "Market Value:", p.market_value
#     )

# print("\nLOOKUP ONE POSITION")
# pos = account.get_position("ACHR")
# if pos:
#     print("ACHR shares:", pos.quantity)
#     print("Day P/L:", pos.day_pl)

# print("\nSUMMARY")
# print(json.dumps(account.summary(), indent=4))

# # Refresh account data
# account.refresh()

# for pos in account.positions:
#     if pos.symbol == "ACHR" and pos.quantity > 1000:
#         print("Large ACHR position")

# # if account.buying_power > 20000:
# #     place_trade()
