from typing import Literal  # TypedDict

Session = Literal["NORMAL", "AM", "PM", "SEAMLESS"]
# NORMAL    Regular hours order
# AM        Pre-market buy/sell
# PM        After-hours (4–8 pm ET)
# SEAMLESS  24/5 overnight continuous

Duration = Literal[
    "DAY",
    "GOOD_TILL_CANCEL",
    "FILL_OR_KILL",
    "IMMEDIATE_OR_CANCEL",
    "END_OF_WEEK",
    "END_OF_MONTH",
    "NEXT_END_OF_MONTH",
    "UNKNOWN",
]

"""
The four combinations
session	    duration	        Effective execution hours	Order remains
NORMAL	    DAY	                9:30 AM-4:00 PM ET	        Today only
NORMAL	    GOOD_TILL_CANCEL	9:30 AM-4:00 PM ET	        Up to 180 days
SEAMLESS	DAY	                7:00 AM-8:00 PM ET	        Today only
SEAMLESS	GOOD_TILL_CANCEL	7:00 AM-8:00 PM ET	        Up to 180 days

The Schwab API documentation describes NORMAL as the regular session, 9:30 AM-4:00 PM ET, and SEAMLESS as the combination of the pre-market, normal, and after-market sessions.

Schwab's current extended-hours documentation specifies the practical windows as 7:00-9:25 AM ET, 9:30 AM-4:00 PM ET, and 4:05-8:00 PM ET, with five-minute closures around the regular session boundaries.

Schwab's extended-hours rules generally restrict extended-hours equity trading to limit orders. In particular, Schwab states that market, stop, and stop-limit orders aren't eligible for extended-hours execution in the standard extended-hours sessions.

"""

# status
OrderRequest = Literal[
    "AWAITING_PARENT_ORDER",
    "AWAITING_CONDITION",
    "AWAITING_STOP_CONDITION",
    "AWAITING_MANUAL_REVIEW",
    "ACCEPTED",
    "AWAITING_UR_OUT",
    "PENDING_ACTIVATION",
    "QUEUED",
    "WORKING",
    "REJECTED",
    "PENDING_CANCEL",
    "CANCELED",
    "PENDING_REPLACE",
    "REPLACED",
    "FILLED",
    "EXPIRED",
    "NEW",
    "AWAITING_RELEASE_TIME",
    "PENDING_ACKNOWLEDGEMENT",
    "PENDING_RECALL",
    "UNKNOWN",
]

OrderStrategyType = Literal[
    "SINGLE",
    "CANCEL",
    "RECALL",
    "PAIR",
    "FLATTEN",
    "TWO_DAY_SWAP",
    "BLAST_ALL",
    "OCO",
    "TRIGGER",
]

OrderType = Literal[
    "MARKET",
    "LIMIT",
    "STOP",
    "STOP_LIMIT",
    "TRAILING_STOP",
    "CABINET",
    "NON_MARKETABLE",
    "MARKET_ON_CLOSE",
    "EXERCISE",
    "TRAILING_STOP_LIMIT",
    "NET_DEBIT",
    "NET_CREDIT",
    "NET_ZERO",
    "LIMIT_ON_CLOSE",
    "UNKNOWN",
]

OrderLegInstruction = Literal[
    "BUY",
    "SELL",
    "BUY_TO_COVER",
    "SELL_SHORT",
    "BUY_TO_OPEN",
    "BUY_TO_CLOSE",
    "SELL_TO_OPEN",
    "SELL_TO_CLOSE",
    "EXCHANGE",
    "SELL_SHORT_EXEMPT",
]

OrderLegCollectionInstrumentAssetType = Literal[
    "EQUITY",
    "OPTION",
    "INDEX",
    "MUTUAL_FUND",
    "CASH_EQUIVALENT",
    "FIXED_INCOME",
    "CURRENCY",
    "COLLECTIVE_INVESTMENT",
]

ComplexOrderStrategyType = Literal[
    "NONE",
    "COVERED",
    "VERTICAL",
    "BACK_RATIO",
    "CALENDAR",
    "DIAGONAL",
    "STRADDLE",
    "STRANGLE",
    "COLLAR_SYNTHETIC",
    "BUTTERFLY",
    "CONDOR",
    "IRON_CONDOR",
    "VERTICAL_ROLL",
    "COLLAR_WITH_STOCK",
    "DOUBLE_DIAGONAL",
    "UNBALANCED_BUTTERFLY",
    "UNBALANCED_CONDOR",
    "UNBALANCED_IRON_CONDOR",
    "UNBALANCED_VERTICAL_ROLL",
    "MUTUAL_FUND_SWAP",
    "CUSTOM",
]

stopPriceLinkBasis = Literal[
    "MANUAL", "BASE", "TRIGGER", "LAST", "BID", "ASK", "ASK_BID", "MARK", "AVERAGE"
]

stopPriceLinkType = Literal["VALUE", "PERCENT", "TICK"]

stopTypestring = Literal["STANDARD", "BID", "ASK", "LAST", "MARK"]
priceLinkBasisstring = Literal[
    "MANUAL", "BASE", "TRIGGER", "LAST", "BID", "ASK", "ASK_BID", "MARK", "AVERAGE"
]

orderStrategyTypestring = Literal[
    "SINGLE",
    "CANCEL",
    "RECALL",
    "PAIR",
    "FLATTEN",
    "TWO_DAY_SWAP",
    "BLAST_ALL",
    "OCO",
    "TRIGGER",
]


# from enum import Enum
# from typing import TYPE_CHECKING


# def str_enum(name: str, members: list[str]) -> type[Enum]:
#     """
#     Creates a string-valued enum where each member.name == member.value.
#     Usage: OrderType.MARKET == "MARKET" is True
#     """
#     return Enum(name, {m: m for m in members}, type=str)


# if TYPE_CHECKING:
#     from typing import TypeAlias

#     Duration: TypeAlias = str


# Session = str_enum(
#     "Session",
#     [
#         "NORMAL",
#         "AM",
#         "PM",
#         "SEAMLESS",
#     ],
# )


# Duration = str_enum(
#     "Duration",
#     [
#         "DAY",
#         "GOOD_TILL_CANCEL",
#         "FILL_OR_KILL",
#         "IMMEDIATE_OR_CANCEL",
#         "END_OF_WEEK",
#         "END_OF_MONTH",
#         "NEXT_END_OF_MONTH",
#         "UNKNOWN",
#     ],
# )


# OrderRequest = str_enum(
#     "OrderRequest",
#     [
#         "AWAITING_PARENT_ORDER",
#         "AWAITING_CONDITION",
#         "AWAITING_STOP_CONDITION",
#         "AWAITING_MANUAL_REVIEW",
#         "ACCEPTED",
#         "AWAITING_UR_OUT",
#         "PENDING_ACTIVATION",
#         "QUEUED",
#         "WORKING",
#         "REJECTED",
#         "PENDING_CANCEL",
#         "CANCELED",
#         "PENDING_REPLACE",
#         "REPLACED",
#         "FILLED",
#         "EXPIRED",
#         "NEW",
#         "AWAITING_RELEASE_TIME",
#         "PENDING_ACKNOWLEDGEMENT",
#         "PENDING_RECALL",
#         "UNKNOWN",
#     ],
# )

# OrderStrategyType = str_enum(
#     "OrderStrategyType",
#     [
#         "SINGLE",
#         "CANCEL",
#         "RECALL",
#         "PAIR",
#         "FLATTEN",
#         "TWO_DAY_SWAP",
#         "BLAST_ALL",
#         "OCO",
#         "TRIGGER",
#     ],
# )

# OrderType = str_enum(
#     "OrderType",
#     [
#         "MARKET",
#         "LIMIT",
#         "STOP",
#         "STOP_LIMIT",
#         "TRAILING_STOP",
#         "CABINET",
#         "NON_MARKETABLE",
#         "MARKET_ON_CLOSE",
#         "EXERCISE",
#         "TRAILING_STOP_LIMIT",
#         "NET_DEBIT",
#         "NET_CREDIT",
#         "NET_ZERO",
#         "LIMIT_ON_CLOSE",
#         "UNKNOWN",
#     ],
# )

# OrderLegInstruction = str_enum(
#     "OrderLegInstruction",
#     [
#         "BUY",
#         "SELL",
#         "BUY_TO_COVER",
#         "SELL_SHORT",
#         "BUY_TO_OPEN",
#         "BUY_TO_CLOSE",
#         "SELL_TO_OPEN",
#         "SELL_TO_CLOSE",
#         "EXCHANGE",
#         "SELL_SHORT_EXEMPT",
#     ],
# )

# OrderLegCollectionInstruction = str_enum(
#     "OrderLegCollectionInstruction",
#     [
#         "BUY",
#         "SELL",
#         "BUY_TO_COVER",
#         "SELL_SHORT",
#         "BUY_TO_OPEN",
#         "BUY_TO_CLOSE",
#         "SELL_TO_OPEN",
#         "SELL_TO_CLOSE",
#         "EXCHANGE",
#         "SELL_SHORT_EXEMPT",
#     ],
# )


# OrderLegCollectionInstrumentAssetType = str_enum(
#     "OrderLegCollectionInstrumentAssetType",
#     [
#         "EQUITY",
#         "OPTION",
#         "INDEX",
#         "MUTUAL_FUND",
#         "CASH_EQUIVALENT",
#         "FIXED_INCOME",
#         "CURRENCY",
#         "COLLECTIVE_INVESTMENT",
#     ],
# )

# ComplexOrderStrategyType = str_enum(
#     "ComplexOrderStrategyType",
#     [
#         "NONE",
#         "COVERED",
#         "VERTICAL",
#         "BACK_RATIO",
#         "CALENDAR",
#         "DIAGONAL",
#         "STRADDLE",
#         "STRANGLE",
#         "COLLAR_SYNTHETIC",
#         "BUTTERFLY",
#         "CONDOR",
#         "IRON_CONDOR",
#         "VERTICAL_ROLL",
#         "COLLAR_WITH_STOCK",
#         "DOUBLE_DIAGONAL",
#         "UNBALANCED_BUTTERFLY",
#         "UNBALANCED_CONDOR",
#         "UNBALANCED_IRON_CONDOR",
#         "UNBALANCED_VERTICAL_ROLL",
#         "MUTUAL_FUND_SWAP",
#         "CUSTOM",
#     ],
# )
