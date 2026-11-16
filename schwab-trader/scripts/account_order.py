# import sys
# from pathlib import Path

# # Add the src folder to sys.path dynamically
# sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

import datetime as dt
import json
import pprint
import pandas as pd

from schwab_trader.accounts.schwab import client, SchwabAccount

from schwab_trader.orders.equity_v2 import (
    build_market_order_payload,
    build_limit_order_payload,
    build_trailing_stop_order_payload,
    build_oto_limit_order_payload,
    # build_sell_limit_stoplimit_oco_payload,
    # build_sell_trailingstop_sell_limit_oco_payload,
    # build_sell_trailingstop_sell_stoplimit_oco_payload,
    # build_buy_limit_trigger_sell_limit_stop_oco_payload,
    # build_buy_trailingstop_trigger_sell_trailingstop_payload,
    # build_sell_trailingstop_trigger_buy_trailingstop_payload,
)

# from schwab_trader.orders.option import (
#     buy_limit_single_option_dict,
#     buy_limit_vertical_call_spread_dict,
#     sell_covered_call_dict,
# )

from schwab_trader.orders.utils import (
    get_hashvalue,
    place_order,
    cancel_order,
    get_utc_time_range,
    iter_keys_path_tuple,
    get_orders,
)

# Specified an accout number, instiate a client, the client will fetch the matching account hashValue for later identification
# From account number (accountNumber) to account hash (hashValue)
accountNumber = "29308909"

hashValue = get_hashvalue(client, accountNumber)
print(hashValue)
# ========================================================================
# Account Summary
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

# Session:
# NORMAL    Regular hours order
# AM        Pre-market buy/sell
# PM        After-hours (4–8 pm ET)
# SEAMLESS  24/5 overnight continuous
# ========================================================================

# create an order configuration dictionary
# Buy order configurations
order_payload = build_market_order_payload(
    symbol="THISISADEMO",
    quantity=1,
    instruction="BUY",  # "BUY" | "SELL"
    session="NORMAL",
)

order_payload = build_limit_order_payload(
    symbol="THISISADEMO",
    quantity=300,
    limit_price=278.4,
    instruction="SELL",
    session="NORMAL",
    duration="DAY",
)


order_payload = build_oto_limit_order_payload(
    symbol="THISISADEMO",
    quantity=1,
    instructions=["BUY", "SELL"],
    limit_prices=[100, 120],
    sessions=("NORMAL", "NORMAL"),
    durations=("DAY", "DAY"),
)

# order_payload = build_buy_limit_trigger_sell_limit_stop_oco_payload(
#     symbol="THISISADEMO",
#     quantity=400,
#     # (buy_limit, sell_limit, sell_stop)
#     prices=[10.0, 15.0, 9.0],
#     # (buy_session, sell_limit_session, sell_stop_session)
#     sessions=("NORMAL", "NORMAL", "NORMAL"),
#     # (buy_duration, sell_duration)
#     durations=("DAY", "GOOD_TILL_CANCEL"),
# )

order_payload = build_trailing_stop_order_payload(
    symbol="THISISADEMO",
    quantity=1,
    instruction="BUY",  # "BUY" | "SELL"
    stop_price_link_basis="BID",
    stop_price_link_type="PERCENT",  # "VALUE" | "PERCENT" | "TICK"
    stop_price_offset=2.0,
    session="NORMAL",
    duration="DAY",
)


# ========================================================================
# Check orders
# ========================================================================
from_time, to_time = get_utc_time_range(
    offset=dt.timedelta(days=1, hours=8, minutes=0)
    )

orders = client.account_orders(
    hashValue,
    fromEnteredTime=from_time,
    toEnteredTime=to_time,
    # status="EXPIRED",
    # status="PENDING_ACTIVATION",
    status="WORKING",
    # status="FILLED",
).json()

print(json.dumps(orders, indent=4))

# Check account holding positions
account = SchwabAccount(client, hashValue)
print(account.positions)


#  ==============================================================
# submit an order 
# 🚧 TODO: This feature is still under development.
# ❗ Important: Validate user input.
#  ==============================================================

#  Build an 🟢 order payload
order_payload = build_limit_order_payload(
    symbol="NBIS",
    quantity=100,
    limit_price=105.1,
    instruction="BUY", # ❗BUY❗ 
    session="SEAMLESS",
    duration="DAY",
)

# Submit an 🟢 order
status, date, order_id = place_order(
    client=client,
    accountHash=hashValue,
    order=order_payload,
)
print(status, date, order_id)

#  ==============================================================
# Build an 🔴 order payload
order_payload = build_limit_order_payload(
    symbol="NBIS",
    quantity=100,
    limit_price=107.3,
    instruction="SELL", # ❗SELL❗
    session="SEAMLESS",
    duration="DAY",
)

# Submit an 🔴 order
status, date, order_id = place_order(
    client=client,
    accountHash=hashValue,
    order=order_payload,
)
print(status, date, order_id)

#  ==============================================================
# Build an 🟢 --> 🔴 order payload
order_payload = build_oto_limit_order_payload(
    symbol="NBIS",
    quantity=100,
    instructions=["BUY", "SELL"], # ❗BUY --> SELL❗
    limit_prices=[106.2, 117.4],
    # sessions=("NORMAL", "NORMAL"), # 9:30 AM-4:00 PM ET
    sessions=("SEAMLESS", "SEAMLESS"),  # 7:00 AM-8:00 PM ET
    durations=("DAY", "DAY"),
)

# Submit an 🟢 --> 🔴 order
status, date, order_id = place_order(
    client=client,
    accountHash=hashValue,
    order=order_payload,
)
print(status, date, order_id)

#  ==============================================================
# Build an 🔴 --> 🟢 order payload
order_payload = build_oto_limit_order_payload(
    symbol="NBIS",
    quantity=100,
    instructions=["SELL", "BUY"], # ❗SELL --> BUY❗
    limit_prices=[112.2, 108.2],
    # sessions=("NORMAL", "NORMAL"), # 9:30 AM-4:00 PM ET
    sessions=("SEAMLESS", "SEAMLESS"),  # 7:00 AM-8:00 PM ET
    durations=("DAY", "DAY"),
)

# Submit an 🔴 --> 🟢 order
status, date, order_id = place_order(
    client=client,
    accountHash=hashValue,
    order=order_payload,
)
print(status, date, order_id)


order_data = client.order_details(hashValue, order_id)
print(json.dumps(order_data.json(), indent=4))

#  ==============================================================
# Cancel an order
order_id = "1008684396386" # SELL 100 NBIS @117.4
status_code, date = cancel_order(
    client=client,
    accountHash=hashValue,
    order_id=order_id,
)  # status_code 200 >>> success
print(status_code, date)


# List all cancalable orders
from_time, to_time = get_utc_time_range(
    offset=dt.timedelta(days=3, hours=8, minutes=5)
    )

orders = get_orders(
    hashValue=hashValue,
    status=None,
    cancelableOnly=True,
    fromTime=from_time,
    toTime=to_time,
)

for order in orders:
    # print(json.dumps(order, indent=4))
    # TypeError: Object of type datetime is not JSON serializable
    pprint.pprint(orders, indent=2, sort_dicts=False)


# ========================================================================
# Check orders
# ========================================================================


# Get all orders (or met the status) in the past delta time period

from_time, to_time = get_utc_time_range(
    # to_time= dt.datetime(2026, 3, 6, 10, 0)
    offset=dt.timedelta(days=4, hours=1, minutes=5)
)
# or simply
from_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=4, hours=8, minutes=5)
to_time = dt.datetime.now(dt.timezone.utc)

orders = client.account_orders(
    hashValue,
    fromEnteredTime=from_time,
    toEnteredTime=to_time,
    status="WORKING",
    # status="FILLED",
).json()

print(json.dumps(orders, indent=4))


all_orders = get_orders(
    hashValue,
    fromTime=from_time,
    toTime=to_time,
    cancelableOnly=True,
    status="WORKING",
    # status="FILLED",
    # status="AWAITING_PARENT_ORDER",
    # status="PENDING_ACTIVATION"
)
# Return a list of dictionary

df = pd.DataFrame(all_orders)

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
        keys=[
            "orderId",
            "symbol",
            # "instruction",
            # "status",
            "price",
            "quantity",
            # "orderType",
            # "duration"
        ],
        # predicate=lambda d: d.get("cancelable") is True,
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
order = client.order_details(
    accountHash=hashValue,
    orderId=order_id,
    # orderId="1005789269420",
).json()
print(json.dumps(order, indent=4))

# Cancel an order
status_code, date = cancel_order(
    client=client,
    accountHash=hashValue,
    # order_id=order_ids[0],
    order_id="1005645558909",
)

if status_code == 200:
    order_ids.pop(0)  # cancellation succeed, remove it (the 1st) from the list


# To cancel all recent orders
from_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=0, hours=8, minutes=5)
to_time = dt.datetime.now(dt.timezone.utc)

all_orders = get_orders(
    hashValue,
    cancelableOnly=True,
    fromTime=from_time,
    toTime=to_time,
)

for order in all_orders:
    if order.get("cancelable"):
        status_code, date = cancel_order(
            client=client,
            accountHash=hashValue,
            order_id=order.get("orderId"),
        )
        print(status_code)

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


from_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2, hours=2, minutes=1)
to_time = dt.datetime.now(dt.timezone.utc)


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
    startDate=from_time,
    endDate=to_time,
    types="TRADE",
    symbol=None,  # str | None = None
)  # All transactions for a specific account.

data = response.json()
import json

acctivity_list = json.dumps(data, indent=4)
print(acctivity_list)


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




# Compare the steaming data to historical account acctivity data
from_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2, hours=2, minutes=1)
to_time = dt.datetime.now(dt.timezone.utc)
response = client.transactions(
    accountHash=hashValue,
    startDate=from_time,
    endDate=to_time,
    types="TRADE",
    symbol=None,  # str | None = None
)  # All transactions for a specific account.

data = response.json()
import json

acctivity_list = json.dumps(data, indent=4)
print(acctivity_list)



# ========================================================================
# ========================================================================
# Place an option order
# ========================================================================
# ========================================================================


# order_o1 = sell_covered_call_dict(
#     symbol="XYZ   260313C00009000",  # XYZ Mar 13 2026 $9.00 Call
#     quantity=1,
#     limit_price=0.30,
# )

# order_o2 = buy_limit_vertical_call_spread_dict(
#     symbol_higher_strike="XYZ   260313C00450000",  # XYZ Mar 13 2026 $45 Put
#     symbol_lower_strike="XYZ   260313P00043000",  # XYZ Mar 13 2026 $43 Put
#     # symbol_higher_strike=
#     # symbol_lower_strike=
#     quantity=1,
#     limit_price=0.30,
# )

# order_o3 = buy_limit_single_option_dict(
#     symbol="XYZ   260313C00500000",  # XYZ March 13, 2024 $50 CALL
#     # symbol=
#     quantity=1,
#     limit_price=0.30,
# )

# # submit an order
# order = order_o1


# status, date, order_id = place_order(client=client, accountHash=hashValue, order=order)
