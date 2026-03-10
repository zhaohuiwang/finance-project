# import sys
# from pathlib import Path

# # Add the src folder to sys.path dynamically
# sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

import datetime
import json
from pprint import pprint

from src.schwab_trader.accounts.schwab import client, SchwabAccount
from src.schwab_trader.accounts.type_literal import Duration
from src.schwab_trader.orders.equity import (
    buy_market_dict,
    sell_market_dict,
    buy_limit_dict,
    sell_limit_dict,
    buy_limit_trigger_sell_limit_dict,
    sell_limit_sell_stoplimit_oco_dict,
    buy_limit_trigger_sell_limit_sell_stop_oco_dict,
    sell_trailing_stop_dict,
)
from src.schwab_trader.orders.option import (
    buy_limit_single_option_dict,
    buy_limit_vertical_call_spread_dict,
    sell_covered_call_dict,
)

from src.schwab_trader.orders.utils import (
    place_order,
    cancel_order,
    get_utc_time_range,
    iter_keys_path_tuple,
)

# Specified an accout number, instiate a client, the client will fetch the matching account hashValue for later identification

accountNumber = "29308909"


# ========================================================================
# From account number (accountNumber) to account hash (hashValue)
# ========================================================================

response = client.linked_accounts()
data = response.json()
hashValue = next(
    (item["hashValue"] for item in data if item["accountNumber"] == accountNumber), None
)

print(hashValue)

response = client.account_details(accountHash=hashValue, fields="positions")

data = response.json()

print(json.dumps(data, indent=4))


# ensure order total are within the buying power limit of the account
# stream account balance and positions data to make real-time decision on order placement and management

# ========================================================================
# Place an equity order
# ========================================================================

# create an order configuration dictionary
order_1 = buy_limit_dict(
    symbol="ACHR",
    quantity=1,
    limit_price=6.2,
    duration="DAY",
)

order_2 = sell_limit_dict(
    symbol="NBIS",
    quantity=1,
    limit_price=100.0,
    duration="GOOD_TILL_CANCEL",
)

order_3 = buy_limit_trigger_sell_limit_dict(
    symbol="NBIS",
    quantity=1,
    buy_limit_price=20,
    sell_limit_price=120,
    buy_duration="DAY",
    sell_duration="GOOD_TILL_CANCEL",
)

order_4 = sell_limit_sell_stoplimit_oco_dict(
    symbol="NBIS",
    quantity=1,
    sell_limit_price=120,  # 45.97
    sell_stop_price=80,  # 37.00
    sell_stoplimit_price=80.20,  # 37.03
    duration="DAY",
)

order_5 = buy_limit_trigger_sell_limit_sell_stop_oco_dict(
    symbol="NBIS",
    quantity=1,
    buy_limit_price=80.0,  # 14.97
    sell_limit_price=98.2,  # 15.27
    sell_stop_price=75.2,  # 11.27
    buy_duration="DAY",
    sell_duration="GOOD_TILL_CANCEL",
)

order_6 = sell_trailing_stop_dict(
    symbol="NBIS",
    quantity=1,
    stop_price_offset=10,  # 10
    duration="DAY",
)

order_7 = buy_market_dict(
    symbol="THISISADEMO",
    quantity=1,
    duration="DAY",
)

order_8 = sell_market_dict(
    symbol="THISISADEMO",
    quantity=1,
    duration="DAY",
)


# submit an order
order = order_5


status_code, date, order_id = place_order(
    client=client, accountHash=hashValue, order=order
)

# status_code 201 >>> success

# ========================================================================
# Place an option order
# ========================================================================

order_o1 = sell_covered_call_dict(
    symbol="XYZ   260313C00009000",  # XYZ Mar 13 2026 $9.00 Call
    # symbol=
    quantity=1,
    limit_price=0.30,
)

order_o2 = buy_limit_vertical_call_spread_dict(
    symbol_higher_strike="XYZ   260313C00450000",  # XYZ Mar 13 2026 $45 Put
    symbol_lower_strike="XYZ   260313P00043000",  # XYZ Mar 13 2026 $43 Put
    # symbol_higher_strike=
    # symbol_lower_strike=
    quantity=1,
    limit_price=0.30,
)

order_o3 = buy_limit_single_option_dict(
    symbol="XYZ   260313C00500000",  # XYZ March 13, 2024 $50 CALL
    # symbol=
    quantity=1,
    limit_price=0.30,
)

# submit an order
order = order_o1


status_code, date, order_id = place_order(
    client=client, accountHash=hashValue, order=order
)

# status_code 201 >>> success

# ========================================================================
# Check orders
# ========================================================================


# Get all orders (or met the status) in the past delta time period

from_time, to_time = get_utc_time_range(
    # to_time= datetime.datetime(2026, 3, 6, 10, 0)
    offset=datetime.timedelta(days=0, hours=0, minutes=20)
)
# or simply
from_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
    days=0, hours=2, minutes=5
)
to_time = datetime.datetime.now(datetime.timezone.utc)

orders = client.account_orders(
    hashValue,
    fromEnteredTime=from_time,
    toEnteredTime=to_time,
    # status='PENDING_ACTIVATION'
).json()
print(orders)

# orders_all_account = client.account_orders_all(
#     fromEnteredTime=from_time,
#     toEnteredTime=to_time,
# ).json()
# print(orders_all_account)

# status string Enum: [ AWAITING_PARENT_ORDER, AWAITING_CONDITION, AWAITING_STOP_CONDITION, AWAITING_MANUAL_REVIEW, ACCEPTED, AWAITING_UR_OUT, PENDING_ACTIVATION, QUEUED, WORKING, REJECTED, PENDING_CANCEL, CANCELED, PENDING_REPLACE, REPLACED, FILLED, EXPIRED, NEW, AWAITING_RELEASE_TIME, PENDING_ACKNOWLEDGEMENT, PENDING_RECALL, UNKNOWN ]


# Get values for specified keys from returned json object from client.account_orders()
iter_result = list(
    iter_keys_path_tuple(
        data=orders,
        keys=["orderId", "enteredTime", "status", "price"],
        predicate=lambda d: d.get("cancelable") is True,
        root_name="orders",
    )
)

pprint([dict(group) for group in iter_result])


# ========================================================================
# Cancel orders
# ========================================================================

# List all the order IDs
order_ids = [
    value for group in iter_result for path, value in group if "['orderId']" in path
]

# Examine an order details - the 1st in the list
orders = client.order_details(
    accountHash=hashValue,
    #orderId=order_ids[0],
    orderId='1005645558838',
    ).json()


# Cancel an order
status_code, date = cancel_order(
    client=client,
    accountHash=hashValue,
    #order_id=order_ids[0],
    order_id='1005645558909',
    
)

if status_code == 200:
    order_ids.pop(0)  # cancellation succeed, remove it (the 1st) from the list


# ========================================================================
# Other client methods
# ========================================================================

response = (
    client.preferences()
)  # Get user preference information for the logged in user.


response = client.movers("NASDAQ")  # a specific index and direction
response = client.price_history(
    symbol="NBIS",
    periodType="month",
    frequencyType="daily",
    # frequency=1,
    needExtendedHoursData=False,
    needPreviousClose=False,
)  # Get price history for a ticker
response.status_code
response.json()


response = client.linked_accounts()  # [{'accountNumber': str, 'hashValue': str},]
response.json()

response = client.account_details(
    accountHash=hashValue, fields="positions"  # the default will not list positions
)  # Specific account information with balances and positions.
data = response.json()
import json

print(json.dumps(data, indent=4))

# List holding position and quantity, lost of tuple like [('ACHR', 2900.0), ...]
positions = data["securitiesAccount"]["positions"]

symbol_quantity = [
    (item["instrument"]["symbol"], item["longQuantity"]) for item in positions
]


from_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
    days=0, hours=2, minutes=1
)
to_time = datetime.datetime.now(datetime.timezone.utc)


response = client.account_orders_all(
    fromEnteredTime=from_time,
    toEnteredTime=to_time,
    maxResults=None,
    status=None,
)  # Get all orders for all accounts

response = client.account_orders(
    accountHash=hashValue,
    fromEnteredTime=from_time,
    toEnteredTime=to_time,
    maxResults=None,  # int | None,
    status=None,  # str | None = None
)  # All orders for a specific account. Orders retrieved can be filtered.

response = client.option_expiration_chain(
    symbol="NBIS",
)  # Get an option expiration chain for a ticker

response = client.option_chains(
    symbol="NBIS",
    # contractType: str | None = None,
    # strikeCount: int | None = None,
    # includeUnderlyingQuote: bool | None = None,
    # strategy: str | None = None, interval: str | None = None,
    # strike: float | None = None,
    # range: str | None = None,
    # fromDate: datetime.datetime | datetime.date | str | None = None,
    # toDate: datetime.datetime | datetime.date | str | None = None,
    # volatility: float | None = None,
    # underlyingPrice: float | None = None,
    # interestRate: float | None = None,
    # daysToExpiration: int | None = None,
    # expMonth: str | None = None,
    # optionType: str | None = None,
    # entitlement: str | None = None
)  # Get Option Chain including information on options contracts associated with each expiration for a ticker.

response = client.quote(
    symbol_id="NBIS",
    # fields: str | None = None
)  # Get quote for a single symbol

response = client.quotes(
    symbols=["NBIS", "IREN"],
    fields="",  # str | None = None
    indicative=False,
)  # Get quote for a list of symbols

response = client.transactions(
    accountHash=hashValue,
    startDate="",
    endDate="",
    types="",
    symbol=None,  # str | None = None
)  # All transactions for a specific account.

response = client.transaction_details(
    accountHash=hashValue, transactionId=""  # str | int
)  # Get specific transaction information for a specific account


# ========================================================================
# Example Usage - SchwabAccount
# ========================================================================

account = SchwabAccount(client, hashValue)

print("\nACCOUNT INFO")
print(account.account_number)
print(account.account_type)

print("\nBALANCES")
print("Cash:", account.cash)
print("Equity:", account.equity)
print("Buying Power:", account.buying_power)

print("\nPOSITIONS")
for p in account.positions:
    print(
        p.symbol,
        "Qty:",
        p.quantity,
        "Avg:",
        p.avg_price,
        "Market Value:",
        p.market_value,
    )

print("\nLOOKUP ONE POSITION")
pos = account.get_position("ACHR")
if pos:
    print("ACHR shares:", pos.quantity)
    print("Day P/L:", pos.day_pl)

print("\nSUMMARY")
print(json.dumps(account.summary(), indent=4))

# Refresh account data
account.refresh()

# for pos in account.positions:
#     if pos.symbol == "ACHR" and pos.quantity > 1000:
#         print("Large ACHR position")

# if account.buying_power > 20000:
#     place_trade()
