""" "
Purpose: Real-time streaming and visualization of stock market data using Schwab's streaming API and Dash/Matplotlib for live charting.

Data Buffers
Stores time, price, and volume in deque buffers with a fixed MAX_POINTS to prevent memory overflow.
Optional OHLC buffers for candlestick aggregation.

Indicators Computed
Moving Averages (MA20, MA50) for smoothing prices.
VWAP (Volume-Weighted Average Price) for volume-weighted price benchmark.

Live Plotting / Dashboard
Uses Dash or Matplotlib in interactive mode for real-time chart updates.
Plots: Price line, VWAP line, optional candlestick + volume bars
Chart refresh interval controlled by dcc.Interval or time.sleep() in Matplotlib loop.

Threaded Consumer
A background thread consumes streaming messages, updates buffers, and prints debug information.
Ensures the UI thread remains responsive.

Command-Line Arguments
Symbols can be passed via argparse, or just the default list:
```Bash
python dashboard.py AMD NVDA AAPL
python dashboard.py
```
Supports nargs="+" to require at least one symbol.

"""

import argparse
import json
import os
import threading
from collections import deque
from datetime import datetime

import pandas as pd
import dotenv
import schwabdev

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go

parser = argparse.ArgumentParser(description="Live Trading Dashboard")
parser.add_argument(
    "symbols",
    nargs="*",
    default=["AMD", "NVDA", "AAPL"],
    help="List of symbols to track, e.g. AMD NVDA AAPL",
)
args = parser.parse_args()

# ---------------- SETTINGS ----------------

SYMBOLS = args.symbols

FIELD_PRICE = "3"
FIELD_VOLUME = "8"
# https://tda-api.readthedocs.io/en/v1.3.3/streaming.html#equities-quotes

MAX_POINTS = 500  # at most 500 recent points to hold.

dotenv.load_dotenv()

client = schwabdev.Client(
    os.getenv("APP_KEY"), os.getenv("APP_SECRET"), os.getenv("CALLBACK_URL")
)

streamer = schwabdev.Stream(client)

shared = []

# collections.deque ensure data to hold at most MAX_POINTS recent points per symbol.
data = {
    sym: {
        "time": deque(maxlen=MAX_POINTS),
        "price": deque(maxlen=MAX_POINTS),
        "volume": deque(maxlen=MAX_POINTS),
        "open": deque(maxlen=MAX_POINTS),
        "high": deque(maxlen=MAX_POINTS),
        "low": deque(maxlen=MAX_POINTS),
    }
    for sym in SYMBOLS
}


# ---------------- STREAM HANDLER ----------------
def response_handler(msg):
    shared.append(msg)


streamer.start(response_handler)
streamer.send(
    streamer.level_one_equities(",".join(SYMBOLS), f"0,{FIELD_PRICE},{FIELD_VOLUME}")
)


# ---------------- CONSUMER ----------------
def consumer():
    while True:
        while shared:
            msg = json.loads(shared.pop(0))
            if "data" not in msg:
                continue

            for service in msg["data"]:
                ts = datetime.fromtimestamp(service["timestamp"] / 1000)

                for content in service["content"]:
                    symbol = content.get("key")
                    if symbol not in SYMBOLS:
                        continue

                    price = content.get(FIELD_PRICE)
                    volume = content.get(FIELD_VOLUME)

                    if price is not None:
                        price_float = float(price)
                        vol_float = float(volume) if volume else 0.0

                        data[symbol]["time"].append(ts)
                        data[symbol]["price"].append(price_float)
                        data[symbol]["volume"].append(vol_float)

                        # Candlestick OHLC logic still running, but we can comment it later if desired
                        if (
                            len(data[symbol]["open"]) == 0
                            or ts != data[symbol]["time"][-2]
                        ):
                            data[symbol]["open"].append(price_float)
                            data[symbol]["high"].append(price_float)
                            data[symbol]["low"].append(price_float)
                        else:
                            data[symbol]["high"][-1] = max(
                                data[symbol]["high"][-1], price_float
                            )
                            data[symbol]["low"][-1] = min(
                                data[symbol]["low"][-1], price_float
                            )


threading.Thread(target=consumer, daemon=True).start()

# ---------------- DASH APP ----------------
app = dash.Dash(__name__)

app.layout = html.Div(
    [
        html.H2("Live Dashboard (Line + Indicators)"),
        dcc.Dropdown(
            id="symbol",
            options=[{"label": s, "value": s} for s in SYMBOLS],
            value=SYMBOLS[0],
        ),
        dcc.Graph(id="price-chart"),
        dcc.Interval(
            id="update",
            interval=2000,  # dashboard updates/redraws the chart with the latest buffered data in milliseconds, i.e., 1000 is 1 second
        ),
    ]
)


# ---------------- DATAFRAME & INDICATORS ----------------
def compute_df(sym):
    min_len = min(
        len(data[sym]["time"]), len(data[sym]["price"]), len(data[sym]["volume"])
    )
    df = pd.DataFrame(
        {
            "time": list(data[sym]["time"])[-min_len:],
            "price": list(data[sym]["price"])[-min_len:],
            "volume": list(data[sym]["volume"])[-min_len:],
            # Candlestick arrays included but can be ignored in plotting
            "open": list(data[sym]["open"])[-min_len:],
            "high": list(data[sym]["high"])[-min_len:],
            "low": list(data[sym]["low"])[-min_len:],
        }
    )

    if len(df) > 0:
        df["ma20"] = df["price"].rolling(20).mean()
        df["ma50"] = df["price"].rolling(50).mean()
        cumulative_pv = (df["price"] * df["volume"]).cumsum()
        cumulative_vol = df["volume"].cumsum()
        df["vwap"] = cumulative_pv / cumulative_vol.replace(0, 1)
        # Volume-Weighted Average Price or VWAP = Cumulative Price × Volume​ / Cumulative Volume

    return df


# ---------------- DASH CALLBACK ----------------
@app.callback(
    Output("price-chart", "figure"),
    Input("update", "n_intervals"),
    Input("symbol", "value"),
)
def update_chart(_, sym):
    df = compute_df(sym)
    fig = go.Figure()

    if len(df) > 0:
        # ---------------- COMMENTED OUT CANDLESTICKS & VOLUME ----------------
        # fig.add_trace(go.Candlestick(
        #     x=df["time"],
        #     open=df["open"],
        #     high=df["high"],
        #     low=df["low"],
        #     close=df["price"],
        #     name="Candlestick"
        # ))

        # fig.add_trace(go.Bar(
        #     x=df["time"],
        #     y=df["volume"],
        #     name="Volume",
        #     marker_color="grey",
        #     yaxis="y2",
        #     opacity=0.3
        # ))

        # ---------------- LINE PRICE + INDICATORS ----------------
        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["price"],
                name="Price",
                mode="lines",
                line=dict(color="green"),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["ma20"],
                name="MA20",
                line=dict(color="blue"),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["ma50"],
                name="MA50",
                line=dict(color="orange"),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["vwap"],
                name="VWAP",
                line=dict(color="purple"),
            )
        )

    fig.update_layout(
        template="plotly_dark",
        xaxis_title="Time",
        yaxis_title="Price",
        title=f"Live Line & Indicators: {sym}",
    )

    return fig


# ---------------- RUN APP ----------------
if __name__ == "__main__":
    app.run(debug=True)
