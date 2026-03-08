"""
Options and their Symbology:
Options symbols are broken down as:
Underlying Symbol (6 characters including spaces) | Expiration (6 characters) | Call/Put (1 character) | Strike Price (5+3=8 characters)

Option Symbol: XYZ 210115C00050000
Stock Symbol: XYZ
Expiration: 2021/01/15
Type: Call
Strike Price: $50.00

Option Symbol: XYZ 210115C00062500
Stock Symbol: XYZ
Expiration: 2021/01/15
Type: Call
Strike Price: $62.50

"""

# Dictionary specification for option orders.


def buy_limit_single_option_dict(
    symbol: str, quantity: int, limit_price: float
) -> dict:
    """
    Buy Limit: Single Option
    Buy to open 10 contracts of the XYZ March 15, 2024 $50 CALL ("XYZ   240315C00500000") at a Limit of $6.45 good for the Day.
    This is a bullish strategy, meaning you're betting on the stock price going above $50 by the expiration date (March 15, 2024).

    Risk: The most you can lose is the premium you pay ($6,450).
    Reward: The potential profit is unlimited, depending on how high the underlying stock price rises.

    """
    return {
        "complexOrderStrategyType": "NONE",
        "orderType": "LIMIT",
        "session": "NORMAL",
        "price": str(limit_price),
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY_TO_OPEN",
                "quantity": quantity,
                "instrument": {"symbol": symbol.upper(), "assetType": "OPTION"},
            }
        ],
    }


def buy_limit_vertical_call_spread_dict(
    symbol_higher_strike: str,
    symbol_lower_strike: str,
    quantity: int,
    limit_price: float,
) -> dict:
    """
    Buy Limit: Vertical Call Spread
    Buy to open 2 contracts of the XYZ March 15, 2024 $45 Put and Sell to open 2 contract of the XYZ March 15, 2024 $43 Put at a LIMIT price of $0.10 good for the Day.
    "XYZ   240315P00045000" is XYZ Mar 15 2024 $45 Put
    "XYZ   240315P00043000" is XYZ Mar 15 2024 $43 Put
    Vertical Put Spread involves:
        Buying a higher strike put (in this case, the $45 Put).
        Selling a lower strike put (in this case, the $43 Put).
    The goal of this buy limit vertical put spread is to pay a small amount (net debit) to create a position where you expect moderate downside movement in XYZ, with the maximum profit realized if XYZ stays above $45 at expiration.

    The max risk is limited to the net debit you pay, while the max reward is the difference between the strike prices ($45 - $43), minus the premium paid for the spread.
    """
    return {
        "orderType": "NET_DEBIT",
        "session": "NORMAL",
        "price": limit_price,
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY_TO_OPEN",
                "quantity": quantity,
                "instrument": {
                    "symbol": symbol_higher_strike.upper(),
                    "assetType": "OPTION",
                },
            },
            {
                "instruction": "SELL_TO_OPEN",
                "quantity": quantity,
                "instrument": {
                    "symbol": symbol_lower_strike.upper(),
                    "assetType": "OPTION",
                },
            },
        ],
    }


def sell_covered_call_dict(symbol: str, quantity: int, limit_price: float) -> dict:
    """
    Sell Covered Call
    Sell to open 1 contract of the XYZ March 6, 2026 $9.00 CALL at a Limit of $0.50 good for the Day.
    symbol="ACHR  260306C00009000" is ACHR Mar 6 2026 $9.00 Call

    Reward: The maximum reward is the premium received from selling the call option, plus the possibility of capital appreciation up to the strike price ($9.00), but no higher.

    Risk: The risk is similar to holding the stock itself because if the stock price drops, you may lose on the stock's decline, though you still keep the premium collected from the sale of the call.

    """
    return {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "NET_DEBIT",
        "complexOrderStrategyType": "COVERED",
        "orderStrategyType": "SINGLE",
        "price": limit_price,
        "orderLegCollection": [
            {
                "orderLegType": "OPTION",
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": symbol.upper(),
                },
                "instruction": "SELL_TO_OPEN",
                "quantity": quantity,
            }
        ],
    }


# order = sell_covered_call(
#     symbol="ACHR  260306C00009000",
#     quantity=1,
#     limit_price=0.5)

# response = client.place_order(accountHash, order)
# # Check if the status code is 201 (Created successfully)
# if response.status_code == 201:
#     print("Order placed successfully!")
# else:
#     print(f"Failed to place the order. Status code: {response.status_code}")
#     print(f"Response content: {response.text}")
