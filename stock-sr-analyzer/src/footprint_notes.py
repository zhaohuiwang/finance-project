"""
Footprint charts & tick data — what this project can and cannot do.

True footprint / order-flow charts need:
  - Tick trades with aggressor side (buy vs sell), OR
  - Bid/ask volume at price (DOM / L2 snapshots)

Yahoo Finance OHLCV (used by this project) does NOT provide that.
This module documents the data contract and points users to external sources.
"""

FOOTPRINT_DATA_CONTRACT = """
Required for real footprint charts
---------------------------------
Per trade (tick):
  - timestamp
  - price
  - size (volume)
  - side / aggressor (buy = lift ask, sell = hit bid)   [critical]

Optional:
  - bid/ask at time of trade
  - order-book depth snapshots

Typical sources (examples, not endorsements)
--------------------------------------------
  Equities / US stocks:
    - Polygon, Databento, Intrinio, professional broker APIs
  Futures:
    - CQG, Rithmic, Databento, exchange direct
  Crypto:
    - Exchange WebSocket trades (Binance, Bybit, etc.) via ccxt or native WS

What this project does instead
------------------------------
  - Volume Profile from OHLCV (POC, VA)
  - Delta / CVD proxies (close vs open volume split)
  - Absorption & imbalance proxies
  - VWAP (cumulative, rolling, anchored)

These are useful filters on daily/swing horizons but are NOT footprint charts.
"""


def print_footprint_requirements() -> None:
    print(FOOTPRINT_DATA_CONTRACT)


def footprint_status() -> dict:
    return {
        "supported_in_project": False,
        "reason": "No tick/aggressor data from yfinance OHLCV",
        "proxies_available": [
            "volume_profile_poc_va",
            "delta_cvd_proxy",
            "absorption_proxy",
            "swing_imbalance_proxy",
            "vwap_variants",
        ],
        "data_needed": ["tick trades with side", "or bid/ask volume at price"],
    }
