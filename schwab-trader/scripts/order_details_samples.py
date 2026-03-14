
# After you place a sell_limit_sell_stoplimit_oco order
# thinkorswim app > order history > view thinkLog notes on order > "TA_zhwang22gmailcom1753933248 SELL -380 IREN @45.00 LMT OCO #1005667584230"
# "TA_zhwang22gmailcom1753933248 SELL -380 IREN @39.80 STPLMT 40.00 OCO #1005667584230"



order = sell_limit_dict(
    symbol="NBIS",
    quantity=1,
    limit_price=100.0,
    duration=Duration.GOOD_TILL_CANCEL,
)
order_details = {
    "session": "NORMAL",
    "duration": "GOOD_TILL_CANCEL",
    "orderType": "LIMIT",
    "complexOrderStrategyType": "NONE",
    "quantity": 1.0,
    "filledQuantity": 0.0,
    "remainingQuantity": 0.0,
    "requestedDestination": "AUTO",
    "destinationLinkName": "AutoRoute",
    "price": 100.0,
    "orderLegCollection": [
        {
            "orderLegType": "EQUITY",
            "legId": 1,
            "instrument": {
                "assetType": "EQUITY",
                "cusip": "N97284108",
                "symbol": "NBIS",
                "instrumentId": 4339891,
            },
            "instruction": "SELL",
            "positionEffect": "CLOSING",
            "quantity": 1.0,
        }
    ],
    "orderStrategyType": "SINGLE",
    "orderId": 1005588236651,
    "cancelable": False,
    "editable": False,
    "status": "CANCELED",
    "enteredTime": "2026-03-04T01:26:35+0000",
    "closeTime": "2026-03-04T01:29:35+0000",
    "tag": "TA_zhwang22gmailcom1753933248",
    "accountNumber": 29308909,
    "orderActivityCollection": [
        {
            "activityType": "EXECUTION",
            "activityId": 113515796766,
            "executionType": "CANCELED",
            "quantity": 1.0,
            "orderRemainingQuantity": 0.0,
            "executionLegs": [
                {
                    "legId": 1,
                    "quantity": 1.0,
                    "mismarkedQuantity": 0.0,
                    "price": 0.0,
                    "time": "2026-03-04T01:29:35+0000",
                    "instrumentId": 4339891,
                }
            ],
        }
    ],
}


order = buy_limit_trigger_sell_limit_dict(
    symbol="NBIS",
    quantity=1,
    buy_limit_price=20,
    sell_limit_price=120,
    buy_duration=Duration.DAY,
    sell_duration=Duration.GOOD_TILL_CANCEL,
)
order_details = {
    "session": "NORMAL",
    "duration": "DAY",
    "orderType": "LIMIT",
    "complexOrderStrategyType": "NONE",
    "quantity": 1.0,
    "filledQuantity": 0.0,
    "remainingQuantity": 1.0,
    "requestedDestination": "AUTO",
    "destinationLinkName": "AutoRoute",
    "price": 20.0,
    "orderLegCollection": [
        {
            "orderLegType": "EQUITY",
            "legId": 1,
            "instrument": {
                "assetType": "EQUITY",
                "cusip": "N97284108",
                "symbol": "NBIS",
                "instrumentId": 4339891,
            },
            "instruction": "BUY",
            "positionEffect": "OPENING",
            "quantity": 1.0,
        }
    ],
    "orderStrategyType": "TRIGGER",
    "orderId": 1005588236683,
    "cancelable": True,
    "editable": False,
    "status": "PENDING_ACTIVATION",
    "enteredTime": "2026-03-04T01:46:44+0000",
    "tag": "TA_zhwang22gmailcom1753933248",
    "accountNumber": 29308909,
    "childOrderStrategies": [
        {
            "session": "NORMAL",
            "duration": "GOOD_TILL_CANCEL",
            "orderType": "LIMIT",
            "complexOrderStrategyType": "NONE",
            "quantity": 1.0,
            "filledQuantity": 0.0,
            "remainingQuantity": 1.0,
            "requestedDestination": "AUTO",
            "destinationLinkName": "AutoRoute",
            "price": 120.0,
            "orderLegCollection": [
                {
                    "orderLegType": "EQUITY",
                    "legId": 1,
                    "instrument": {
                        "assetType": "EQUITY",
                        "cusip": "N97284108",
                        "symbol": "NBIS",
                        "instrumentId": 4339891,
                    },
                    "instruction": "SELL",
                    "positionEffect": "CLOSING",
                    "quantity": 1.0,
                }
            ],
            "orderStrategyType": "SINGLE",
            "orderId": 1005588236684,
            "cancelable": True,
            "editable": False,
            "status": "AWAITING_PARENT_ORDER",
            "enteredTime": "2026-03-04T01:46:44+0000",
            "tag": "TA_zhwang22gmailcom1753933248",
            "accountNumber": 29308909,
        }
    ],
}
# Notice  'orderLegCollection' and 'childOrderStrategies' > 'orderLegCollection'


# Real Example
order_1 = buy_limit_dict(
    symbol="ACHR",
    quantity=1,
    limit_price=6.2,
    duration="DAY",
)

order = order_1

status_code, date, order_id = place_order(
    client=client, accountHash=hashValue, order=order
)
# >>> status_code
# 201
# >>> date
# 'Mon, 09 Mar 2026 15:50:23 GMT'
# >>> order_id
# '1005638175790'
order = client.order_details(hashValue, '1005638175790').json()
print(json.dumps(order, indent=4))

{
    "session": "NORMAL",
    "duration": "DAY",
    "orderType": "LIMIT",
    "complexOrderStrategyType": "NONE",
    "quantity": 1.0,
    "filledQuantity": 1.0,
    "remainingQuantity": 0.0,
    "requestedDestination": "AUTO",
    "destinationLinkName": "HRTF",
    "price": 6.2,
    "orderLegCollection": [
        {
            "orderLegType": "EQUITY",
            "legId": 1,
            "instrument": {
                "assetType": "EQUITY",
                "cusip": "03945R102",
                "symbol": "ACHR",
                "instrumentId": 154587181
            },
            "instruction": "BUY",
            "positionEffect": "OPENING",
            "quantity": 1.0
        }
    ],
    "orderStrategyType": "SINGLE",
    "orderId": 1005638175790,
    "cancelable": false,
    "editable": false,
    "status": "FILLED",
    "enteredTime": "2026-03-09T15:50:23+0000",
    "closeTime": "2026-03-09T15:50:23+0000",
    "tag": "TA_zhwang22gmailcom1753933248",
    "accountNumber": 29308909,
    "orderActivityCollection": [
        {
            "activityType": "EXECUTION",
            "activityId": 113893845005,
            "executionType": "FILL",
            "quantity": 1.0,
            "orderRemainingQuantity": 0.0,
            "executionLegs": [
                {
                    "legId": 1,
                    "quantity": 1.0,
                    "mismarkedQuantity": 0.0,
                    "price": 6.2,
                    "time": "2026-03-09T15:50:23+0000",
                    "instrumentId": 154587181
                }
            ]
        }
    ]
}


# Example
order_5 = buy_limit_trigger_sell_limit_sell_stop_oco_dict(
    symbol="NBIS",
    quantity=1,
    buy_limit_price=80.0,  # 14.97
    sell_limit_price=98.2,  # 15.27
    sell_stop_price=75.2,  # 11.27
    buy_duration="DAY",
    sell_duration="GOOD_TILL_CANCEL",
)

order = order_5


status_code, date, order_id = place_order(
    client=client, accountHash=hashValue, order=order
)
status_code, date, order_id 
# (201, 'Mon, 09 Mar 2026 16:05:53 GMT', '1005639387086')

order = client.order_details(hashValue, '1005639387086').json()
print(json.dumps(order, indent=4))
# Note there is no "orderActivityCollection" if the order have not been filled.
{
    "session": "NORMAL",
    "duration": "DAY",
    "orderType": "LIMIT",
    "complexOrderStrategyType": "NONE",
    "quantity": 1.0,
    "filledQuantity": 0.0,
    "remainingQuantity": 1.0,
    "requestedDestination": "AUTO",
    "destinationLinkName": "HRTF",
    "price": 80.0,
    "orderLegCollection": [
        {
            "orderLegType": "EQUITY",
            "legId": 1,
            "instrument": {
                "assetType": "EQUITY",
                "cusip": "N97284108",
                "symbol": "NBIS",
                "instrumentId": 4339891
            },
            "instruction": "BUY",
            "positionEffect": "OPENING",
            "quantity": 1.0
        }
    ],
    "orderStrategyType": "TRIGGER",
    "orderId": 1005639387086,
    "cancelable": true,
    "editable": false,
    "status": "WORKING",
    "enteredTime": "2026-03-09T16:05:52+0000",
    "tag": "TA_zhwang22gmailcom1753933248",
    "accountNumber": 29308909,
    "childOrderStrategies": [
        {
            "orderStrategyType": "OCO",
            "orderId": 1005639387087,
            "cancelable": true,
            "editable": false,
            "status": "AWAITING_PARENT_ORDER",
            "enteredTime": "2026-03-09T16:05:52+0000",
            "tag": "TA_zhwang22gmailcom1753933248",
            "accountNumber": 29308909,
            "childOrderStrategies": [
                {
                    "session": "NORMAL",
                    "duration": "GOOD_TILL_CANCEL",
                    "orderType": "STOP",
                    "complexOrderStrategyType": "NONE",
                    "quantity": 1.0,
                    "filledQuantity": 0.0,
                    "remainingQuantity": 1.0,
                    "requestedDestination": "AUTO",
                    "destinationLinkName": "AutoRoute",
                    "stopPrice": 75.2,
                    "stopType": "STANDARD",
                    "orderLegCollection": [
                        {
                            "orderLegType": "EQUITY",
                            "legId": 1,
                            "instrument": {
                                "assetType": "EQUITY",
                                "cusip": "N97284108",
                                "symbol": "NBIS",
                                "instrumentId": 4339891
                            },
                            "instruction": "SELL",
                            "positionEffect": "CLOSING",
                            "quantity": 1.0
                        }
                    ],
                    "orderStrategyType": "SINGLE",
                    "orderId": 1005639387089,
                    "cancelable": true,
                    "editable": false,
                    "status": "AWAITING_PARENT_ORDER",
                    "enteredTime": "2026-03-09T16:05:52+0000",
                    "tag": "TA_zhwang22gmailcom1753933248",
                    "accountNumber": 29308909
                },
                {
                    "session": "NORMAL",
                    "duration": "GOOD_TILL_CANCEL",
                    "orderType": "LIMIT",
                    "complexOrderStrategyType": "NONE",
                    "quantity": 1.0,
                    "filledQuantity": 0.0,
                    "remainingQuantity": 1.0,
                    "requestedDestination": "AUTO",
                    "destinationLinkName": "AutoRoute",
                    "price": 98.2,
                    "orderLegCollection": [
                        {
                            "orderLegType": "EQUITY",
                            "legId": 1,
                            "instrument": {
                                "assetType": "EQUITY",
                                "cusip": "N97284108",
                                "symbol": "NBIS",
                                "instrumentId": 4339891
                            },
                            "instruction": "SELL",
                            "positionEffect": "CLOSING",
                            "quantity": 1.0
                        }
                    ],
                    "orderStrategyType": "SINGLE",
                    "orderId": 1005639387088,
                    "cancelable": true,
                    "editable": false,
                    "status": "AWAITING_PARENT_ORDER",
                    "enteredTime": "2026-03-09T16:05:52+0000",
                    "tag": "TA_zhwang22gmailcom1753933248",
                    "accountNumber": 29308909
                }
            ]
        }
    ]
}

>>> pprint([dict(group) for group in iter_result])
[{"orders[0]['enteredTime']": '2026-03-09T19:19:43+0000',
  "orders[0]['orderId']": 1005644251905,
  "orders[0]['price']": 80.0,
  "orders[0]['status']": 'WORKING'},
 {"orders[0]['childOrderStrategies'][0]['enteredTime']": '2026-03-09T19:19:43+0000',
  "orders[0]['childOrderStrategies'][0]['orderId']": 1005644251906,
  "orders[0]['childOrderStrategies'][0]['status']": 'AWAITING_PARENT_ORDER'},
 {"orders[0]['childOrderStrategies'][0]['childOrderStrategies'][1]['enteredTime']": '2026-03-09T19:19:43+0000',
  "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][1]['orderId']": 1005644251908,
  "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][1]['status']": 'AWAITING_PARENT_ORDER'},
 {"orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['enteredTime']": '2026-03-09T19:19:43+0000',
  "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['orderId']": 1005644251907,
  "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['price']": 98.2,
  "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['status']": 'AWAITING_PARENT_ORDER'}]

# If you cancel "1005644251905", all others are cancelled too
# If yoy cancel any of the other three (1005644251906 > 1005644251908, 1005644251907 they are actually two orders), all the childorder are cancelled but not the "1005644251905".


[
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 2.0,
        "filledQuantity": 0.0,
        "remainingQuantity": 2.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "AutoRoute",
        "price": 80.0,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "N97284108",
                    "symbol": "NBIS",
                    "instrumentId": 4339891
                },
                "instruction": "BUY",
                "positionEffect": "OPENING",
                "quantity": 2.0
            }
        ],
        "orderStrategyType": "TRIGGER",
        "orderId": 1005675641156,
        "cancelable": true,
        "editable": false,
        "status": "PENDING_ACTIVATION",
        "enteredTime": "2026-03-11T20:12:15+0000",
        "tag": "TA_zhwang22gmailcom1753933248",
        "accountNumber": 29308909,
        "childOrderStrategies": [
            {
                "orderStrategyType": "OCO",
                "orderId": 1005675641157,
                "cancelable": true,
                "editable": false,
                "status": "AWAITING_PARENT_ORDER",
                "enteredTime": "2026-03-11T20:12:15+0000",
                "tag": "TA_zhwang22gmailcom1753933248",
                "accountNumber": 29308909,
                "childOrderStrategies": [
                    {
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "LIMIT",
                        "complexOrderStrategyType": "NONE",
                        "quantity": 2.0,
                        "filledQuantity": 0.0,
                        "remainingQuantity": 2.0,
                        "requestedDestination": "AUTO",
                        "destinationLinkName": "AutoRoute",
                        "price": 98.2,
                        "orderLegCollection": [
                            {
                                "orderLegType": "EQUITY",
                                "legId": 1,
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "cusip": "N97284108",
                                    "symbol": "NBIS",
                                    "instrumentId": 4339891
                                },
                                "instruction": "SELL",
                                "positionEffect": "CLOSING",
                                "quantity": 2.0
                            }
                        ],
                        "orderStrategyType": "SINGLE",
                        "orderId": 1005675641158,
                        "cancelable": true,
                        "editable": false,
                        "status": "AWAITING_PARENT_ORDER",
                        "enteredTime": "2026-03-11T20:12:15+0000",
                        "tag": "TA_zhwang22gmailcom1753933248",
                        "accountNumber": 29308909
                    },
                    {
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "STOP",
                        "complexOrderStrategyType": "NONE",
                        "quantity": 2.0,
                        "filledQuantity": 0.0,
                        "remainingQuantity": 2.0,
                        "requestedDestination": "AUTO",
                        "destinationLinkName": "AutoRoute",
                        "stopPrice": 75.2,
                        "stopType": "STANDARD",
                        "orderLegCollection": [
                            {
                                "orderLegType": "EQUITY",
                                "legId": 1,
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "cusip": "N97284108",
                                    "symbol": "NBIS",
                                    "instrumentId": 4339891
                                },
                                "instruction": "SELL",
                                "positionEffect": "CLOSING",
                                "quantity": 2.0
                            }
                        ],
                        "orderStrategyType": "SINGLE",
                        "orderId": 1005675641159,
                        "cancelable": true,
                        "editable": false,
                        "status": "AWAITING_PARENT_ORDER",
                        "enteredTime": "2026-03-11T20:12:15+0000",
                        "tag": "TA_zhwang22gmailcom1753933248",
                        "accountNumber": 29308909
                    }
                ]
            }
        ]
    },
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 1.0,
        "filledQuantity": 0.0,
        "remainingQuantity": 1.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "AutoRoute",
        "price": 0.2,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "03945R102",
                    "symbol": "ACHR",
                    "instrumentId": 154587181
                },
                "instruction": "BUY",
                "positionEffect": "OPENING",
                "quantity": 1.0
            }
        ],
        "orderStrategyType": "SINGLE",
        "orderId": 1005675641153,
        "cancelable": true,
        "editable": true,
        "status": "PENDING_ACTIVATION",
        "enteredTime": "2026-03-11T20:12:07+0000",
        "tag": "TA_zhwang22gmailcom1753933248",
        "accountNumber": 29308909
    },


]




>>> resp = client.quotes("IREN").json()
>>> print(json.dumps(resp, indent=4))

{
    "IREN": {
        "assetMainType": "EQUITY",
        "assetSubType": "COE",
        "quoteType": "NBBO",
        "realtime": true,
        "ssid": 77026444,
        "symbol": "IREN",
        "extended": {
            "askPrice": 0.0,
            "askSize": 0,
            "bidPrice": 0.0,
            "bidSize": 0,
            "lastPrice": 41.02,
            "lastSize": 100,
            "mark": 0.0,
            "quoteTime": 1773388800000,
            "totalVolume": 0,
            "tradeTime": 1773388785000
        },
        "fundamental": {
            "avg10DaysVolume": 35632658.0,
            "avg1YearVolume": 30840034.0,
            "divAmount": 0.0,
            "divFreq": 0,
            "divPayAmount": 0.0,
            "divYield": 0.0,
            "eps": 0.39,
            "fundLeverageFactor": 0.0,
            "lastEarningsDate": "2026-02-05T00:00:00Z",
            "peRatio": 31.00525,
            "sharesOutstanding": 332280383
        },
        "quote": {
            "52WeekHigh": 76.87,
            "52WeekLow": 5.125,
            "askMICId": "ARCX",
            "askPrice": 41.55,
            "askSize": 500,
            "askTime": 1773435300608,
            "bidMICId": "ARCX",
            "bidPrice": 41.44,
            "bidSize": 100,
            "bidTime": 1773435419662,
            "closePrice": 41.37,
            "highPrice": 44.15,
            "lastMICId": "XADF",
            "lastPrice": 41.4401,
            "lastSize": 1000,
            "lowPrice": 41.0,
            "mark": 41.55,
            "markChange": 0.18,
            "markPercentChange": 0.4350979,
            "netChange": 0.0701,
            "netPercentChange": 0.16944646,
            "openPrice": 42.625,
            "postMarketChange": -0.1399,
            "postMarketPercentChange": -0.33645984,
            "quoteTime": 1773435419662,
            "securityStatus": "Normal",
            "totalVolume": 34316087,
            "tradeTime": 1773435457586
        },
        "reference": {
            "cusip": "Q4982L109",
            "description": "IREN LTD",
            "exchange": "Q",
            "exchangeName": "NASDAQ",
            "isHardToBorrow": false,
            "isShortable": true,
            "htbQuantity": 396434,
            "htbRate": 0.0
        },
        "regular": {
            "regularMarketLastPrice": 41.58,
            "regularMarketLastSize": 1160351,
            "regularMarketNetChange": 0.21,
            "regularMarketPercentChange": 0.50761421,
            "regularMarketTradeTime": 1773432000315
        }
    }
}

["quote"]["closePrice": 41.37,