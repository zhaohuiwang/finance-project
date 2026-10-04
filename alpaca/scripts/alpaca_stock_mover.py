
import json
import os
import requests
from dotenv import load_dotenv
from rich import print_json

load_dotenv()


# The top market movers (gainers and losers) 
# https://docs.alpaca.markets/us/reference/movers-1

url = "https://data.alpaca.markets/v1beta1/screener/stocks/movers?"

headers = {
    "accept": "application/json",
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
    "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET_KEY"],
}


response = requests.get(
    url,
    headers=headers,
    params={"top": 10},
    timeout=15
)

response.raise_for_status()
print(response.text)

data = response.json()
print(json.dumps(data, indent=4))

# This will automatically format AND color-code your JSON string or dictionary
print_json(data=data)



# Using alpaca-py
import os
from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.requests import MarketMoversRequest
from alpaca.data.enums import MarketType

client = ScreenerClient(
    api_key=os.getenv("ALPACA_API_KEY"),
    secret_key=os.environ["ALPACA_API_SECRET_KEY"],
)

result = client.get_market_movers(
    MarketMoversRequest(
        market_type=MarketType.STOCKS,
        top=10
    )
)


# Most active stocks by volume 
# https://docs.alpaca.markets/us/reference/mostactives-1
url = "https://data.alpaca.markets/v1beta1/screener/stocks/most-actives"

headers = {
    "accept": "application/json",
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
    "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET_KEY"],
}

response = requests.get(
    url,
    headers=headers,
    params={"top": 20, "by": "volume"},
    timeout=15,
)


response.raise_for_status()
print(response.text)

data = response.json()
print(json.dumps(data, indent=4))

# This will automatically format AND color-code your JSON string or dictionary
print_json(data=data)



# RVOL (Relative Volume) 
# RVOL=Today's Volume / Average Volume over previous N days

symbol = "WDC"

url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
headers = {
    "accept": "application/json",
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
    "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET_KEY"],
}

params = {
    "timeframe": "1Day",
    "limit": 21,
    "feed": "sip"
}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=15
)

response.raise_for_status()

data = response.json()

for bar in data["bars"]:
    print(
        bar["t"],
        bar["c"],   # close
        bar["v"]    # volume
    )



url = "https://paper-api.alpaca.markets/v2/assets"
headers = {
    "accept": "application/json",
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
    "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET_KEY"],
}
params = {
    "status": "active",
    "asset_class": "us_equity"
}

response = requests.get(
    url,
    headers=headers,
    params=params
)

response.raise_for_status()

assets = response.json()

symbols = [
    x["symbol"]
    for x in assets
    if x["tradable"]
]

print(len(symbols))
print(symbols[:20])




from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass

trading_client = TradingClient(
    os.environ["APCA_API_KEY_ID"],
    os.environ["APCA_API_SECRET_KEY"]
)

search_params = GetAssetsRequest(
    asset_class=AssetClass.US_EQUITY
)

assets = trading_client.get_all_assets(search_params)

for asset in assets[:20]:
    print(asset.symbol, asset.name)