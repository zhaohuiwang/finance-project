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
