"""
Schwab equity order payload builders.

All public functions return a dict that can be sent directly to the
Schwab Trader API.  Prices are always emitted as strings for precision.

TypedDict is the more accurate choice (other than @dataclass) because the Schwab API works with plain JSON objects (dictionaries), not Python class instances. TypedDict alone never protects you at runtime.
At development time, we run the following static type checker:
pip install pyright mypy
pyright your_module.py
# or
mypy your_module.py

If you want to 1. validate data 2. covert or coerce values 3. raise errors from wrong input at runtime, you need to add Pydantic models.

TypedDict helps you write correct code. Pydantic (or manual checks) helps you run correct code.

Naming:
stop_price_link_bases -- in helper functions and payload definations
StopPriceLinkBasis -- Literal type alias defined in type_literal module
stopPriceLinkBasis -- JSON formatted payload key

"""

from __future__ import annotations

from decimal import Decimal
from numbers import Real
from typing import (
    Any,
    Literal,
    Mapping,
    NotRequired,
    Sequence,
    TypedDict,
    Union,
    get_args,
)
import math


from schwab_trader.accounts.type_literal import (
    ComplexOrderStrategyType,  # ["NONE", ...]
    Instruction,  # ["BUY","SELL", ...]
    Session,  # ["NORMAL", "AM", "PM", "SEAMLESS"]
    Duration,  # ["DAY","GOOD_TILL_CANCEL",...]
    OrderType,  # ["MARKET","LIMIT","STOP","STOP_LIMIT","TRAILING_STOP",...]
    OrderStrategyType,  # ["SINGLE","OCO","TRIGGER",...]
    OrderLegCollectionInstrumentAssetType,  # ["EQUITY","OPTION",...]
    StopPriceLinkBasis,
    StopPriceLinkType,  # ["VALUE", "PERCENT", "TICK"]
    TaxLotMethod,  # ["FIFO", "LIFO", ...]
)

# ---------------------------------------------------------------------------
# Strong typing - TypedDict creates a typing construct, it is essentially a dict with extra metadata
# ---------------------------------------------------------------------------


class Instrument(TypedDict):
    symbol: str
    assetType: OrderLegCollectionInstrumentAssetType


class OrderLeg(TypedDict):
    # orderLegType: optional, mostly the same as instrument.assetType
    instruction: Instruction
    quantity: int
    instrument: Instrument


class OrderPayload(TypedDict):
    """Base shape of every Schwab order payload."""

    orderType: OrderType
    session: Session
    duration: Duration
    orderStrategyType: OrderStrategyType
    orderLegCollection: list[OrderLeg]

    # Optional / conditional fields - Keys marked with NotRequired is optional
    price: NotRequired[str]
    stopPrice: NotRequired[str]
    stopPriceLinkBasis: NotRequired[StopPriceLinkBasis]
    stopPriceLinkType: NotRequired[StopPriceLinkType]
    stopPriceOffset: NotRequired[float]
    complexOrderStrategyType: NotRequired[ComplexOrderStrategyType]
    childOrderStrategies: NotRequired[
        list["OrderPayload"]
    ]  # "OrderPayload" ← forward ref


Number = Union[int, float, Decimal]


# ---------------------------------------------------------------------------
# Validation helpers (clear error messages, no stringly typing)
# ---------------------------------------------------------------------------


def _validate_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError(f"symbol must be a non-empty string, got {symbol!r}")
    return symbol.strip().upper()


def _validate_positive(name: str, value: Number) -> None:
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise ValueError(f"{name} must be a real number, got {value!r}")
    is_finite = (
        value.is_finite() if isinstance(value, Decimal) else math.isfinite(value)
    )
    if not is_finite or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")


def _validate_percent(name: str, value: Number) -> None:
    _validate_positive(name, value)
    if not 0 < float(value) < 100:
        raise ValueError(f"{name} must be a percentage in (0, 100), got {value!r}")


# Both quantity: 100.0 and quantity: 100 specifications are OK.
def _validate_quantity(name: str, quantity: int) -> None:
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ValueError(f"{name} must be a positive integer, got {quantity!r}")
    # !r is a conversion flag in f-strings. It call repr(value) instead of str(value), makes the error message show the exact value (with quotes if it’s a string, etc.)


def _validate_literal(name: str, value: str, literal_type) -> None:
    allowed = get_args(literal_type)
    if value not in allowed:
        raise ValueError(f"{name} must be one of {list(allowed)}, got {value!r}")


def _validate_trailing_stop(
    link_type: StopPriceLinkType,
    offset: Number,
) -> None:
    if link_type not in ("VALUE", "PERCENT", "TICK"):
        raise ValueError(
            f"stop_price_link_type must be 'VALUE', 'PERCENT' or 'TICK', got {link_type!r}"
        )
    if link_type == "PERCENT":
        _validate_percent("stop_price_offset", offset)
    else:
        _validate_positive("stop_price_offset", offset)


def _validate_order_strategy(strategy: str) -> None:
    # Only the following three are supported values according to Schwab SDK.
    if strategy not in (
        "SINGLE",
        "OCO",
        "TRIGGER",
    ):
        raise ValueError(f"{strategy} is not a verified order submission strategy")


def _validate_xxx(xxx: str) -> None:
    pass


def _validate_tuple(name: str, value: Sequence[Any], expected_len: int) -> None:
    if not isinstance(value, (tuple, list)) or len(value) != expected_len:
        raise ValueError(
            f"{name} must be a sequence of length {expected_len}, got {value!r}"
        )


# ---------------------------------------------------------------------------
# Low-level construction helpers
# ---------------------------------------------------------------------------


def _price(value: Number) -> str:
    """Schwab expects prices as strings for precision."""
    return str(value)


def _make_instrument(symbol: str) -> Instrument:
    return {"symbol": _validate_symbol(symbol), "assetType": "EQUITY"}


def _make_leg(
    symbol: str,
    quantity: int,
    instruction: Instruction,
) -> OrderLeg:
    _validate_quantity("quantity", quantity)
    _validate_literal("instruction", instruction, Instruction)
    return {
        "orderLegType": "EQUITY",
        "instruction": instruction,
        "quantity": quantity,
        "instrument": _make_instrument(symbol),
    }


def _market_order(
    leg: OrderLeg,
    session: Session = "NORMAL",
) -> OrderPayload:
    _validate_literal("session", session, Session)
    return {
        "orderType": "MARKET",
        "session": session,
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }


def _limit_order(
    leg: OrderLeg,
    price: Number,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
    strategy: OrderStrategyType = "SINGLE",
) -> OrderPayload:
    _validate_positive("price", price)
    _validate_literal("session", session, Session)
    _validate_literal("duration", duration, Duration)
    _validate_literal("orderStrategyType", strategy, OrderStrategyType)
    return {
        "orderType": "LIMIT",
        "price": _price(price),
        "session": session,
        "duration": duration,
        "orderStrategyType": strategy,
        "orderLegCollection": [leg],
    }


def _stop_order(
    leg: OrderLeg,
    stop_price: Number,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    _validate_positive("stop_price", stop_price)
    _validate_literal("session", session, Session)
    _validate_literal("duration", duration, Duration)
    return {
        "orderType": "STOP",
        "stopPrice": _price(stop_price),
        "session": session,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }


def _stop_limit_order(
    leg: OrderLeg,
    stop_price: Number,
    limit_price: Number,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    _validate_positive("stop_price", stop_price)
    _validate_positive("limit_price", limit_price)
    _validate_literal("session", session, Session)
    _validate_literal("duration", duration, Duration)
    return {
        "orderType": "STOP_LIMIT",
        "price": _price(limit_price),
        "stopPrice": _price(stop_price),
        "session": session,
        "duration": duration,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [leg],
    }


def _trailing_stop_order(
    leg: OrderLeg,
    link_basis: StopPriceLinkBasis,
    link_type: StopPriceLinkType,
    offset: Number,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
    strategy: OrderStrategyType = "SINGLE",
) -> OrderPayload:
    _validate_trailing_stop(link_type, offset)
    _validate_literal("session", session, Session)
    _validate_literal("duration", duration, Duration)
    _validate_literal("orderStrategyType", strategy, OrderStrategyType)
    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "TRAILING_STOP",
        "stopPriceLinkBasis": link_basis,
        "stopPriceLinkType": link_type,
        "stopPriceOffset": float(offset),
        "session": session,
        "duration": duration,
        "orderStrategyType": strategy,
        "orderLegCollection": [leg],
    }


# ---------------------------------------------------------------------------
# Public builders – simple orders
# ---------------------------------------------------------------------------


def build_market_order_payload(
    symbol: str,
    quantity: int,
    instruction: Instruction,
    session: Session = "NORMAL",
) -> OrderPayload:
    """
    Build a market order (always DAY duration).

    Example
    -------
    >>> build_market_order_payload("AAPL", 10, "BUY")
    """
    leg = _make_leg(symbol, quantity, instruction)
    return _market_order(leg, session)


def build_limit_order_payload(
    symbol: str,
    quantity: int,
    instruction: Instruction,
    limit_price: Number,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    Build a simple limit order.

    Example
    -------
    >>> build_limit_order_payload("AAPL", 10, "BUY", 175.50)
    """
    leg = _make_leg(symbol, quantity, instruction)
    return _limit_order(leg, limit_price, session, duration)


def build_trailing_stop_order_payload(
    symbol: str,
    quantity: int,
    instruction: Instruction,
    stop_price_link_basis: StopPriceLinkBasis = "BID",
    stop_price_link_type: StopPriceLinkType = "PERCENT",
    stop_price_offset: Number = 2.0,
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    Build a trailing-stop order that becomes a market order when triggered.

    Example
    -------
    >>> build_trailing_stop_order_payload("AAPL", 10, "SELL", stop_price_offset=1.5)
    """
    leg = _make_leg(symbol, quantity, instruction)
    return _trailing_stop_order(
        leg,
        stop_price_link_basis,
        stop_price_link_type,
        stop_price_offset,
        session,
        duration,
    )


# ---------------------------------------------------------------------------
# Public builders – multi-leg / complex orders
# ---------------------------------------------------------------------------


def build_oto_limit_order_payload(
    symbol: str,
    quantity: int,
    instructions: tuple[Instruction, Instruction],
    limit_prices: tuple[Number, Number],
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    durations: tuple[Duration, Duration] = ("DAY", "DAY"),
) -> OrderPayload:
    """
    One-Triggers-Other (OTO) limit order.

    Tuple positions: [0] = primary, [1] = secondary.

    Example
    -------
    >>> build_oto_limit_order_payload(
    ...     "AAPL", 10,
    ...     instructions=("BUY", "SELL"),
    ...     limit_prices=(150.0, 165.0),
    ... )
    """
    _validate_tuple("instructions", instructions, 2)
    _validate_tuple("limit_prices", limit_prices, 2)
    _validate_tuple("sessions", sessions, 2)
    _validate_tuple("durations", durations, 2)

    primary_instr, secondary_instr = instructions
    primary_price, secondary_price = limit_prices
    primary_session, secondary_session = sessions
    primary_duration, secondary_duration = durations

    primary_leg = _make_leg(symbol, quantity, primary_instr)
    secondary_leg = _make_leg(symbol, quantity, secondary_instr)

    secondary = _limit_order(
        secondary_leg, secondary_price, secondary_session, secondary_duration
    )
    primary = _limit_order(
        primary_leg,
        primary_price,
        primary_session,
        primary_duration,
        strategy="TRIGGER",
    )
    primary["childOrderStrategies"] = [secondary]
    return primary


def build_sell_limit_stoplimit_oco_payload(
    symbol: str,
    quantity: int,
    sell_prices: tuple[Number, tuple[Number, Number]],
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    OCO: SELL limit + SELL stop-limit.

    sell_prices = (limit_price, (stop_price, stop_limit_price))
    Constraint: limit_price > stop_price >= stop_limit_price

    Example
    -------
    >>> build_sell_limit_stoplimit_oco_payload(
    ...     "AAPL", 10,
    ...     sell_prices=(180.0, (165.0, 164.50)),
    ... )
    """
    _validate_tuple("sell_prices", sell_prices, 2)
    _validate_tuple("sell_prices[1]", sell_prices[1], 2)
    _validate_tuple("sessions", sessions, 2)

    limit_price, (stop_price, stop_limit_price) = sell_prices
    session_limit, session_stoplimit = sessions

    if not limit_price > stop_price:
        raise ValueError(
            f"limit_price ({limit_price}) must be greater than stop_price ({stop_price})"
        )
    if not stop_price >= stop_limit_price:
        raise ValueError(
            f"stop_price ({stop_price}) must be >= stop_limit_price ({stop_limit_price})"
        )

    leg = _make_leg(symbol, quantity, "SELL")
    limit_leg = _limit_order(leg, limit_price, session_limit, duration)
    stoplimit_leg = _stop_limit_order(
        leg, stop_price, stop_limit_price, session_stoplimit, duration
    )

    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [limit_leg, stoplimit_leg],
    }  # type: ignore[return-value]


def build_sell_trailingstop_sell_limit_oco_payload(
    symbol: str,
    quantity: int,
    sell_prices: tuple[Number, Number],
    stop_price_link_type: StopPriceLinkType = "PERCENT",
    stop_price_link_basis: StopPriceLinkBasis = "LAST",
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    OCO: SELL limit + SELL trailing-stop.

    sell_prices = (limit_price, trailing_offset)

    Example
    -------
    >>> build_sell_trailingstop_sell_limit_oco_payload(
    ...     "AAPL", 10, sell_prices=(180.0, 2.0)
    ... )
    """
    _validate_tuple("sell_prices", sell_prices, 2)
    limit_price, offset = sell_prices

    leg = _make_leg(symbol, quantity, "SELL")
    limit_leg = _limit_order(leg, limit_price, session, duration)
    trailing_leg = _trailing_stop_order(
        leg, stop_price_link_basis, stop_price_link_type, offset, session, duration
    )

    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [limit_leg, trailing_leg],
    }  # type: ignore[return-value]


def build_sell_trailingstop_sell_stoplimit_oco_payload(
    symbol: str,
    quantity: int,
    stop_prices: tuple[Number, Number],
    stop_price_offset: Number,
    stop_price_link_type: StopPriceLinkType = "PERCENT",
    stop_price_link_basis: StopPriceLinkBasis = "LAST",
    session: Session = "NORMAL",
    duration: Duration = "DAY",
) -> OrderPayload:
    """
    OCO: SELL trailing-stop + SELL stop-limit.

    stop_prices = (stop_price, stop_limit_price)
    Constraint: stop_price >= stop_limit_price

    Example
    -------
    >>> build_sell_trailingstop_sell_stoplimit_oco_payload(
    ...     "AAPL", 10,
    ...     stop_prices=(165.0, 164.5),
    ...     stop_price_offset=1.5,
    ... )
    """
    _validate_tuple("stop_prices", stop_prices, 2)
    stop_price, stop_limit_price = stop_prices

    if stop_price < stop_limit_price:
        raise ValueError(
            f"stop_price ({stop_price}) must be >= stop_limit_price ({stop_limit_price})"
        )

    leg = _make_leg(symbol, quantity, "SELL")
    trailing_leg = _trailing_stop_order(
        leg,
        stop_price_link_basis,
        stop_price_link_type,
        stop_price_offset,
        session,
        duration,
    )
    stoplimit_leg = _stop_limit_order(
        leg, stop_price, stop_limit_price, session, duration
    )

    return {
        "orderStrategyType": "OCO",
        "childOrderStrategies": [trailing_leg, stoplimit_leg],
    }  # type: ignore[return-value]


def build_buy_limit_trigger_sell_limit_sell_stop_oco_payload(
    symbol: str,
    quantity: int,
    prices: tuple[Number, Number, Number],
    sessions: tuple[Session, Session, Session] = ("NORMAL", "NORMAL", "NORMAL"),
    durations: tuple[Duration, Duration] = ("DAY", "GOOD_TILL_CANCEL"),
) -> OrderPayload:
    """
    First-triggers-OCO:

        BUY limit  →  OCO(SELL limit, SELL stop)

    prices    = (buy_limit, sell_limit, sell_stop)
    sessions  = (buy, sell_limit, sell_stop)
    durations = (buy, sell)

    Example
    -------
    >>> build_buy_limit_trigger_sell_limit_sell_stop_oco_payload(
    ...     "AAPL", 10,
    ...     prices=(150.0, 165.0, 140.0),
    ... )
    """
    _validate_tuple("prices", prices, 3)
    _validate_tuple("sessions", sessions, 3)
    _validate_tuple("durations", durations, 2)

    buy_limit, sell_limit, sell_stop = prices
    session_buy, session_sell_limit, session_sell_stop = sessions
    buy_duration, sell_duration = durations

    buy_leg = _make_leg(symbol, quantity, "BUY")
    sell_leg = _make_leg(symbol, quantity, "SELL")

    sell_limit_payload = _limit_order(
        sell_leg, sell_limit, session_sell_limit, sell_duration
    )
    sell_stop_payload = _stop_order(
        sell_leg, sell_stop, session_sell_stop, sell_duration
    )

    primary = _limit_order(
        buy_leg, buy_limit, session_buy, buy_duration, strategy="TRIGGER"
    )
    primary["childOrderStrategies"] = [
        {
            "orderStrategyType": "OCO",
            "childOrderStrategies": [sell_limit_payload, sell_stop_payload],
        }
    ]
    return primary


def build_buy_trailingstop_trigger_sell_trailingstop_payload(
    symbol: str,
    quantities: tuple[int, int],
    stop_price_link_bases: tuple[StopPriceLinkBasis, StopPriceLinkBasis] = (
        "MARK",
        "MARK",
    ),
    stop_price_link_types: tuple[StopPriceLinkType, StopPriceLinkType] = (
        "PERCENT",
        "PERCENT",
    ),
    stop_price_offsets: tuple[Number, Number] = (2.0, 2.0),
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    durations: tuple[Duration, Duration] = ("DAY", "DAY"),
) -> OrderPayload:
    """
    Trailing-stop BUY that triggers a trailing-stop SELL.

    All paired values are 2-tuples: (buy, sell).

    Example
    -------
    >>> build_buy_trailingstop_trigger_sell_trailingstop_payload(
    ...     "AAPL",
    ...     quantities=(10, 10),
    ...     stop_price_offsets=(1.5, 2.0),
    ... )
    """
    _validate_tuple("quantities", quantities, 2)
    _validate_tuple("stop_price_link_bases", stop_price_link_bases, 2)
    _validate_tuple("stop_price_link_types", stop_price_link_types, 2)
    _validate_tuple("stop_price_offsets", stop_price_offsets, 2)
    _validate_tuple("sessions", sessions, 2)
    _validate_tuple("durations", durations, 2)

    qty_buy, qty_sell = quantities
    basis_buy, basis_sell = stop_price_link_bases
    type_buy, type_sell = stop_price_link_types
    offset_buy, offset_sell = stop_price_offsets
    session_buy, session_sell = sessions
    duration_buy, duration_sell = durations

    buy_leg = _make_leg(symbol, qty_buy, "BUY")
    sell_leg = _make_leg(symbol, qty_sell, "SELL")

    sell_payload = _trailing_stop_order(
        sell_leg, basis_sell, type_sell, offset_sell, session_sell, duration_sell
    )
    primary = _trailing_stop_order(
        buy_leg,
        basis_buy,
        type_buy,
        offset_buy,
        session_buy,
        duration_buy,
        strategy="TRIGGER",
    )
    primary["childOrderStrategies"] = [sell_payload]
    return primary


def build_sell_trailingstop_trigger_buy_trailingstop_payload(
    symbol: str,
    quantities: tuple[int, int],
    stop_price_link_bases: tuple[StopPriceLinkBasis, StopPriceLinkBasis] = (
        "MARK",
        "MARK",
    ),
    stop_price_link_types: tuple[StopPriceLinkType, StopPriceLinkType] = (
        "PERCENT",
        "PERCENT",
    ),
    stop_price_offsets: tuple[Number, Number] = (2.0, 2.0),
    sessions: tuple[Session, Session] = ("NORMAL", "NORMAL"),
    durations: tuple[Duration, Duration] = ("DAY", "DAY"),
) -> OrderPayload:
    """
    Trailing-stop SELL that triggers a trailing-stop BUY.

    All paired values are 2-tuples: (sell, buy).

    Example
    -------
    >>> build_sell_trailingstop_trigger_buy_trailingstop_payload(
    ...     "AAPL",
    ...     quantities=(10, 10),
    ...     stop_price_offsets=(2.0, 1.5),
    ... )
    """
    _validate_tuple("quantities", quantities, 2)
    _validate_tuple("stop_price_link_bases", stop_price_link_bases, 2)
    _validate_tuple("stop_price_link_types", stop_price_link_types, 2)
    _validate_tuple("stop_price_offsets", stop_price_offsets, 2)
    _validate_tuple("sessions", sessions, 2)
    _validate_tuple("durations", durations, 2)

    qty_sell, qty_buy = quantities
    basis_sell, basis_buy = stop_price_link_bases
    type_sell, type_buy = stop_price_link_types
    offset_sell, offset_buy = stop_price_offsets
    session_sell, session_buy = sessions
    duration_sell, duration_buy = durations

    sell_leg = _make_leg(symbol, qty_sell, "SELL")
    buy_leg = _make_leg(symbol, qty_buy, "BUY")

    buy_payload = _trailing_stop_order(
        buy_leg, basis_buy, type_buy, offset_buy, session_buy, duration_buy
    )
    primary = _trailing_stop_order(
        sell_leg,
        basis_sell,
        type_sell,
        offset_sell,
        session_sell,
        duration_sell,
        strategy="TRIGGER",
    )
    primary["childOrderStrategies"] = [buy_payload]
    return primary
