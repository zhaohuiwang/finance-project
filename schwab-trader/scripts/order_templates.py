# https://tylerebowers.github.io/Schwabdev/?source=pages%2Forders.html
"""
from https://developer.schwab.com/products/trader-api--individual/details/specifications/Retail%20Trader%20API%20Production

orderType string Enum:
    [ MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP, CABINET, NON_MARKETABLE, MARKET_ON_CLOSE, EXERCISE, TRAILING_STOP_LIMIT, NET_DEBIT, NET_CREDIT, NET_ZERO, LIMIT_ON_CLOSE, UNKNOWN ]
session string Enum:
    [ NORMAL, AM, PM, SEAMLESS ]
duration string Enum:
    [ DAY, GOOD_TILL_CANCEL, FILL_OR_KILL, IMMEDIATE_OR_CANCEL, END_OF_WEEK, END_OF_MONTH, NEXT_END_OF_MONTH, UNKNOWN ]
orderStrategyType string Enum:
    [ SINGLE, CANCEL, RECALL, PAIR, FLATTEN, TWO_DAY_SWAP, BLAST_ALL, OCO, TRIGGER ]
OrderLegCollection
    instruction string Enum:
        [ BUY, SELL, BUY_TO_COVER, SELL_SHORT, BUY_TO_OPEN, BUY_TO_CLOSE, SELL_TO_OPEN, SELL_TO_CLOSE, EXCHANGE, SELL_SHORT_EXEMPT ]
    quantity	number($double)
    instrument
        symbol string
        assetType string Enum:
            [ EQUITY, OPTION, INDEX, MUTUAL_FUND, CASH_EQUIVALENT, FIXED_INCOME, CURRENCY, COLLECTIVE_INVESTMENT ]
complexOrderStrategyType string Enum:
    [ NONE, COVERED, VERTICAL, BACK_RATIO, CALENDAR, DIAGONAL, STRADDLE, STRANGLE, COLLAR_SYNTHETIC, BUTTERFLY, CONDOR, IRON_CONDOR, VERTICAL_ROLL, COLLAR_WITH_STOCK, DOUBLE_DIAGONAL, UNBALANCED_BUTTERFLY, UNBALANCED_CONDOR, UNBALANCED_IRON_CONDOR, UNBALANCED_VERTICAL_ROLL, MUTUAL_FUND_SWAP, CUSTOM ]


status string Enum:
[ AWAITING_PARENT_ORDER, AWAITING_CONDITION, AWAITING_STOP_CONDITION, AWAITING_MANUAL_REVIEW, ACCEPTED, AWAITING_UR_OUT, PENDING_ACTIVATION, QUEUED, WORKING, REJECTED, PENDING_CANCEL, CANCELED, PENDING_REPLACE, REPLACED, FILLED, EXPIRED, NEW, AWAITING_RELEASE_TIME, PENDING_ACKNOWLEDGEMENT, PENDING_RECALL, UNKNOWN ]


If an order format is not shown here, place an order from a different platform (e.g. TOS) and use client.order_details(...) to infer the format.

"""

accountHash = "5050E677CA3B9139950404F8253F841A99BCA9528AB8CDC11684488239FA145B"


# Buy 10 shares of AMD at market price
quantity = 10
symbol = "AMD"


def create_buy_market_order(symbol: str, quantity: int) -> dict:
    return {
        "orderType": "MARKET",
        "session": "NORMAL",
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": quantity,
                "instrument": {
                    "symbol": symbol.upper(),
                    "assetType": "EQUITY",
                },
            }
        ],
    }


# Buy 4 shares of INTC at limit price $10.00
order = {
    "orderType": "LIMIT",
    "session": "NORMAL",
    "duration": "DAY",
    "orderStrategyType": "SINGLE",
    "price": "10.00",
    "orderLegCollection": [
        {
            "instruction": "BUY",
            "quantity": 4,
            "instrument": {
                "symbol": "INTC",
                "assetType": "EQUITY",
            },
        }
    ],
}


# Sell 3 options
# Symbol format: Underlying Symbol (6 chars including spaces) + Expiration (YYMMDD, 6 chars) + Call/Put (1 char) + Strike Price (5+3 = 8 chars)

order = {
    "orderType": "LIMIT",
    "session": "NORMAL",
    "price": 1.0,
    "duration": "GOOD_TILL_CANCEL",
    "orderStrategyType": "SINGLE",
    "complexOrderStrategyType": "NONE",
    "orderLegCollection": [
        {
            "instruction": "SELL_TO_OPEN",
            "quantity": 3,
            "instrument": {
                "symbol": "AAPL  240517P00190000",
                "assetType": "OPTION",
            },
        }
    ],
}


# Buy 3 options
# Symbol format: Underlying Symbol (6 chars including spaces) + Expiration (YYMMDD, 6 chars) + Call/Put (1 char) + Strike Price (5+3 = 8 chars)

order = {
    "orderType": "LIMIT",
    "session": "NORMAL",
    "price": 0.1,
    "duration": "GOOD_TILL_CANCEL",
    "orderStrategyType": "SINGLE",
    "complexOrderStrategyType": "NONE",
    "orderLegCollection": [
        {
            "instruction": "BUY_TO_OPEN",
            "quantity": 3,
            "instrument": {
                "symbol": "AAPL  240517P00190000",
                "assetType": "OPTION",
            },
        }
    ],
}


# Buy limited vertical put spread
order = {
    "orderType": "NET_DEBIT",
    "session": "NORMAL",
    "price": "0.10",
    "duration": "DAY",
    "orderStrategyType": "SINGLE",
    "orderLegCollection": [
        {
            "instruction": "BUY_TO_OPEN",
            "quantity": 2,
            "instrument": {
                "symbol": "XYZ   240315P00045000",
                "assetType": "OPTION",
            },
        },
        {
            "instruction": "SELL_TO_OPEN",
            "quantity": 2,
            "instrument": {
                "symbol": "XYZ   240315P00043000",
                "assetType": "OPTION",
            },
        },
    ],
}


# Conditional Order: If 10 shares XYZ filled, then sell 10 shares ABC
order = {
    "orderType": "LIMIT",
    "session": "NORMAL",
    "price": "34.97",
    "duration": "DAY",
    "orderStrategyType": "TRIGGER",
    "orderLegCollection": [
        {
            "instruction": "BUY",
            "quantity": 10,
            "instrument": {
                "symbol": "XYZ",
                "assetType": "EQUITY",
            },
        }
    ],
    "childOrderStrategies": [
        {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "price": "42.03",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 10,
                    "instrument": {
                        "symbol": "ABC",
                        "assetType": "EQUITY",
                    },
                }
            ],
        }
    ],
}

# Conditional Order (OCO): If 2 shares XYZ filled, then cancel sell 2 shares ABC
order = {
    "orderStrategyType": "OCO",
    "childOrderStrategies": [
        {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "price": "45.97",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 2,
                    "instrument": {
                        "symbol": "XYZ",
                        "assetType": "EQUITY",
                    },
                }
            ],
        },
        {
            "orderType": "STOP_LIMIT",
            "session": "NORMAL",
            "price": "37.00",
            "stopPrice": "37.03",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 2,
                    "instrument": {
                        "symbol": "ABC",
                        "assetType": "EQUITY",
                    },
                }
            ],
        },
    ],
}


# Conditional Order: If 5 shares XYZ filled, then sell 5 shares ABC and 5 shares IJK
order = {
    "orderStrategyType": "TRIGGER",
    "session": "NORMAL",
    "duration": "DAY",
    "orderType": "LIMIT",
    "price": 14.97,
    "orderLegCollection": [
        {
            "instruction": "BUY",
            "quantity": 5,
            "instrument": {
                "assetType": "EQUITY",
                "symbol": "XYZ",
            },
        }
    ],
    "childOrderStrategies": [
        {
            "orderStrategyType": "OCO",
            "childOrderStrategies": [
                {
                    "orderStrategyType": "SINGLE",
                    "session": "NORMAL",
                    "duration": "GOOD_TILL_CANCEL",
                    "orderType": "LIMIT",
                    "price": 15.27,
                    "orderLegCollection": [
                        {
                            "instruction": "SELL",
                            "quantity": 5,
                            "instrument": {
                                "assetType": "EQUITY",
                                "symbol": "ABC",
                            },
                        }
                    ],
                },
                {
                    "orderStrategyType": "SINGLE",
                    "session": "NORMAL",
                    "duration": "GOOD_TILL_CANCEL",
                    "orderType": "STOP",
                    "stopPrice": 11.27,
                    "orderLegCollection": [
                        {
                            "instruction": "SELL",
                            "quantity": 5,
                            "instrument": {
                                "assetType": "EQUITY",
                                "symbol": "IJK",
                            },
                        }
                    ],
                },
            ],
        }
    ],
}

"""
stopPriceLinkType string Enum:
    [ VALUE, PERCENT, TICK ]
stopPriceLinkBasis string Enum:
    [ MANUAL, BASE, TRIGGER, LAST, BID, ASK, ASK_BID, MARK, AVERAGE ]
stopPriceOffset number($double) 
"""

# Sell Trailing Stop: 10 shares XYZ with a trailing stop offset of 10
order = {
    "complexOrderStrategyType": "NONE",
    "orderType": "TRAILING_STOP",
    "session": "NORMAL",
    "stopPriceLinkBasis": "BID",
    "stopPriceLinkType": "VALUE",
    "stopPriceOffset": 10,
    "duration": "DAY",
    "orderStrategyType": "SINGLE",
    "orderLegCollection": [
        {
            "instruction": "SELL",
            "quantity": 10,
            "instrument": {
                "symbol": "XYZ",
                "assetType": "EQUITY",
            },
        }
    ],
}

# Iron Condor
order = {
    "orderStrategyType": "SINGLE",
    "orderType": "NET_CREDIT",
    "price": price,
    "orderLegCollection": [
        {
            "instruction": "SELL_TO_OPEN",
            "quantity": quantity,
            "instrument": {
                "assetType": "OPTION",
                "symbol": short_call_symbol,
            },
        },
        {
            "instruction": "BUY_TO_OPEN",
            "quantity": quantity,
            "instrument": {
                "assetType": "OPTION",
                "symbol": long_call_symbol,
            },
        },
        {
            "instruction": "SELL_TO_OPEN",
            "quantity": quantity,
            "instrument": {
                "assetType": "OPTION",
                "symbol": short_put_symbol,
            },
        },
        {
            "instruction": "BUY_TO_OPEN",
            "quantity": quantity,
            "instrument": {
                "assetType": "OPTION",
                "symbol": long_put_symbol,
            },
        },
    ],
    "complexOrderStrategyType": "CUSTOM",
    "duration": "DAY",
    "session": "NORMAL",
}
