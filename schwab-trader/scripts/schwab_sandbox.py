

import os
import schwabdev

from dotenv import load_dotenv

load_dotenv()

client = schwabdev.Client(
    os.getenv("APP_KEY"),
    os.getenv("APP_SECRET"),
    os.getenv("CALLBACK_URL")
    )

streamer = schwabdev.Stream(client)

symbols = ["WDC", "MU"]
symbols_str = ",".join(symbols)

fields = ",".join(str(x) for x in [
    0, 1, 2, 3,
    4, 5,
    8, 9,
    10, 11, 12,
    17, 18,
    29, 31, 32, 33,
    34, 35
])

streamer.start(receiver=print)

streamer.send(
    # Market data
    streamer.level_one_equities(
        symbols_str,
        fields
    )
)

streamer.send(
    # Specific Schwab account data
    streamer.account_activity(
        "Account Activity",
        "0,1,2,3"
    )
)

input("Press ENTER to stop...\n")

streamer.stop()




import json
from datetime import datetime


def receiver(message):
    try:
        data = json.loads(message)
    except Exception:
        print(message)
        return

    print(json.dumps(data, indent=2))

streamer.start(receiver=receiver)



# Level One Equities Quotes, fields for equity quotes.
# 0       Ticker symbol
# 1       Bid price
# 2       Ask price
# 3       Last trade price
# 4       Size of the highest bid
# 5       Size of the lowest ask
# 6       Exchange ID of the lowest ask
# 7       Exchange ID of the highest bid
# 8       Total volume trade to date
# 9       Size of the last trade
# 10      Daily high price
# 11      Daily low price
# 12      Previous close price
# 13      Exchange ID
# 14      Is this equity marginable?
# 15      Description
# 16      Exchange ID of the last trade
# 17      Today’s open price
# 18      Net change
# 19      52 week high price
# 20      52 week low price
# 21      P/E ratio
# 22      Dividend amount
# 23      Dividend yield
# 24      ETF net asset value
# 25      Exchange name
# 26      Dividend date
# 27      Is this a regular market quote?
# 28      Is this a regular market trade?
# 29      Regular market last price
# 30      Regular market last size
# 31      Regular market net change
# 32      Security status
# 33      Mark
# 34      Quote time in milliseconds
# 35      Last trade time in milliseconds
# 36      Regular market trade time in milliseconds
# 37      Bid time in millis
# 38      Ask time in millis
# 39      Ask MIC ID
# 40      Bid MIC ID
# 41      Last trade MIC ID
# 42      Net change in percent
# 43      Regular market change in percent
# 44      Mark change
# 45      Mark change in percent
# 46      HTB quantity
# 47      HTB rate
# 48      Is this equity hard to borrow?
# 49      Is this equity shortable
# 50      Post market net change
# 51      Post market net change percent


{"data":[
    {"service":"LEVELONE_EQUITIES", 
     "timestamp":1786378769961,
     "command":"SUBS",
     "content":[
         {"key":"MU",
          "1":878.66,
          "2":879,
          "3":878.83,
          "5":360,
          "8":16493307,
          "9":100,
          "18":1.26,
          "29":878.83,
          "31":1.26,
          "33":878.83,
          "34":1786378769486,
          "35":1786378769407
          },
          {"key":"WDC",
           "3":445.71,
           "8":3509813,
           "9":200,
           "18":11.41,
           "29":445.71,
           "31":11.41,
           "33":445.71,
           "35":1786378768994
           }
           ]
           }
           ]
           }




"""
Example of translating field numbers to field names in a streaming response.
"""

import logging
import os
from dotenv import load_dotenv
import schwabdev
import json
import datetime



def translate_data(response) -> list[str]:
    """
    Translate field numbers to field names

    Returns:
        list[str]: list of field names
    """
    for item in response.get("data", []):
        if isinstance(item, dict):
            service = item.get("service", None)
            timestamp = item.get("timestamp", None)
            content = item.get("content", None)
            if timestamp:
                item["timestamp"] = datetime.datetime.fromtimestamp(timestamp / 1000)

            if service and content and service.startswith("LEVELONE_"):
                if isinstance(content, list):
                    for quote in content:
                        for field, value in quote.copy().items():
                            if field.isdigit():
                                new_field = translate_field(service, field)
                                quote[new_field] = quote.pop(field)                           
                                      
    return response
    
    
def translate_field(service: str, field: str|int) -> str:
    """
    Translate field number to field name

    Args:
        field (str|int): field number
    Returns:
        str: field name
    """
    mapping = schwabdev.stream_fields.get(service.upper(), None)
    if mapping is None:
        return str(field)
    try:
        if isinstance(mapping, dict):
            return mapping.get(field, str(field))
        elif isinstance(mapping, list):
            index = int(field)
            if 0 <= index < len(mapping):
                return mapping[index]
            else:
                return str(field)
        else:
            return str(field)
    except Exception:
        return str(field)

if __name__ == "__main__":
    print("Welcome to Schwabdev, The Unofficial Schwab API Python Wrapper!")
    print("Documentation: https://tylerebowers.github.io/Schwabdev/")

    # place your app key and app secret in the .env file
    load_dotenv()  # load environment variables from .env file

    

    # set logging level
    logging.basicConfig(level=logging.INFO)

    client = schwabdev.Client(
    os.getenv("APP_KEY"),
    os.getenv("APP_SECRET"),
    os.getenv("CALLBACK_URL")
    )
    streamer = schwabdev.Stream(client)

    def response_handler(msg):
        translated = translate_data(json.loads(msg))
        print(translated)


    streamer.start(response_handler)
    streamer.start(receiver=print)

    streamer.send(
        streamer.level_one_equities(
            "AMD,INTC", "0,1,2,3,4,5,6,7,8,9,10,11,12,13"
            )
            )
    streamer.send(
        streamer.account_activity(
            "Account Activity", "0,1,2,3"
            )
            )
    # streamer.send(streamer.nyse_book(["F"], "0,1,2,3,4,5,6,7,8"))

    import time
    time.sleep(30)
    streamer.stop()