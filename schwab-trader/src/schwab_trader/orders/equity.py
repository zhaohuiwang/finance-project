from enum import Enum
from schwab_trader.accounts.type_literal import (
    OrderType,
    stopPriceLinkBasis,
    stopPriceLinkType,
    Session,
    Duration,
)

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
    instrument = {"symbol": symbol.upper(), "assetType": "EQUITY"}
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
                "instrument": instrument,
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
                        "instrument": instrument,
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
    instrument = {"symbol": symbol.upper(), "assetType": "EQUITY"}

    limit_leg = {
        "orderType": "LIMIT",
        "session": session_sell_limit,
        "price": str(sell_limit_price),  # "45.97"
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,
                "instrument": instrument,
            }
        ],
    }
    stop_limit_leg = {
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
                "instrument": instrument,
            }
        ],
    }

    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [limit_leg, stop_limit_leg],
    }


def sell_trailing_sell_limit_oco_dict(
    symbol: str,
    quantity: int,
    sell_limit_price: float,
    stop_price_offset: float,
    stop_price_link_type: stopPriceLinkType = "PERCENT",
    session: str = "NORMAL",
    duration: str = "DAY",
) -> dict:
    """
    Build a Schwab OCO sell order with a trailing-stop and limit-sell leg.

    The returned order contains two SELL child orders:

    1. LIMIT SELL:
       Sells the specified quantity when the market reaches the
       specified `sell_limit_price`.

    2. TRAILING STOP SELL:
       Sells the specified quantity when the trailing stop is triggered.
       The trailing stop is linked to the LAST traded price and uses
       `stop_price_offset` according to `stop_price_link_type`.
      

    For a 2% trailing stop, the basic relationship is:
    Trailing Stop Price=Highest Reference Pricex(1-0.02) where the Highest Reference Price is the highest qualifying LAST price reached since the trailing order became active.

    Because the two orders are combined as an OCO (One-Cancels-the-Other),
    execution of one child order causes the other child order to be
    canceled.

    Args:
        symbol: Stock ticker symbol, e.g. "AAPL".
        quantity: Number of shares to sell.
        sell_limit_price: Limit price for the take-profit SELL order.
        stop_price_offset: Trailing-stop offset. Its meaning depends on
            `stop_price_link_type`; for example, 2 with "PERCENT" means
            a 2% trailing offset.
        stop_price_link_type: Type of trailing-stop offset, such as
            "PERCENT" or another value supported by Schwab.
        session: Trading session for the child orders. Defaults to
            "NORMAL".
        duration: Order duration for the child orders. Defaults to "DAY".

    Returns:
        A dictionary formatted for use as a Schwab API OCO order.

    Example:
        >>> order = sell_trailing_sell_limit_oco_dict(
        ...     symbol="AAPL",
        ...     quantity=100,
        ...     sell_limit_price=250.00,
        ...     stop_price_offset=2.0,
        ...     stop_price_link_type="PERCENT",
        ... )
        >>>
        >>> response = client.place_order(hash_value, order)

    The example creates an OCO order that attempts to:
        - Sell 100 AAPL shares at a $250.00 limit price, OR
        - Sell 100 AAPL shares using a 2% trailing stop.

    Whichever SELL order executes first causes the other OCO leg
    to be canceled.
    """

    instrument = {"symbol": symbol, "assetType": "EQUITY"}

    limit_leg = {
        "orderType": "LIMIT",
        "session": session,
        "duration": duration,
        "price": str(sell_limit_price),
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {"instruction": "SELL", "quantity": quantity, "instrument": instrument}
        ],
    }

    trailing_leg = {
        "orderType": "TRAILING_STOP",
        "session": session,
        "duration": duration,
        "stopPriceLinkBasis": "LAST",
        "stopPriceLinkType": stop_price_link_type,
        "stopPriceOffset": stop_price_offset,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {"instruction": "SELL", "quantity": quantity, "instrument": instrument}
        ],
    }

    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [limit_leg, trailing_leg],
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
    instrument = {"assetType": "EQUITY", "symbol": symbol.upper()}
    sell_limit_leg = {
        "orderStrategyType": "SINGLE",
        "session": session_sell_limit,
        "duration": sell_duration,
        "orderType": "LIMIT",
        "price": str(sell_limit_price),  # "15.27"
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,
                "instrument": instrument,
            }
        ],
    }
    sell_stop_leg = {
        "orderStrategyType": "SINGLE",
        "session": session_sell_stop,
        "duration": sell_duration,
        "orderType": "STOP",
        "stopPrice": str(sell_stop_price),  # "11.27"
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,
                "instrument": instrument,
            }
        ],
    }

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
                "instrument": instrument,
            }
        ],
        "childOrderStrategies": [
            {
                "orderStrategyType": "OCO",
                "childOrderStrategies": [sell_limit_leg, sell_stop_leg],
            }
        ],
    }


def buy_trailing_stop_dict(
    symbol: str,
    quantity: int,
    stop_price_link_basis: stopPriceLinkBasis = "BID",
    stop_price_link_type: stopPriceLinkType = "PERCENT",  # "VALUE" or "PERCENT" or "TICK"
    stop_price_offset: float = 2.0,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    """
    Create a BUY trailing stop order for an equity position.

    A trailing stop buy order is typically used to enter a long position only
    after price begins moving upward from a lower level. The stop trigger price
    automatically trails the market by a fixed offset.

    Trailing behavior:
    - The stop price follows the market downward by the specified offset.
    - If the market reverses upward by the offset amount, the trailing stop
      triggers and submits a market buy order.
    - The stop price never moves higher while the market is falling.

    Example:
        Current price: $110
        Trailing offset: 10 points (VALUE)

        If the stock drops from $110 to $100:
            trailing stop adjusts down to $110

        If the stock later rises back to $110:
            the order triggers and submits a market BUY order.

    Percent example:
        With stop_price_link_type="PERCENT" and stop_price_offset=2.0,
        the stop price trails the market by 2%.

    Args:
        symbol:
            Stock ticker symbol.

        quantity:
            Number of shares to purchase.

        stop_price_link_basis:
            Reference price used for trailing calculations.
            Common values include:
            - "BID"
            - "ASK"
            - "LAST"
            - "MARK"

        stop_price_link_type:
            Type of trailing offset:
            - "VALUE"   -> dollar amount
            - "PERCENT" -> percentage
            - "TICK"    -> tick increment

        stop_price_offset:
            Trailing offset amount based on stop_price_link_type.

        session:
            Trading session for the order.
            Typically "NORMAL".

        duration:
            Order duration.
            Common values:
            - "DAY"
            - "GOOD_TILL_CANCEL"

    Returns:
        dict:
            Schwab API trailing stop BUY order payload.
    """

    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "session": session,
        "stopPriceLinkBasis": stop_price_link_basis,
        "stopPriceLinkType": stop_price_link_type,
        "stopPriceOffset": stop_price_offset,  # 10
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": quantity,  # 10
                "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
            }
        ],
    }


def sell_trailing_stop_dict(
    symbol: str,
    quantity: int,
    stop_price_link_basis: stopPriceLinkBasis = "BID",
    stop_price_link_type: stopPriceLinkType = "PERCENT",  # "VALUE" or "PERCENT" or "TICK"
    stop_price_offset: float = 2.0,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    """
    Create a SELL trailing stop order for an equity position.

    A trailing stop sell order is commonly used to protect profits or limit
    downside risk on an existing long position. The stop trigger price
    automatically trails the market as price increases.

    Trailing behavior:
    - The stop price follows the market upward by the specified offset.
    - If the market reverses downward by the offset amount, the trailing stop
      triggers and submits a market sell order.
    - The stop price never moves lower while the market is rising.

    Example:
        Current price: $110
        Trailing offset: 10 points (VALUE)

        If the stock rises from $110 to $130:
            trailing stop adjusts up to $120

        If the stock later falls to $120:
            the order triggers and submits a market SELL order.

    Percent example:
        With stop_price_link_type="PERCENT" and stop_price_offset=2.0,
        the stop price trails the market by 2%.

    Args:
        symbol:
            Stock ticker symbol.

        quantity:
            Number of shares to sell.

        stop_price_link_basis:
            Reference price used for trailing calculations.
            Common values include:
            - "BID"
            - "ASK"
            - "LAST"
            - "MARK"

        stop_price_link_type:
            Type of trailing offset:
            - "VALUE"   -> dollar amount
            - "PERCENT" -> percentage
            - "TICK"    -> tick increment

        stop_price_offset:
            Trailing offset amount based on stop_price_link_type.

        session:
            Trading session for the order.
            Typically "NORMAL".

        duration:
            Order duration.
            Common values:
            - "DAY"
            - "GOOD_TILL_CANCEL"

    Returns:
        dict:
            Schwab API trailing stop SELL order payload.
    """

    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "session": session,
        "stopPriceLinkBasis": stop_price_link_basis,
        "stopPriceLinkType": stop_price_link_type,
        "stopPriceOffset": stop_price_offset,  # 10
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": quantity,  # 10
                "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
            }
        ],
    }


def buy_trailingstop_trigger_sell_trailingstop_dict(
    symbol: str,
    quantity_buy: int,
    quantity_sell: int,
    stop_price_link_basis_buy: stopPriceLinkBasis = "MARK",
    stop_price_link_type_buy: stopPriceLinkType = "PERCENT",  # "VALUE" or "PERCENT" or "TICK"
    stop_price_offset_buy: float = 2.0,
    session_buy: Session = "NORMAL",
    buy_duration: Duration = "DAY",  # "GOOD_TILL_CANCEL", "END_OF_WEEK", "END_OF_MONTH", ...
    stop_price_link_basis_sell: stopPriceLinkBasis = "MARK",
    stop_price_link_type_sell: stopPriceLinkType = "PERCENT",
    stop_price_offset_sell: float = 2.0,
    session_sell: Session = "NORMAL",
    sell_duration: Duration = "DAY",
) -> dict:
    """ """
    return {
        "orderType": "TRAILING_STOP",
        "session": session_buy,
        "duration": buy_duration,
        "quantity": quantity_buy,
        "complexOrderStrategyType": "NONE",
        "orderStrategyType": "TRIGGER",
        "stopPriceLinkBasis": stop_price_link_basis_buy,
        "stopPriceLinkType": stop_price_link_type_buy,
        "stopPriceOffset": stop_price_offset_buy,
        "stopType": "MARK",
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "instruction": "BUY",
                "quantity": quantity_buy,
                "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
            }
        ],
        "childOrderStrategies": [
            {
                "orderType": "TRAILING_STOP",
                "session": session_sell,
                "duration": sell_duration,
                "quantity": quantity_sell,
                "complexOrderStrategyType": "NONE",
                "orderStrategyType": "SINGLE",
                "stopPriceLinkBasis": stop_price_link_basis_sell,
                "stopPriceLinkType": stop_price_link_type_sell,
                "stopPriceOffset": stop_price_offset_sell,
                "stopType": "MARK",
                "orderLegCollection": [
                    {
                        "orderLegType": "EQUITY",
                        "instruction": "SELL",
                        "quantity": quantity_sell,
                        "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
                    }
                ],
            }
        ],
    }


def sell_trailingstop_trigger_buy_trailingstop_dict(
    symbol: str,
    quantity_sell: int,
    quantity_buy: int,
    stop_price_link_basis_sell: stopPriceLinkBasis = "MARK",
    stop_price_link_type_sell: stopPriceLinkType = "PERCENT",  # "VALUE" or "PERCENT" or "TICK"
    stop_price_offset_sell: float = 2.0,
    session_sell: Session = "NORMAL",
    sell_duration: Duration = "DAY",  # "GOOD_TILL_CANCEL", "END_OF_WEEK", "END_OF_MONTH", ...
    stop_price_link_basis_buy: stopPriceLinkBasis = "MARK",
    stop_price_link_type_buy: stopPriceLinkType = "PERCENT",
    stop_price_offset_buy: float = 2.0,
    session_buy: Session = "NORMAL",
    buy_duration: Duration = "DAY",
) -> dict:
    """ """
    return {
        "orderType": "TRAILING_STOP",
        "session": session_sell,
        "duration": sell_duration,
        "quantity": quantity_sell,
        "complexOrderStrategyType": "NONE",
        "orderStrategyType": "TRIGGER",
        "stopPriceLinkBasis": stop_price_link_basis_sell,
        "stopPriceLinkType": stop_price_link_type_sell,
        "stopPriceOffset": stop_price_offset_sell,
        "stopType": "MARK",
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "instruction": "SELL",
                "quantity": quantity_sell,
                "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
            }
        ],
        "childOrderStrategies": [
            {
                "orderType": "TRAILING_STOP",
                "session": session_buy,
                "duration": buy_duration,
                "quantity": quantity_buy,
                "complexOrderStrategyType": "NONE",
                "orderStrategyType": "SINGLE",
                "stopPriceLinkBasis": stop_price_link_basis_buy,
                "stopPriceLinkType": stop_price_link_type_buy,
                "stopPriceOffset": stop_price_offset_buy,
                "stopType": "MARK",
                "orderLegCollection": [
                    {
                        "orderLegType": "EQUITY",
                        "instruction": "BUY",
                        "quantity": quantity_buy,
                        "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
                    }
                ],
            }
        ],
    }
