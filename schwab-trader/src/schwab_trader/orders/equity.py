from enum import Enum
from typing import Any, TypedDict

from schwab_trader.accounts.type_literal import (
    OrderType,
    Instruction,
    StopPriceLinkBasis,
    StopPriceLinkType,
    Session,
    Duration,
    TaxLotMethod,
)

# Dictionary specification for equity orders.
# Note: Prices must be string in the JSON for precision

OrderPayload = dict[str, Any]  # For the returned type

# ---------------------------------------------------------------------------
# Shared validators
# ---------------------------------------------------------------------------


def _validate_symbol_instructions_quantities(symbol: str, **kwargs) -> None:
    """
    Validate symbol, instructions, and quantities.
    Requirement: "instruction" has to be in the instruction specification parameter(s) name and so does "quantity" in the quantity parameter(s).
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must not be empty.")

    for name, value in kwargs.items():
        if "instruction" in name:
            if value not in ("BUY", "SELL"):
                raise ValueError(f"{name.replace('_', ' ')} must be 'BUY' or 'SELL'.")
        elif "quantity" in name:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(
                    f"{name.replace('_', ' ')} must be a positive integer."
                )
        else:
            raise ValueError(f"Unsupported validation field: {name}.")


def _validate_positive_values(**values) -> None:
    """Validate positive finite numeric values."""
    from numbers import Real
    from decimal import Decimal
    import math

    for name, value in values.items():
        is_finite = (
            value.is_finite() if isinstance(value, Decimal) else math.isfinite(value)
        )
        if (
            isinstance(value, bool)
            or not isinstance(value, (Real, Decimal))
            or not is_finite
            or value <= 0
        ):
            raise ValueError(
                f"{name.replace('_', ' ')} must be a positive finite number."
            )


def _validate_positive_percent_values(**values) -> None:
    """Validate percentage values (0 < value < 100)."""
    from numbers import Real
    from decimal import Decimal
    import math

    for name, value in values.items():
        is_finite = (
            value.is_finite() if isinstance(value, Decimal) else math.isfinite(value)
        )
        if (
            isinstance(value, bool)
            or not isinstance(value, (Real, Decimal))
            or not is_finite
            or not 0 < value < 100
        ):
            raise ValueError(
                f"{name.replace('_', ' ')} must be a percentage "
                "greater than 0 and less than 100."
            )


def _validate_trailing_stop(
    stop_price_link_type: StopPriceLinkType,
    stop_price_offset: float,
) -> None:
    """Validate trailing-stop offset and link type."""
    if stop_price_link_type not in ("VALUE", "PERCENT", "TICK"):
        raise ValueError("stop_price_link_type must be 'VALUE', 'PERCENT', or 'TICK'.")
    if stop_price_link_type == "PERCENT":
        _validate_positive_percent_values(stop_price_offset=stop_price_offset)
    else:
        _validate_positive_values(stop_price_offset=stop_price_offset)


def _make_equity_leg(
    symbol: str,
    quantity: int,
    instruction: Instruction,
) -> dict:
    """Common order-leg builder."""
    return {
        "orderLegType": "EQUITY",
        "instruction": instruction,
        "quantity": quantity,
        "instrument": {
            "symbol": symbol.upper(),
            "assetType": "EQUITY",
        },
    }


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def build_market_order_payload(
    symbol: str,
    quantity: int,
    instruction: Instruction,
    session: Session = "NORMAL",
) -> OrderPayload:
    """Market order. Duration is always DAY for market orders."""
    _validate_symbol_instructions_quantities(
        symbol,
        input_instruction=instruction,
        input_quantity=quantity,
    )
    order_leg = _make_equity_leg(symbol, quantity, instruction)
    return {
        "orderType": "MARKET",
        "session": session,
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [order_leg],
    }


def build_limit_order_payload(
    symbol: str,
    quantity: int,
    limit_price: float,
    instruction: Instruction,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    """Simple limit order."""
    _validate_symbol_instructions_quantities(
        symbol,
        input_instruction=instruction,
        input_quantity=quantity,
    )
    _validate_positive_values(input_limit_price=limit_price)

    order_leg = _make_equity_leg(symbol, quantity, instruction)
    return {
        "orderType": "LIMIT",
        "price": str(limit_price),
        "session": session,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [order_leg],
    }


def build_trailing_stop_order_payload(
    symbol: str,
    quantity: int,
    instruction: Instruction,  # "BUY" or "SELL"
    stop_price_link_basis: StopPriceLinkBasis = "BID",
    stop_price_link_type: StopPriceLinkType = "PERCENT",
    stop_price_offset: float = 2.0,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> dict:
    """
    Build a Schwab trailing-stop order payload for an equity position.

    The trailing stop trigger price follows the reference market price
    according to the specified offset. When triggered, the order submits
    a market order.

    Args:
        symbol:
            Stock ticker symbol.

        quantity:
            Number of shares.

        instruction:
            Order instruction: "BUY" or "SELL".

        stop_price_link_basis:
            Reference price used for trailing calculations:
            "BID", "ASK", "LAST", or "MARK".

        stop_price_link_type:
            Trailing offset type:
            "VALUE", "PERCENT", or "TICK".

        stop_price_offset:
            Trailing offset amount.

        session:
            Trading session, typically "NORMAL".

        duration:
            Order duration, typically "DAY".

    Returns:
        dict:
            Schwab API trailing-stop order payload.
    """
    # Validate inputs.
    _validate_symbol_instructions_quantities(
        symbol,
        input_instruction=instruction,
        input_quantity=quantity,
    )

    if stop_price_link_type == "PERCENT":
        _validate_positive_percent_values(input_stop_price_offset=stop_price_offset)
    else:
        _validate_positive_values(input_stop_price_offset=stop_price_offset)

    _validate_trailing_stop(stop_price_link_type, stop_price_offset)

    instrument = {
        "symbol": symbol.upper(),
        "assetType": "EQUITY",
    }
    order_leg = _make_equity_leg(symbol, quantity, instruction)
    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "session": session,
        "stopPriceLinkBasis": stop_price_link_basis,
        "stopPriceLinkType": stop_price_link_type,
        "stopPriceOffset": stop_price_offset,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [order_leg],
    }


def build_oto_limit_order_payload(
    symbol: str,
    quantity: int,
    instructions: tuple[Instruction, Instruction],
    limit_prices: tuple[float, float],
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    durations: tuple[Duration, Duration] = ("DAY", "DAY"),
) -> dict:
    """
    Build a One-Triggers-Other (OTO) limit order.

    Tuple positions:
        [0] Primary order
        [1] Secondary order

    Example:
        Buy 10 shares of XYZ at $34.97.
        When filled, trigger a sell order at $42.03.
    """

    # Validate inputs.
    _validate_symbol_instructions_quantities(
        symbol,
        primary_instruction=instructions[0],
        secondary_instruction=instructions[1],
        quantity=quantity,
    )

    # Validate tuple/list inputs.
    for name, values in (
        ("instructions", instructions),
        ("limit_prices", limit_prices),
        ("sessions", sessions),
        ("durations", durations),
    ):
        if not isinstance(values, (tuple, list)) or len(values) != 2:
            raise ValueError(f"{name} must contain exactly two values.")

    # Validate individual values.
    _validate_positive_values(
        primary_limit_price=limit_prices[0],
        secondary_limit_price=limit_prices[1],
    )

    primary_instruction, secondary_instruction = instructions
    primary_price, secondary_price = limit_prices
    primary_session, secondary_session = sessions
    primary_duration, secondary_duration = durations

    primary_leg = _make_equity_leg(symbol, quantity, primary_instruction)
    secondary_leg = _make_equity_leg(symbol, quantity, secondary_instruction)

    secondary_payload = {
        "orderType": "LIMIT",
        "price": str(secondary_price),
        "session": secondary_session,
        "duration": secondary_duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [secondary_leg],
    }

    return {
        "orderType": "LIMIT",
        "price": str(primary_price),
        "session": primary_session,
        "duration": primary_duration,
        "orderStrategyType": "TRIGGER",
        "orderLegCollection": [primary_leg],
        "childOrderStrategies": [secondary_payload],
    }


def build_sell_limit_stoplimit_oco_payload(
    symbol: str,
    quantity: int,
    # (limit_price, (stop_price, stop_limit_price))
    sell_prices: tuple[float, tuple[float, float]],
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    OCO: SELL limit  +  SELL stop-limit.

    sell_prices = (limit_price, (stop_price, stop_limit_price))
    Constraint: limit_price > stop_price >= stop_limit_price
    """
    _validate_symbol_instructions_quantities(
        symbol, input_instruction="SELL", input_quantity=quantity
    )

    if (
        not isinstance(sell_prices, (tuple, list))
        or len(sell_prices) != 2
        or not isinstance(sell_prices[1], (tuple, list))
        or len(sell_prices[1]) != 2
    ):
        raise ValueError(
            "sell_prices must be (limit_price, (stop_price, stop_limit_price))"
        )
    if not isinstance(sessions, (tuple, list)) or len(sessions) != 2:
        raise ValueError("sessions must contain exactly two values")

    limit_price, (stop_price, stop_limit_price) = sell_prices
    session_limit, session_stoplimit = sessions

    _validate_positive_values(
        limit_price=limit_price,
        stop_price=stop_price,
        stop_limit_price=stop_limit_price,
    )
    if not limit_price > stop_price:
        raise ValueError("limit_price must be greater than stop_price")
    if not stop_price >= stop_limit_price:
        raise ValueError("stop_limit_price must be <= stop_price")

    leg = _make_equity_leg(symbol, quantity, "SELL")

    limit_payload = {
        "orderType": "LIMIT",
        "price": str(limit_price),
        "session": session_limit,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }
    stoplimit_payload = {
        "orderType": "STOP_LIMIT",
        "price": str(stop_limit_price),
        "stopPrice": str(stop_price),
        "session": session_stoplimit,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }
    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [limit_payload, stoplimit_payload],
    }


def build_sell_trailingstop_sell_limit_oco_payload(
    symbol: str,
    quantity: int,
    # (limit_price, trailing_offset)
    sell_prices: tuple[float, float],
    stop_price_link_type: StopPriceLinkType = "PERCENT",
    stop_price_link_basis: StopPriceLinkBasis = "LAST",
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    OCO: SELL limit  +  SELL trailing-stop.

    sell_prices = (limit_price, trailing_offset)
    """
    _validate_symbol_instructions_quantities(
        symbol, input_instruction="SELL", input_quantity=quantity
    )
    if not isinstance(sell_prices, (tuple, list)) or len(sell_prices) != 2:
        raise ValueError("sell_prices must be (limit_price, trailing_offset)")

    limit_price, offset = sell_prices
    _validate_positive_values(limit_price=limit_price)
    _validate_trailing_stop(stop_price_link_type, offset)

    leg = _make_equity_leg(symbol, quantity, "SELL")

    limit_payload = {
        "orderType": "LIMIT",
        "price": str(limit_price),
        "session": session,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }
    trailing_payload = {
        "orderType": "TRAILING_STOP",
        "stopPriceLinkBasis": stop_price_link_basis,
        "stopPriceLinkType": stop_price_link_type,
        "stopPriceOffset": offset,
        "session": session,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }
    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [limit_payload, trailing_payload],
    }


def build_sell_trailingstop_sell_stoplimit_oco_payload(
    symbol: str,
    quantity: int,
    # (stop_price, stop_limit_price)
    stop_prices: tuple[float, float],
    stop_price_offset: float,
    stop_price_link_type: StopPriceLinkType = "PERCENT",
    stop_price_link_basis: StopPriceLinkBasis = "LAST",
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    OCO: SELL trailing-stop  +  SELL stop-limit.

    stop_prices = (stop_price, stop_limit_price)
    Constraint: stop_price >= stop_limit_price
    """
    _validate_symbol_instructions_quantities(
        symbol, input_instruction="SELL", input_quantity=quantity
    )
    if not isinstance(stop_prices, (tuple, list)) or len(stop_prices) != 2:
        raise ValueError("stop_prices must be (stop_price, stop_limit_price)")

    stop_price, stop_limit_price = stop_prices
    _validate_positive_values(stop_price=stop_price, stop_limit_price=stop_limit_price)
    _validate_trailing_stop(stop_price_link_type, stop_price_offset)

    if stop_price < stop_limit_price:
        raise ValueError("stop_price must be >= stop_limit_price")

    leg = _make_equity_leg(symbol, quantity, "SELL")

    trailing_payload = {
        "orderType": "TRAILING_STOP",
        "session": session,
        "duration": duration,
        "stopPriceLinkBasis": stop_price_link_basis,
        "stopPriceLinkType": stop_price_link_type,
        "stopPriceOffset": stop_price_offset,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }
    stoplimit_payload = {
        "orderType": "STOP_LIMIT",
        "price": str(stop_limit_price),
        "stopPrice": str(stop_price),
        "session": session,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }
    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [trailing_payload, stoplimit_payload],
    }


def build_buy_limit_trigger_sell_limit_stop_oco_payload(
    symbol: str,
    quantity: int,
    # (buy_limit, sell_limit, sell_stop)
    prices: tuple[float, float, float],
    # (buy_session, sell_limit_session, sell_stop_session)
    sessions: tuple[Session, Session, Session] = (
        "NORMAL",
        "NORMAL",
        "NORMAL",
    ),
    # (buy_duration, sell_duration)
    durations: tuple[Duration, Duration] = ("DAY", "GOOD_TILL_CANCEL"),
) -> OrderPayload:
    """
    First-triggers-OCO:

        BUY limit  →  OCO(SELL limit, SELL stop)

    prices   = (buy_limit, sell_limit, sell_stop)
    sessions = (buy, sell_limit, sell_stop)
    durations = (buy, sell)
    """
    _validate_symbol_instructions_quantities(
        symbol, input_instruction="BUY", input_quantity=quantity
    )
    if not isinstance(prices, (tuple, list)) or len(prices) != 3:
        raise ValueError("prices must be (buy_limit, sell_limit, sell_stop)")
    if not isinstance(sessions, (tuple, list)) or len(sessions) != 3:
        raise ValueError("sessions must contain three values")
    if not isinstance(durations, (tuple, list)) or len(durations) != 2:
        raise ValueError("durations must be (buy_duration, sell_duration)")

    buy_limit, sell_limit, sell_stop = prices
    session_buy, session_sell_limit, session_sell_stop = sessions
    buy_duration, sell_duration = durations

    _validate_positive_values(
        buy_limit=buy_limit,
        sell_limit=sell_limit,
        sell_stop=sell_stop,
    )

    buy_leg = _make_equity_leg(symbol, quantity, "BUY")
    sell_leg = _make_equity_leg(symbol, quantity, "SELL")

    sell_limit_payload = {
        "orderType": "LIMIT",
        "price": str(sell_limit),
        "session": session_sell_limit,
        "duration": sell_duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [sell_leg],
    }
    sell_stop_payload = {
        "orderType": "STOP",
        "stopPrice": str(sell_stop),
        "session": session_sell_stop,
        "duration": sell_duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [sell_leg],
    }

    return {
        "orderType": "LIMIT",
        "price": str(buy_limit),
        "session": session_buy,
        "duration": buy_duration,
        "orderStrategyType": "TRIGGER",
        "orderLegCollection": [buy_leg],
        "childOrderStrategies": [
            {
                "orderStrategyType": "OCO",
                "childOrderStrategies": [
                    sell_limit_payload,
                    sell_stop_payload,
                ],
            }
        ],
    }


def build_buy_trailingstop_trigger_sell_trailingstop_payload(
    symbol: str,
    quantities: tuple[int, int],  # (buy_qty, sell_qty)
    # trailing parameters for buy / sell
    stop_price_link_bases: tuple[StopPriceLinkBasis, StopPriceLinkBasis] = (
        "MARK",
        "MARK",
    ),
    stop_price_link_types: tuple[StopPriceLinkType, StopPriceLinkType] = (
        "PERCENT",
        "PERCENT",
    ),
    stop_price_offsets: tuple[float, float] = (2.0, 2.0),
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    durations: tuple[Duration, Duration] = ("DAY", "DAY"),
) -> OrderPayload:
    """
    Trailing-stop BUY that triggers a trailing-stop SELL.

    All paired values are 2-tuples: (buy, sell).
    """
    if not isinstance(quantities, (tuple, list)) or len(quantities) != 2:
        raise ValueError("quantities must be (buy_qty, sell_qty)")

    qty_buy, qty_sell = quantities
    _validate_symbol_instructions_quantities(
        symbol,
        buy_instruction="BUY",
        buy_quantity=qty_buy,
        sell_instruction="SELL",
        sell_quantity=qty_sell,
    )

    for name, values in (
        ("stop_price_link_bases", stop_price_link_bases),
        ("stop_price_link_types", stop_price_link_types),
        ("stop_price_offsets", stop_price_offsets),
        ("sessions", sessions),
        ("durations", durations),
    ):
        if not isinstance(values, (tuple, list)) or len(values) != 2:
            raise ValueError(f"{name} must contain exactly two values")

    basis_buy, basis_sell = stop_price_link_bases
    type_buy, type_sell = stop_price_link_types
    offset_buy, offset_sell = stop_price_offsets
    session_buy, session_sell = sessions
    duration_buy, duration_sell = durations

    _validate_trailing_stop(type_buy, offset_buy)
    _validate_trailing_stop(type_sell, offset_sell)

    buy_leg = _make_equity_leg(symbol, qty_buy, "BUY")
    sell_leg = _make_equity_leg(symbol, qty_sell, "SELL")

    sell_payload = {
        "orderType": "TRAILING_STOP",
        "session": session_sell,
        "duration": duration_sell,
        "stopPriceLinkBasis": basis_sell,
        "stopPriceLinkType": type_sell,
        "stopPriceOffset": offset_sell,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [sell_leg],
    }

    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "session": session_buy,
        "duration": duration_buy,
        "stopPriceLinkBasis": basis_buy,
        "stopPriceLinkType": type_buy,
        "stopPriceOffset": offset_buy,
        "orderStrategyType": "TRIGGER",
        "orderLegCollection": [buy_leg],
        "childOrderStrategies": [sell_payload],
    }


def build_sell_trailingstop_trigger_buy_trailingstop_payload(
    symbol: str,
    quantities: tuple[int, int],  # (sell_qty, buy_qty)
    stop_price_link_bases: tuple[StopPriceLinkBasis, StopPriceLinkBasis] = (
        "MARK",
        "MARK",
    ),
    stop_price_link_types: tuple[StopPriceLinkType, StopPriceLinkType] = (
        "PERCENT",
        "PERCENT",
    ),
    stop_price_offsets: tuple[float, float] = (2.0, 2.0),
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    durations: tuple[Duration, Duration] = ("DAY", "DAY"),
) -> OrderPayload:
    """
    Trailing-stop SELL that triggers a trailing-stop BUY.

    All paired values are 2-tuples: (sell, buy).
    """
    if not isinstance(quantities, (tuple, list)) or len(quantities) != 2:
        raise ValueError("quantities must be (sell_qty, buy_qty)")

    qty_sell, qty_buy = quantities
    _validate_symbol_instructions_quantities(
        symbol,
        sell_instruction="SELL",
        sell_quantity=qty_sell,
        buy_instruction="BUY",
        buy_quantity=qty_buy,
    )

    for name, values in (
        ("stop_price_link_bases", stop_price_link_bases),
        ("stop_price_link_types", stop_price_link_types),
        ("stop_price_offsets", stop_price_offsets),
        ("sessions", sessions),
        ("durations", durations),
    ):
        if not isinstance(values, (tuple, list)) or len(values) != 2:
            raise ValueError(f"{name} must contain exactly two values")

    basis_sell, basis_buy = stop_price_link_bases
    type_sell, type_buy = stop_price_link_types
    offset_sell, offset_buy = stop_price_offsets
    session_sell, session_buy = sessions
    duration_sell, duration_buy = durations

    _validate_trailing_stop(type_sell, offset_sell)
    _validate_trailing_stop(type_buy, offset_buy)

    sell_leg = _make_equity_leg(symbol, qty_sell, "SELL")
    buy_leg = _make_equity_leg(symbol, qty_buy, "BUY")

    buy_payload = {
        "orderType": "TRAILING_STOP",
        "session": session_buy,
        "duration": duration_buy,
        "stopPriceLinkBasis": basis_buy,
        "stopPriceLinkType": type_buy,
        "stopPriceOffset": offset_buy,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [buy_leg],
    }

    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "session": session_sell,
        "duration": duration_sell,
        "stopPriceLinkBasis": basis_sell,
        "stopPriceLinkType": type_sell,
        "stopPriceOffset": offset_sell,
        "orderStrategyType": "TRIGGER",
        "orderLegCollection": [sell_leg],
        "childOrderStrategies": [buy_payload],
    }
