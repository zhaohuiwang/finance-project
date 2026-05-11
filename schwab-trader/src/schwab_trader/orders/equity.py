from enum import Enum
from schwab_trader.accounts.type_literal import OrderType, StopPriceLinkType, Session, Duration

# Dictionary specification for equity orders.
# Note: Prices must be string in the JSON for precision


def buy_market_dict(
    symbol: str,
    quantity: int,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    """
    Example:
    buy_market_dict("AAPL", 10, Duration.FILL_OR_KILL)

    """
    return {
        "orderType": "MARKET",
        "session": session,
        "duration": duration,
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
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    return {
        "orderType": "MARKET",
        "session": session,
        "duration": duration,
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
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    return {
        "orderType": "LIMIT",
        "session": session,
        "duration": duration,
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
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    return {
        "orderType": "LIMIT",
        "session": session,
        "duration": duration,
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
    session_buy: Session = "NORMAL",
    session_sell: Session = "NORMAL",
    buy_duration: Duration = "DAY",
    sell_duration: Duration = "DAY",
) -> dict:
    """
    Conditional Order: One Triggers Another
    Buy 10 shares of XYZ at a Limit price of $34.97 good for the Day. If filled, immediately submit an order to Sell 10 shares of XYZ with a Limit price of $42.03 good for the Day. Also known as 1st Trigger Sequence.
    a.k.a. 1st Trigger Sequence.
    """
    return {
        "orderType": "LIMIT",
        "session": session_buy,
        "price": str(buy_limit_price),  # "34.97"
        "duration": buy_duration,
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
                "session": session_sell,
                "price": str(sell_limit_price),  # "42.03"
                "duration": sell_duration,
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
    session_sell_limit: Session = "NORMAL",
    session_sell_stoplimit: Session = "NORMAL",
    duration: Duration = "DAY",
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
                "session": session_sell_limit,
                "price": str(sell_limit_price),  # "45.97"
                "duration": duration,
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
                "session": session_sell_stoplimit,
                "price": str(sell_stoplimit_price),  # "37.00"
                "stopPrice": str(sell_stop_price),  # "37.03"
                "duration": duration,
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
    session_buy_limit: Session = "NORMAL",
    session_sell_limit: Session = "NORMAL",
    session_sell_stop: Session = "NORMAL",
    buy_duration: Duration = "DAY",
    sell_duration: Duration = "GOOD_TILL_CANCEL",
) -> dict:
    """
    Conditional Order: One Triggers A One Cancels Another
    Buy 5 shares of XYZ at a Limit price of $14.97 good for the Day. Once filled, 2 sell orders are immediately sent: Sell 5 shares of XYZ at a Limit price of $15.27 and Sell 5 shares of XYZ with a Stop order where the stop price is $11.27. If one of the sell orders fill, the other order is immediately cancelled. Both Sell orders are Good till Cancel. Also known as a 1st Trigger OCO order.

    """

    return {
        "orderStrategyType": "TRIGGER",
        "session": session_buy_limit,
        "duration": buy_duration,
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
                        "session": session_sell_limit,
                        "duration": sell_duration,
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
                        "session": session_sell_stop,
                        "duration": sell_duration,
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
    stop_price_link_type: StopPriceLinkType = "PERCENTAGE",
    stop_price_offset: float=5,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    """
    Build a Schwab API payload for an equity trailing stop sell order. A trailing stop order dynamically adjusts its stop trigger as the stock
    price moves upward. The trailing offset is defined by
    `stop_price_offset` and interpreted according to
    `stop_price_link_type`.

    Example behavior:
        If XYZ is trading at $110 with a trailing offset of $10:
        - Initial stop trigger = $100
        - If XYZ rises to $130, the stop trigger adjusts to $120
        - If XYZ later falls to $120 or below, a market sell order is sent

    This function creates only the order payload dictionary and does not
    submit the order to Schwab.

    Args:
        symbol (str):
            Equity ticker symbol (e.g. "AAPL", "SPY").
            The symbol is automatically converted to uppercase.

        quantity (int):
            Number of shares to sell.

        stop_price_link_type (StopPriceLinkType, optional):
            Method used to calculate the trailing offset.
            Common values include: ["VALUE", "PERCENT"]
            Defaults to "PERCENT".

        stop_price_offset (float, optional):
            Trailing offset amount used with
            `stop_price_link_type`.

            Examples:
            - VALUE + 5       -> $5 trailing offset
            - PERCENTAGE + 5  -> 5% trailing offset
            Defaults to 5.

        session (Session, optional):
            Trading session in which the order is active.
            Common values: ["NORMAL", "AM", "PM", "SEAMLESS"]
            Defaults to "NORMAL".

        duration (Duration, optional):
            Length of time the order remains active.
            Common values: ["DAY", "GOOD_TILL_CANCEL"]
            Defaults to "DAY".

    Returns:
        dict:
            Schwab-compatible order payload for a trailing stop
            market sell order.

    Example:
        >>> order = sell_trailing_stop_dict(
        ...     symbol="AAPL",
        ...     quantity=10,
        ...     stop_price_link_type="VALUE",
        ...     stop_price_offset=5,
        ... )
        >>> client.order_place(account_hash, order)

    Notes:
        - Uses "BID" as the stop price link basis.
        - The order type generated is "TRAILING_STOP".
        - When triggered, Schwab submits a market order.
        - Trailing stop orders may execute below the expected stop level
          during fast-moving or illiquid market conditions.
    """
    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "session": session,
        "stopPriceLinkBasis": "BID",
        "stopPriceLinkType": stop_price_link_type,
        "stopPriceOffset": stop_price_offset,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,
                "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
            }
        ],
    }