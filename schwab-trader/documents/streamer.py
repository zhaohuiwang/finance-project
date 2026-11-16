import os
import time

from dotenv import load_dotenv
import schwabdev

load_dotenv()


client = schwabdev.Client(
    os.getenv("APP_KEY"), os.getenv("APP_SECRET"), os.getenv("CALLBACK_URL")
)

# define a variable for the steamer:
streamer = schwabdev.Stream(client)

symbols_str = "AMD, INTC"
loe_fields_str = "0,3,8,10,11,12,19,20,21"
act_fields_Str = "0,1,2,3"


streamer.send(streamer.level_one_equities(symbols_str, loe_fields_str))
# 0: Symbol, 1: BidPrice, 2: AskPrice, 3: Last tradePrice, 8:TotalVolumeTradedToday, 10: Today'sHighPrice, 11: Today'sLowPrice, 12: PreviousClosePrice,18: NetChange, 19: 52-week-high, 20: 52-week-low, 21: P/E

streamer.send(streamer.account_activity("Account Activity", act_fields_Str))
# 0: SubscriptionKey,Symbol, 1: Account, 2: MessageType, 3: MessageData.
# MessageType ['SUBSCRIBED','ORDER_ENTRY','ORDER_CANCEL','ORDER_FILL','ORDER_PARTIAL_FILL']

streamer.start(receiver=print)
# receiver=print show everything including response, data, notify categories. simply prints every message Schwab server sends to your receiver.
# 1. response — result of your request. "I received your subscription request, and it succeeded."
# 2. data — actual streaming data. "Here is new data for your subscription."
# 3. notify — connection/system notification. "The streaming connection is still alive."

time.sleep(30)
streamer.stop()

