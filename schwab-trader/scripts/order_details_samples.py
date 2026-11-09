# After you place a sell_limit_sell_stoplimit_oco order
# thinkorswim app > order history > view thinkLog notes on order > "TA_zhwang22gmailcom1753933248 SELL -380 IREN @45.00 LMT OCO #1005667584230"
# "TA_zhwang22gmailcom1753933248 SELL -380 IREN @39.80 STPLMT 40.00 OCO #1005667584230"


# Real Example - limit sell order triggers limit buy order.  
    {
    "session": "NORMAL",
    "duration": "DAY",
    "orderType": "LIMIT",
    "complexOrderStrategyType": "NONE",
    "quantity": 100.0,
    "filledQuantity": 0.0,
    "remainingQuantity": 100.0,
    "requestedDestination": "AUTO",
    "destinationLinkName": "AutoRoute",
    "price": 138.0,
    "orderLegCollection": [
        {
            "orderLegType": "EQUITY",
            "legId": 1,
            "instrument": {
                "assetType": "EQUITY",
                "cusip": "N97284108",
                "symbol": "NBIS",
                "uniformSymbol": "NBIS",
                "instrumentId": 4339891
            },
            "instruction": "SELL",
            "positionEffect": "CLOSING",
            "quantity": 100.0
        }
    ],
    "orderStrategyType": "TRIGGER",
    "orderId": 1008594108571,
    "cancelable": true,
    "editable": false,
    "status": "PENDING_ACTIVATION",
    "enteredTime": "2026-11-07T15:26:42+0000",
    "tag": "TA_zhwang22gmailcom1753933248",
    "accountNumber": 29308909,
    "childOrderStrategies": [
        {
            "session": "NORMAL",
            "duration": "DAY",
            "orderType": "LIMIT",
            "complexOrderStrategyType": "NONE",
            "quantity": 100.0,
            "filledQuantity": 0.0,
            "remainingQuantity": 100.0,
            "requestedDestination": "AUTO",
            "destinationLinkName": "AutoRoute",
            "price": 123.0,
            "orderLegCollection": [
                {
                    "orderLegType": "EQUITY",
                    "legId": 1,
                    "instrument": {
                        "assetType": "EQUITY",
                        "cusip": "N97284108",
                        "symbol": "NBIS",
                        "uniformSymbol": "NBIS",
                        "instrumentId": 4339891
                    },
                    "instruction": "BUY",
                    "positionEffect": "OPENING",
                    "quantity": 100.0
                }
            ],
            "orderStrategyType": "SINGLE",
            "orderId": 1008594108572,
            "cancelable": true,
            "editable": false,
            "status": "AWAITING_PARENT_ORDER",
            "enteredTime": "2026-11-07T15:26:42+0000",
            "tag": "TA_zhwang22gmailcom1753933248",
            "accountNumber": 29308909
        }
    ]
}

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
order = client.order_details(hashValue, "1005638175790").json()
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
                "instrumentId": 154587181,
            },
            "instruction": "BUY",
            "positionEffect": "OPENING",
            "quantity": 1.0,
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
                    "instrumentId": 154587181,
                }
            ],
        }
    ],
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

order = client.order_details(hashValue, "1005639387086").json()
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
                "instrumentId": 4339891,
            },
            "instruction": "BUY",
            "positionEffect": "OPENING",
            "quantity": 1.0,
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
                                "instrumentId": 4339891,
                            },
                            "instruction": "SELL",
                            "positionEffect": "CLOSING",
                            "quantity": 1.0,
                        }
                    ],
                    "orderStrategyType": "SINGLE",
                    "orderId": 1005639387089,
                    "cancelable": true,
                    "editable": false,
                    "status": "AWAITING_PARENT_ORDER",
                    "enteredTime": "2026-03-09T16:05:52+0000",
                    "tag": "TA_zhwang22gmailcom1753933248",
                    "accountNumber": 29308909,
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
                                "instrumentId": 4339891,
                            },
                            "instruction": "SELL",
                            "positionEffect": "CLOSING",
                            "quantity": 1.0,
                        }
                    ],
                    "orderStrategyType": "SINGLE",
                    "orderId": 1005639387088,
                    "cancelable": true,
                    "editable": false,
                    "status": "AWAITING_PARENT_ORDER",
                    "enteredTime": "2026-03-09T16:05:52+0000",
                    "tag": "TA_zhwang22gmailcom1753933248",
                    "accountNumber": 29308909,
                },
            ],
        }
    ],
}

# >>> pprint([dict(group) for group in iter_result])
[
    {
        "orders[0]['enteredTime']": "2026-03-09T19:19:43+0000",
        "orders[0]['orderId']": 1005644251905,
        "orders[0]['price']": 80.0,
        "orders[0]['status']": "WORKING",
    },
    {
        "orders[0]['childOrderStrategies'][0]['enteredTime']": "2026-03-09T19:19:43+0000",
        "orders[0]['childOrderStrategies'][0]['orderId']": 1005644251906,
        "orders[0]['childOrderStrategies'][0]['status']": "AWAITING_PARENT_ORDER",
    },
    {
        "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][1]['enteredTime']": "2026-03-09T19:19:43+0000",
        "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][1]['orderId']": 1005644251908,
        "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][1]['status']": "AWAITING_PARENT_ORDER",
    },
    {
        "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['enteredTime']": "2026-03-09T19:19:43+0000",
        "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['orderId']": 1005644251907,
        "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['price']": 98.2,
        "orders[0]['childOrderStrategies'][0]['childOrderStrategies'][0]['status']": "AWAITING_PARENT_ORDER",
    },
]

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
                    "instrumentId": 4339891,
                },
                "instruction": "BUY",
                "positionEffect": "OPENING",
                "quantity": 2.0,
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
                                    "instrumentId": 4339891,
                                },
                                "instruction": "SELL",
                                "positionEffect": "CLOSING",
                                "quantity": 2.0,
                            }
                        ],
                        "orderStrategyType": "SINGLE",
                        "orderId": 1005675641158,
                        "cancelable": true,
                        "editable": false,
                        "status": "AWAITING_PARENT_ORDER",
                        "enteredTime": "2026-03-11T20:12:15+0000",
                        "tag": "TA_zhwang22gmailcom1753933248",
                        "accountNumber": 29308909,
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
                                    "instrumentId": 4339891,
                                },
                                "instruction": "SELL",
                                "positionEffect": "CLOSING",
                                "quantity": 2.0,
                            }
                        ],
                        "orderStrategyType": "SINGLE",
                        "orderId": 1005675641159,
                        "cancelable": true,
                        "editable": false,
                        "status": "AWAITING_PARENT_ORDER",
                        "enteredTime": "2026-03-11T20:12:15+0000",
                        "tag": "TA_zhwang22gmailcom1753933248",
                        "accountNumber": 29308909,
                    },
                ],
            }
        ],
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
                    "instrumentId": 154587181,
                },
                "instruction": "BUY",
                "positionEffect": "OPENING",
                "quantity": 1.0,
            }
        ],
        "orderStrategyType": "SINGLE",
        "orderId": 1005675641153,
        "cancelable": true,
        "editable": true,
        "status": "PENDING_ACTIVATION",
        "enteredTime": "2026-03-11T20:12:07+0000",
        "tag": "TA_zhwang22gmailcom1753933248",
        "accountNumber": 29308909,
    },
]


# Canceled example

example = {
    "session": "NORMAL",
    "duration": "DAY",
    "orderType": "LIMIT",
    "complexOrderStrategyType": "NONE",
    "quantity": 388.0,
    "filledQuantity": 0.0,
    "remainingQuantity": 0.0,
    "requestedDestination": "AUTO",
    "destinationLinkName": "HRTF",
    "price": 44.88,
    "orderLegCollection": [
        {
            "orderLegType": "EQUITY",
            "legId": 1,
            "instrument": {
                "assetType": "EQUITY",
                "cusip": "Q4982L109",
                "symbol": "IREN",
                "instrumentId": 156189251,
            },
            "instruction": "SELL",
            "positionEffect": "CLOSING",
            "quantity": 388.0,
        }
    ],
    "orderStrategyType": "SINGLE",
    "orderId": 1005706320014,
    "cancelable": false,
    "editable": false,
    "status": "CANCELED",
    "enteredTime": "2026-03-16T13:02:39+0000",
    "closeTime": "2026-03-16T16:05:51+0000",
    "accountNumber": 29308909,
    "orderActivityCollection": [
        {
            "activityType": "EXECUTION",
            "activityId": 114427119871,
            "executionType": "CANCELED",
            "quantity": 388.0,
            "orderRemainingQuantity": 0.0,
            "executionLegs": [
                {
                    "legId": 1,
                    "quantity": 388.0,
                    "mismarkedQuantity": 0.0,
                    "price": 0.0,
                    "time": "2026-03-16T16:05:51+0000",
                    "instrumentId": 156189251,
                }
            ],
        }
    ],
}


# Filled examples
# buy ACHR at 6.16 filled
# "orderStrategyType": "SINGLE",
# "orderLegCollection" -- list of dictionaries
#     "instruction"
#     "quantity"
#     "instrument"
#         "symbol"
# "orderActivityCollection" -- list of dictionaries
#     "executionType"
#     "executionLegs"
#         "quantity"
#         "price"


[
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 2900.0,
        "filledQuantity": 2900.0,
        "remainingQuantity": 0.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "HRTF",
        "price": 6.16,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "03945R102",
                    "symbol": "ACHR",
                    "instrumentId": 154587181,
                },
                "instruction": "BUY",
                "positionEffect": "OPENING",
                "quantity": 2900.0,
            }
        ],
        "orderStrategyType": "SINGLE",
        "orderId": 1005734504839,
        "cancelable": false,
        "editable": false,
        "status": "FILLED",
        "enteredTime": "2026-03-18T13:57:02+0000",
        "closeTime": "2026-03-18T14:11:15+0000",
        "accountNumber": 29308909,
        "orderActivityCollection": [
            {
                "activityType": "EXECUTION",
                "activityId": 114597718421,
                "executionType": "FILL",
                "quantity": 1782.0,
                "orderRemainingQuantity": 1118.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 1782.0,
                        "mismarkedQuantity": 0.0,
                        "price": 6.16,
                        "time": "2026-03-18T14:11:14+0000",
                        "instrumentId": 154587181,
                    }
                ],
            },
            {
                "activityType": "EXECUTION",
                "activityId": 114597718438,
                "executionType": "FILL",
                "quantity": 724.0,
                "orderRemainingQuantity": 0.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 724.0,
                        "mismarkedQuantity": 0.0,
                        "price": 6.16,
                        "time": "2026-03-18T14:11:15+0000",
                        "instrumentId": 154587181,
                    }
                ],
            },
            {
                "activityType": "EXECUTION",
                "activityId": 114597718423,
                "executionType": "FILL",
                "quantity": 394.0,
                "orderRemainingQuantity": 724.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 394.0,
                        "mismarkedQuantity": 0.0,
                        "price": 6.16,
                        "time": "2026-03-18T14:11:14+0000",
                        "instrumentId": 154587181,
                    }
                ],
            },
        ],
    },
    # sell ACHR at 6.26 filled
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 2900.0,
        "filledQuantity": 2900.0,
        "remainingQuantity": 0.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "HRTF",
        "price": 6.26,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "03945R102",
                    "symbol": "ACHR",
                    "instrumentId": 154587181,
                },
                "instruction": "SELL",
                "positionEffect": "CLOSING",
                "quantity": 2900.0,
            }
        ],
        "orderStrategyType": "SINGLE",
        "orderId": 1005731616903,
        "cancelable": false,
        "editable": false,
        "status": "FILLED",
        "enteredTime": "2026-03-17T19:55:24+0000",
        "closeTime": "2026-03-17T19:55:42+0000",
        "accountNumber": 29308909,
        "orderActivityCollection": [
            {
                "activityType": "EXECUTION",
                "activityId": 114565118039,
                "executionType": "FILL",
                "quantity": 2900.0,
                "orderRemainingQuantity": 0.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 2900.0,
                        "mismarkedQuantity": 0.0,
                        "price": 6.26,
                        "time": "2026-03-17T19:55:42+0000",
                        "instrumentId": 154587181,
                    }
                ],
            }
        ],
    },
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 2900.0,
        "filledQuantity": 2900.0,
        "remainingQuantity": 0.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "ETMM",
        "price": 6.28,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "03945R102",
                    "symbol": "ACHR",
                    "instrumentId": 154587181,
                },
                "instruction": "SELL",
                "positionEffect": "CLOSING",
                "quantity": 2900.0,
            }
        ],
        "orderStrategyType": "SINGLE",
        "orderId": 1005720758543,
        "cancelable": false,
        "editable": false,
        "status": "FILLED",
        "enteredTime": "2026-03-17T13:43:39+0000",
        "closeTime": "2026-03-17T13:43:39+0000",
        "tag": "TA_zhwang22gmailcom1753933248",
        "accountNumber": 29308909,
        "orderActivityCollection": [
            {
                "activityType": "EXECUTION",
                "activityId": 114493627325,
                "executionType": "FILL",
                "quantity": 2900.0,
                "orderRemainingQuantity": 0.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 2900.0,
                        "mismarkedQuantity": 0.0,
                        "price": 6.285,
                        "time": "2026-03-17T13:43:39+0000",
                        "instrumentId": 154587181,
                    }
                ],
            }
        ],
    },
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 2900.0,
        "filledQuantity": 2900.0,
        "remainingQuantity": 0.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "JNST",
        "price": 6.6,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "03945R102",
                    "symbol": "ACHR",
                    "instrumentId": 154587181,
                },
                "instruction": "BUY",
                "positionEffect": "OPENING",
                "quantity": 2900.0,
            }
        ],
        "orderStrategyType": "SINGLE",
        "orderId": 1005720758390,
        "cancelable": false,
        "editable": false,
        "status": "FILLED",
        "enteredTime": "2026-03-17T13:42:06+0000",
        "closeTime": "2026-03-17T13:42:06+0000",
        "tag": "TA_zhwang22gmailcom1753933248",
        "accountNumber": 29308909,
        "orderActivityCollection": [
            {
                "activityType": "EXECUTION",
                "activityId": 114491636337,
                "executionType": "FILL",
                "quantity": 2900.0,
                "orderRemainingQuantity": 0.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 2900.0,
                        "mismarkedQuantity": 0.0,
                        "price": 6.2798,
                        "time": "2026-03-17T13:42:06+0000",
                        "instrumentId": 154587181,
                    }
                ],
            }
        ],
    },
    # Buy (filled) trigger OCO (working)
    # "orderStrategyType": "TRIGGER"
    # "orderLegCollection" -- list of dictionaries
    #     "instruction"
    #     "quantity"
    #     "instrument"
    #         "symbol"
    # "orderActivityCollection" -- list of dictionaries
    #     "executionType"
    #     "executionLegs"
    #         "quantity"
    #         "price"
    # "childOrderStrategies" -- list of dictionaries
    #     "orderStrategyType": "OCO"
    #     "childOrderStrategies" -- list of dictionaries
    #            "orderStrategyType": "SINGLE"
    #            "orderLegCollection"
    #                "instrument"
    #                    "symbol"
    #            No "orderActivityCollection" as its status is working
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 400.0,
        "filledQuantity": 400.0,
        "remainingQuantity": 0.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "NITE",
        "price": 44.3,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "Q4982L109",
                    "symbol": "IREN",
                    "instrumentId": 156189251,
                },
                "instruction": "BUY",
                "positionEffect": "OPENING",
                "quantity": 400.0,
            }
        ],
        "orderStrategyType": "TRIGGER",
        "orderId": 1005719933423,
        "cancelable": false,
        "editable": false,
        "status": "FILLED",
        "enteredTime": "2026-03-17T13:34:53+0000",
        "closeTime": "2026-03-17T13:34:53+0000",
        "tag": "TA_zhwang22gmailcom1753933248",
        "accountNumber": 29308909,
        "orderActivityCollection": [
            {
                "activityType": "EXECUTION",
                "activityId": 114489924721,
                "executionType": "FILL",
                "quantity": 400.0,
                "orderRemainingQuantity": 0.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 400.0,
                        "mismarkedQuantity": 0.0,
                        "price": 44.27,
                        "time": "2026-03-17T13:34:53+0000",
                        "instrumentId": 156189251,
                    }
                ],
            }
        ],
        "childOrderStrategies": [
            {
                "orderStrategyType": "OCO",
                "orderId": 1005719933424,
                "cancelable": true,
                "editable": false,
                "status": "WORKING",
                "enteredTime": "2026-03-17T13:34:53+0000",
                "tag": "TA_zhwang22gmailcom1753933248",
                "accountNumber": 29308909,
                "childOrderStrategies": [
                    {
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "STOP",
                        "complexOrderStrategyType": "NONE",
                        "quantity": 400.0,
                        "filledQuantity": 0.0,
                        "remainingQuantity": 400.0,
                        "requestedDestination": "AUTO",
                        "destinationLinkName": "HRTF",
                        "stopPrice": 40.0,
                        "stopType": "STANDARD",
                        "orderLegCollection": [
                            {
                                "orderLegType": "EQUITY",
                                "legId": 1,
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "cusip": "Q4982L109",
                                    "symbol": "IREN",
                                    "instrumentId": 156189251,
                                },
                                "instruction": "SELL",
                                "positionEffect": "CLOSING",
                                "quantity": 400.0,
                            }
                        ],
                        "orderStrategyType": "SINGLE",
                        "orderId": 1005719933426,
                        "cancelable": true,
                        "editable": false,
                        "status": "WORKING",
                        "enteredTime": "2026-03-17T13:34:53+0000",
                        "tag": "TA_zhwang22gmailcom1753933248",
                        "accountNumber": 29308909,
                    },
                    {
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "LIMIT",
                        "complexOrderStrategyType": "NONE",
                        "quantity": 400.0,
                        "filledQuantity": 0.0,
                        "remainingQuantity": 400.0,
                        "requestedDestination": "AUTO",
                        "destinationLinkName": "HRTF",
                        "price": 47.88,
                        "orderLegCollection": [
                            {
                                "orderLegType": "EQUITY",
                                "legId": 1,
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "cusip": "Q4982L109",
                                    "symbol": "IREN",
                                    "instrumentId": 156189251,
                                },
                                "instruction": "SELL",
                                "positionEffect": "CLOSING",
                                "quantity": 400.0,
                            }
                        ],
                        "orderStrategyType": "SINGLE",
                        "orderId": 1005719933425,
                        "cancelable": true,
                        "editable": false,
                        "status": "WORKING",
                        "enteredTime": "2026-03-17T13:34:53+0000",
                        "tag": "TA_zhwang22gmailcom1753933248",
                        "accountNumber": 29308909,
                    },
                ],
            }
        ],
    },
    # Sell filled
    {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "complexOrderStrategyType": "NONE",
        "quantity": 388.0,
        "filledQuantity": 388.0,
        "remainingQuantity": 0.0,
        "requestedDestination": "AUTO",
        "destinationLinkName": "HRTF",
        "price": 44.88,
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "legId": 1,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": "Q4982L109",
                    "symbol": "IREN",
                    "instrumentId": 156189251,
                },
                "instruction": "SELL",
                "positionEffect": "CLOSING",
                "quantity": 388.0,
            }
        ],
        "orderStrategyType": "SINGLE",
        "orderId": 1005712534968,
        "cancelable": false,
        "editable": false,
        "status": "FILLED",
        "enteredTime": "2026-03-16T16:07:13+0000",
        "closeTime": "2026-03-16T19:09:44+0000",
        "accountNumber": 29308909,
        "orderActivityCollection": [
            {
                "activityType": "EXECUTION",
                "activityId": 114459734819,
                "executionType": "FILL",
                "quantity": 388.0,
                "orderRemainingQuantity": 0.0,
                "executionLegs": [
                    {
                        "legId": 1,
                        "quantity": 388.0,
                        "mismarkedQuantity": 0.0,
                        "price": 44.88,
                        "time": "2026-03-16T19:09:44+0000",
                        "instrumentId": 156189251,
                    }
                ],
            }
        ],
    },
]






# The following complexOrderStrategyType examples are provided by ChatGPT.
    # 1. NONE
    # Description: No complex strategy classification.
    # Example: Buy 100 shares of XYZ.
    {
      "complexOrderStrategyType": "NONE",
      "orderType": "LIMIT",
      "orderLegCollection": [
        {
          "instruction": "BUY",
          "quantity": 100,
          "instrument": {
            "symbol": "XYZ",
            "assetType": "EQUITY"
          }
        }
      ]
    }

    # 2. COVERED
    # Description: Covered option position, typically a covered call. Existing underlying shares may be held in the account rather than included as a new order leg.
    # Example: Sell one call against 100 owned shares.
    {
      "complexOrderStrategyType": "COVERED",
      "orderType": "NET_CREDIT",
      "orderLegCollection": [
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 3. VERTICAL
    # Description: Two options, same underlying, expiration and option type, different strikes.
    # Example: Bull call spread.
    {
      "complexOrderStrategyType": "VERTICAL",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 4. BACK_RATIO
    # Description: Ratio backspread. More options are purchased than sold.
    # Example: 1x2 call backspread.
    {
      "complexOrderStrategyType": "BACK_RATIO",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 5. CALENDAR
    # Description: Same strike, different expiration dates.
    # Example: Sell near-term call and buy longer-term call.
    {
      "complexOrderStrategyType": "CALENDAR",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  270115C00100000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 6. DIAGONAL
    # Description: Different strikes and expiration dates.
    {
      "complexOrderStrategyType": "DIAGONAL",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00105000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  270115C00100000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 7. STRADDLE
    # Description: Same strike and expiration, one call and one put.
    # Example: Long ATM straddle.
    {
      "complexOrderStrategyType": "STRADDLE",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00100000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 8. STRANGLE
    # Description: Different call and put strikes, same expiration.
    {
      "complexOrderStrategyType": "STRANGLE",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00090000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 9. COLLAR_SYNTHETIC
    # Description: Synthetic collar-like construction using options.
    # Example: Synthetic long stock combined with protective put and short call.
    {
      "complexOrderStrategyType": "COLLAR_SYNTHETIC",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00090000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # Validation note: Confirm the broker's precise definition of this classification.
    # 10. BUTTERFLY
    # Description: Three strikes, typically 1-2-1 quantities.
    {
      "complexOrderStrategyType": "BUTTERFLY",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00090000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 11. CONDOR
    # Description: Four strikes, typically four options of equal quantity.
    {
      "complexOrderStrategyType": "CONDOR",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00085000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00095000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00105000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00115000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 12. IRON_CONDOR
    # Description: Two put legs and two call legs, usually a credit spread on each side.
    {
      "complexOrderStrategyType": "IRON_CONDOR",
      "orderType": "NET_CREDIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00085000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00090000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00115000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 13. VERTICAL_ROLL
    # Description: Close an existing vertical and open a replacement vertical.
    {
      "complexOrderStrategyType": "VERTICAL_ROLL",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "SELL_TO_CLOSE",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_CLOSE",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00105000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00115000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # Validation note: Verify support for the roll classification and the combined close/open transaction.
    # 14. COLLAR_WITH_STOCK
    # Description: Long stock, long protective put and short covered call.
    {
      "complexOrderStrategyType": "COLLAR_WITH_STOCK",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY",
          "quantity": 100,
          "instrument": {
            "symbol": "XYZ",
            "assetType": "EQUITY"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00095000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 15. DOUBLE_DIAGONAL
    # Description: A call diagonal combined with a put diagonal.
    {
      "complexOrderStrategyType": "DOUBLE_DIAGONAL",
      "orderType": "NET_CREDIT",
      "orderLegCollection": [
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00105000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  270115C00110000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00095000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  270115P00090000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 16. UNBALANCED_BUTTERFLY
    # Description: Butterfly-like spread with unequal wing quantities.
    {
      "complexOrderStrategyType": "UNBALANCED_BUTTERFLY",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00090000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 3,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 17. UNBALANCED_CONDOR
    # Description: Condor-like construction with unequal quantities.
    {
      "complexOrderStrategyType": "UNBALANCED_CONDOR",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00085000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00095000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00105000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00115000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 18. UNBALANCED_IRON_CONDOR
    # Description: Iron condor with unequal quantities or wing structures.
    {
      "complexOrderStrategyType": "UNBALANCED_IRON_CONDOR",
      "orderType": "NET_CREDIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00085000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218P00090000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00115000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 19. UNBALANCED_VERTICAL_ROLL
    # Description: Vertical roll with unequal quantities in the replacement spread.
    {
      "complexOrderStrategyType": "UNBALANCED_VERTICAL_ROLL",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "SELL_TO_CLOSE",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00100000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_CLOSE",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00110000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 3,
          "instrument": {
            "symbol": "XYZ  270115C00105000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  270115C00115000",
            "assetType": "OPTION"
          }
        }
      ]
    }

    # 20. MUTUAL_FUND_SWAP
    # Description: Mutual fund exchange. This is not a conventional options strategy.
    # Schematic only — not a confirmed Schwab order payload.
    {
      "complexOrderStrategyType": "MUTUAL_FUND_SWAP",
      "orderStrategyType": "SINGLE",
      "orderLegCollection": [
        {
          "instruction": "EXCHANGE",
          "quantity": 10000,
          "instrument": {
            "symbol": "FUND_A",
            "assetType": "MUTUAL_FUND"
          }
        }
      ]
    }

    # Validation note: Mutual fund exchanges have separate request semantics. Verify the actual endpoint schema, destination fund fields and supported instructions.
    # 21. CUSTOM
    # Description: Custom combination that does not match a predefined strategy.
    {
      "complexOrderStrategyType": "CUSTOM",
      "orderType": "NET_DEBIT",
      "orderLegCollection": [
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218C00095000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 2,
          "instrument": {
            "symbol": "XYZ  261218C00105000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "BUY_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00090000",
            "assetType": "OPTION"
          }
        },
        {
          "instruction": "SELL_TO_OPEN",
          "quantity": 1,
          "instrument": {
            "symbol": "XYZ  261218P00085000",
            "assetType": "OPTION"
          }
        }
      ]
    }