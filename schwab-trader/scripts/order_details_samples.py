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
