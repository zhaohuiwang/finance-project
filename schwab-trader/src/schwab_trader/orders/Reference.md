Note:
1. You may specify quantity in top-level like {..., "quantity": 10, ...} but it will be replaced with the quantity specification in the orderLegCollection if the numbers do not align. If only {..., "quantity": 10, ...} is specified in the orderLegCollection, both top-level and orderLegCollection will have {..., "quantity": 10, ...} in the order detail.

Canonical Layout Patterns.
A. Simple single-leg order

```JSON
{
  "orderType": "LIMIT",
  "session": "NORMAL",
  "duration": "DAY",
  "orderStrategyType": "SINGLE",
  "complexOrderStrategyType": "NONE", /* optional */
  "taxLotMethod": "LIFO", /* Optional, the default is set in the account settings */
  "quantity": 10,
  /* 10.0 and 10 both OK. Optional, will be overwritten by quantity in orderLegCollection */
  "price": "175.50",
  "orderLegCollection": [
    {
      "instruction": "BUY",
      "quantity": 10,
      "instrument": { "symbol": "AAPL", "assetType": "EQUITY" }
    }
  ]
}
/* Whole shares only; Prices as strings */
```

B. Trailing Stop
```JSON
{
  "complexOrderStrategyType": "NONE",
  "orderType": "TRAILING_STOP",
  "session": "NORMAL",
  "duration": "DAY",
  "orderStrategyType": "SINGLE",
  "stopPriceLinkBasis": "LAST",      // or BID, ASK, MARK, …
  "stopPriceLinkType": "PERCENT",    // or VALUE, TICK
  "stopPriceOffset": 2.0,
  "orderLegCollection": [ … ]
}
```

C. One-Triggers-Other (OTO) – parent TRIGGER + child
```JSON
{
  "orderType": "LIMIT",
  "session": "NORMAL",
  "duration": "DAY",
  "orderStrategyType": "TRIGGER",
  "price": "150.00",
  "orderLegCollection": [ /* buy leg */ ],
  "childOrderStrategies": [
    {
      "orderType": "LIMIT",
      "session": "NORMAL",
      "duration": "GOOD_TILL_CANCEL",
      "orderStrategyType": "SINGLE",
      "price": "165.00",
      "orderLegCollection": [ /* sell leg */ ]
    }
  ]
}
/*childOrderStrategies can nest (TRIGGER containing an OCO, etc.)*/
```

D. Bracket / First-Triggers-OCO
```JSON
{
        "orderLegType": "EQUITY",
        "instruction": instruction,
        "quantity": quantity,
        "instrument": _make_instrument(symbol),
    }
    
{
  "orderType": "LIMIT",
  "session": "NORMAL",
  "duration": "DAY",
  "orderStrategyType": "TRIGGER",
  "price": "150.00",
  "orderLegCollection": [ /* entry buy */ ],
  "childOrderStrategies": [
    {
      "orderStrategyType": "OCO",
      "childOrderStrategies": [
        { /* take-profit LIMIT */ },
        { /* stop-loss STOP or STOP_LIMIT */ }
      ]
    }
  ]
}
```

E. Pure top-level OCO
```JSON
{
  "orderStrategyType": "OCO",
  "childOrderStrategies": [
    { /* first child – full order object */ },
    { /* second child – full order object */ }
  ]
}
```



# The Schwab's childOrderStrategies structure is inherently hierarchical for conditional orders. THe following nested buy-sell orders is accepted by Schwab and displayed on thinkorswim only (not on the web version).
```Python
buy_leg = {
    "orderLegType": "EQUITY",
    "instrument": {
        "assetType": "EQUITY",
        "symbol": "NBIS",
    },
    "instruction": "BUY",
    "quantity": 1,
}

sell_leg = {
    "orderLegType": "EQUITY",
    "instrument": {
        "assetType": "EQUITY",
        "symbol": "NBIS",
    },
    "instruction": "SELL",
    "quantity": 1,
}

order_payload = {
    # <<<<<<<< Buy-Trigger-Sell... Pattern START here>>>>>>>>
    "orderType": "LIMIT",
    "session": "NORMAL",
    "duration": "DAY",
    "orderStrategyType": "TRIGGER",
    "price": "120.00",
    "orderLegCollection": [buy_leg],
    "childOrderStrategies": [
        {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "TRIGGER",
            "price": "160.00",
            "orderLegCollection": [sell_leg],
            "childOrderStrategies": [
            # <<<<<<<< Buy-Trigger-Sell... Pattern END here>>>>>>>>
                {
                    "orderType": "LIMIT",
                    "session": "NORMAL",
                    "duration": "DAY",
                    "orderStrategyType": "TRIGGER",
                    "price": "120.00",
                    "orderLegCollection": [buy_leg],
                    "childOrderStrategies": [
                        {
                            "orderType": "LIMIT",
                            "session": "NORMAL",
                            "duration": "DAY",
                            "orderStrategyType": "TRIGGER",
                            "price": "160.00",
                            "orderLegCollection": [sell_leg],
                            "childOrderStrategies": [
                                {
                                    "orderType": "LIMIT",
                                    "session": "NORMAL",
                                    "duration": "DAY",
                                    "orderStrategyType": "TRIGGER",
                                    "price": "120.00",
                                    "orderLegCollection": [buy_leg],
                                    "childOrderStrategies": [
                                        {
                                            "orderType": "LIMIT",
                                            "session": "NORMAL",
                                            "duration": "DAY",
                                            "orderStrategyType": "TRIGGER",
                                            "price": "160.00",
                                            "orderLegCollection": [sell_leg],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ],
}


status, date, order_id = place_order(
    client=client,
    accountHash=hashValue,
    order=order_payload,
)
```

# A generalized order generator
```Python
def create_order_payload(
    symbol,
    quantity,
    buy_price,
    sell_price,
    cycles=3,
):
    def make_leg(instruction):
        return {
            "orderLegType": "EQUITY",
            "instrument": {
                "assetType": "EQUITY",
                "symbol": symbol,
            },
            "instruction": instruction,
            "quantity": quantity,
        }

    def make_order(instruction, price, child=None, duration="GOOD_TILL_CANCEL"):
        order = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "TRIGGER",
            "price": str(price),
            "orderLegCollection": [make_leg(instruction)],
        }

        if child:
            order["childOrderStrategies"] = [child]

        return order

    # Build the order chain backwards
    child = None

    for i in range(cycles * 2, 0, -1):
        if i % 2 == 1:
            instruction = "BUY"
            price = buy_price
        else:
            instruction = "SELL"
            price = sell_price

        child = make_order(
            instruction,
            price,
            child,
        )

    # First BUY is the initial parent order
    child["duration"] = "DAY"

    return child


order_payload = create_order_payload(
    symbol="NBIS",
    quantity=1,
    buy_price=120,
    sell_price=160,
    cycles=3,
)

status, date, order_id = place_order(
    client=client,
    accountHash=hashValue,
    order=order_payload,
)

```