
Canonical Layout Patterns.
A. Simple single-leg order

```JSON
{
  "orderType": "LIMIT",
  "session": "NORMAL",
  "duration": "DAY",
  "orderStrategyType": "SINGLE",
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



