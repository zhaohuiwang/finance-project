from enum import Enum
from src.schwab_trader.accounts.enum import OrderType, Session, Duration

# Dictionary specification for equity orders.


def buy_market_dict(
    symbol: str,
    quantity: int,
    duration: Enum = Duration.DAY,
) -> dict:
    """
    Example:
    buy_market_dict("AAPL", 10, Duration.FILL_OR_KILL)

    """
    return {
        "orderType": "MARKET",
        "session": "NORMAL",
        "duration": duration.value,
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


def sell_market_dict(
    symbol: str,
    quantity: int,
    duration: Enum = Duration.DAY,
) -> dict:
    return {
        "orderType": "MARKET",
        "session": "NORMAL",
        "duration": duration.value,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,
                "instrument": {
                    "symbol": symbol.upper(),
                    "assetType": "EQUITY",
                },
            }
        ],
    }


def buy_limit_dict(
    symbol: str,
    quantity: int,
    limit_price: float,
    duration: Enum = Duration.DAY,
) -> dict:
    return {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": duration.value,
        "orderStrategyType": "SINGLE",
        "price": str(limit_price),
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


def sell_limit_dict(
    symbol: str,
    quantity: int,
    limit_price: float,
    duration: Enum = Duration.DAY,
) -> dict:
    return {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": duration.value,
        "orderStrategyType": "SINGLE",
        "price": str(limit_price),
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,
                "instrument": {
                    "symbol": symbol.upper(),
                    "assetType": "EQUITY",
                },
            }
        ],
    }


def buy_limit_trigger_sell_limit_dict(
    symbol: str,
    quantity: int,
    buy_limit_price: float,
    sell_limit_price: float,
    buy_duration: Enum = Duration.DAY,
    sell_duration: Enum = Duration.DAY,
) -> dict:
    """
    Conditional Order: One Triggers Another
    Buy 10 shares of XYZ at a Limit price of $34.97 good for the Day. If filled, immediately submit an order to Sell 10 shares of XYZ with a Limit price of $42.03 good for the Day. Also known as 1st Trigger Sequence.
    a.k.a. 1st Trigger Sequence.
    """
    return {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "price": str(buy_limit_price),  # "34.97"
        "duration": buy_duration.value,
        "orderStrategyType": "TRIGGER",
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": quantity,
                "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
            }
        ],
        "childOrderStrategies": [
            {
                "orderType": "LIMIT",
                "session": "NORMAL",
                "price": str(sell_limit_price),  # "42.03"
                "duration": sell_duration.value,
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": "SELL",
                        "quantity": quantity,
                        "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
                    }
                ],
            }
        ],
    }


def sell_limit_sell_stoplimit_oco_dict(
    symbol: str,
    quantity: int,
    sell_limit_price: float,
    sell_stop_price: float,
    sell_stoplimit_price: float,
    duration: Enum = Duration.DAY,
) -> dict:
    """
    Conditional Order: One Cancels Another
    Sell 2 shares of XYZ at a Limit price of $45.97 and Sell 2 shares of XYZ with a Stop Limit order where the stop price is $37.03 and limit is $37.00. Both orders are sent at the same time. If one order fills, the other order is immediately cancelled. Both orders are good for the Day. Also known as an OCO order.
    """
    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [
            {
                "orderType": "LIMIT",
                "session": "NORMAL",
                "price": str(sell_limit_price),  # "45.97"
                "duration": duration.value,
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": "SELL",
                        "quantity": quantity,
                        "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
                    }
                ],
            },
            {
                "orderType": "STOP_LIMIT",
                "session": "NORMAL",
                "price": str(sell_stoplimit_price),  # "37.00"
                "stopPrice": str(sell_stop_price),  # "37.03"
                "duration": duration.value,
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": "SELL",
                        "quantity": quantity,
                        "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
                    }
                ],
            },
        ],
    }


def buy_limit_trigger_sell_limit_sell_stop_oco_dict(
    symbol: str,
    quantity: int,
    buy_limit_price: float,
    sell_limit_price: float,
    sell_stop_price: float,
    buy_duration: Enum = Duration.DAY,
    sell_duration: Enum = Duration.GOOD_TILL_CANCEL,
) -> dict:
    """
    Conditional Order: One Triggers A One Cancels Another
    Buy 5 shares of XYZ at a Limit price of $14.97 good for the Day. Once filled, 2 sell orders are immediately sent: Sell 5 shares of XYZ at a Limit price of $15.27 and Sell 5 shares of XYZ with a Stop order where the stop price is $11.27. If one of the sell orders fill, the other order is immediately cancelled. Both Sell orders are Good till Cancel. Also known as a 1st Trigger OCO order.

    """

    return {
        "orderStrategyType": "TRIGGER",
        "session": "NORMAL",
        "duration": buy_duration.value,
        "orderType": "LIMIT",
        "price": str(buy_limit_price),  # "14.97"
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": quantity,
                "instrument": {"assetType": "EQUITY", "symbol": symbol.upper()},
            }
        ],
        "childOrderStrategies": [
            {
                "orderStrategyType": "OCO",
                "childOrderStrategies": [
                    {
                        "orderStrategyType": "SINGLE",
                        "session": "NORMAL",
                        "duration": sell_duration.value,
                        "orderType": "LIMIT",
                        "price": str(sell_limit_price),  # "15.27"
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity": quantity,
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "symbol": symbol.upper(),
                                },
                            }
                        ],
                    },
                    {
                        "orderStrategyType": "SINGLE",
                        "session": "NORMAL",
                        "duration": sell_duration.value,
                        "orderType": "STOP",
                        "stopPrice": str(sell_stop_price),  # "11.27"
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity": quantity,
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "symbol": symbol.upper(),
                                },
                            }
                        ],
                    },
                ],
            }
        ],
    }


def sell_trailing_stop_dict(
    symbol: str,
    quantity: int,
    stop_price_offset: float,
    duration: Enum = Duration.DAY,
) -> dict:
    """
    Sell Trailing Stop: Stock
    Sell 10 shares of XYZ with a Trailing Stop where the trail is a -$10 offset from the time the order is submitted. As the stock price goes up, the -$10 trailing offset will follow. If stock XYZ goes from $110 to $130, your trail will automatically be adjusted to $120. If XYZ falls to $120 or below, a Market order is submitted. This order is good for the Day.

    """
    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "session": "NORMAL",
        "stopPriceLinkBasis": "BID",
        "stopPriceLinkType": "VALUE",
        "stopPriceOffset": stop_price_offset,  # 10
        "duration": duration.value,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,  # 10
                "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
            }
        ],
    }
