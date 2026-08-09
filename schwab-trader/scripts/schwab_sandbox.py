

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

symbols = ["AAPL", "NVDA", "SPY"]
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

