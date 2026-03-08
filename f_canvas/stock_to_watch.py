"""
yfinance.Ticker(ticker).history(start= , end= ) Get price + dividends + splits but only processes one ticker at a time.
['Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits']
yfinance.download(tickers, start= , end= , ...) only daily prices and can process a list of ticksers
['Open', 'High', 'Low', 'Close', 'Volume']

"""

################## yfinance download ##################

from collections import OrderedDict
import numpy as np

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

import yfinance as yf
from datetime import date, timedelta
import xarray as xr

# from src.finance_playground.plot_utils import get_matplotlib_colors, plot_historical_price

# yfinance end date is exclusive
end_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

d1 = date.today() - timedelta(days=360 * 1)  # timespan of last 1 years
start_date = d1.strftime("%Y-%m-%d")

indices_ticker = {"Nasdaq": "^IXIC", "S&P 500": "^GSPC", "DJIA": "^DJI"}

company_ticker = {
    "Microsoft": "MSFT",
    "Alphabet": "GOOG",
    "Meta": "META",
    "Apple": "AAPL",
    "Amazon": "AMZN",
    "Array": "ARRY",
    "Enphase Energy": "ENPH",
    "American Airlines": "AAL",
    "Bayer": "BAYRY",
    "Kenvue": "KVUE",
    "Nebius": "NBIS",
    "CoreWeave": "CRWV",
    "IREN": "IREN",
    "Super Micro Computer, Inc.": "SMCI",
}

# tickers = indices_ticker.update(company_ticker) # Appends the righ to the left
tickers = {**indices_ticker, **company_ticker}

tickers = list(tickers.values())

# Instantiate an Ordered Dict to hold stock data as ticker:data pair
data_dict = OrderedDict()

if isinstance(tickers, dict):
    # Assign the ticker/symbol as the Dict key and company name as the name of the level (columns.name) of the corresponding pd.DataFrame.
    for company, symble in tickers.items():
        data_dict[symble] = yf.download(tickers=symble, start=start_date, end=end_date)
        # Data variable list ['Close', 'High', 'Low', 'Open', 'Volume', 'Date'].
        # drop the unnecessary column index level
        if len(data_dict[symble].columns.names) > 1:
            data_dict[symble] = data_dict[symble].droplevel(level=1, axis=1)
            # MultiIndex([...], names=['Price', 'Ticker']) to MultiIndex([...], names='Price')
            data_dict[symble].columns.name = None
        else:
            pass

        # By default, yf.download() returns a DataFrame indexed by Datetime.
        if isinstance(data_dict[symble].index, pd.DatetimeIndex):
            pass
        else:
            # Identify column(s) of datatime64[ns] dtypes
            dt_sub = data_dict[symble].select_dtypes(include=["datetime64[ns]"])
            # .select_dtypes() check over all columns and the index
            # If only 1 identified as datatimes64[ns] dtypes, set it as the index
            if not dt_sub.empty and len(dt_sub.columns) == 1:
                data_dict[symble] = data_dict[symble].set_index(dt_sub.columns)
            else:
                print("Check the time variable(s) in the download data.")
elif isinstance(tickers, list):
    # Assign the ticker/symbol as the Dict key and company name as the name of the level (columns.name) of the corresponding pd.DataFrame.
    for symble in tickers:
        data_dict[symble] = yf.download(tickers=symble, start=start_date, end=end_date)
        # Data variable list ['Close', 'High', 'Low', 'Open', 'Volume', 'Date'].
        # drop the unnecessary column index level
        if len(data_dict[symble].columns.names) > 1:
            data_dict[symble] = data_dict[symble].droplevel(level=1, axis=1)
            # MultiIndex([...], names=['Price', 'Ticker']) to MultiIndex([...], names='Price')
            data_dict[symble].columns.name = None
        else:
            pass
        # By default, yf.download() returns a DataFrame indexed by Datetime.
        if isinstance(data_dict[symble].index, pd.DatetimeIndex):
            pass
        else:
            # Identify column(s) of datatime64[ns] dtypes
            dt_sub = data_dict[symble].select_dtypes(include=["datetime64[ns]"])
            # .select_dtypes() check over all columns and the index
            # If only 1 identified as datatimes64[ns] dtypes, set it as the index
            if not dt_sub.empty and len(dt_sub.columns) == 1:
                data_dict[symble] = data_dict[symble].set_index(dt_sub.columns)
            else:
                print("Check the time variable(s) in the download data.")
else:
    pass

# Convert OrderedDict to xarray.Dataset
dataset_xr = xr.Dataset(
    {
        ticker: xr.DataArray(
            df,
            dims=["Date", "metric"],
            coords={"Date": df.index, "metric": df.columns},
            # Each dataframe was indexed by 'Date', so 'Date' should be kept here.
        )
        for ticker, df in data_dict.items()
    }
)


# Set metric variable(s) and ticker(s): a list or a single pick in string
metric_v = "Close"
metric_v = ["Close", "High", "Low"]

ticker = "NBIS"
ticker = ["NBIS", "^IXIC"]

ticker = "SMCI"
ticker = ["SMCI", "^IXIC"]

# Ensure the metric(es) and ticker(s) are correct
metric_list = list(dataset_xr.coords["metric"].values)

if isinstance(metric_v, str):
    assert metric_v in metric_list, f"The input metric is not correct!"
    metric_v = [metric_v]
elif isinstance(metric_v, list):
    assert set(metric_v).issubset(
        metric_list
    ), f"Not all the input metric(es) are correct!"
else:
    pass

ticker_list = list(dataset_xr.data_vars)

if isinstance(ticker, str):
    assert ticker in ticker_list, f"The input metric is not correct!"
    ticker = [ticker]
elif isinstance(ticker, list):
    assert set(ticker).issubset(ticker_list), f"Not all the input tickers are correct!"
else:
    pass

# ticker = 'NBIS' # after .sel() returns xarray.DataArray which can be ploted directly
# ticker = ['NBIS'] # after .sel() returns xarray.Dataset

# Select a date range, the number of days back from today
day_span = 90

end_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
d1 = date.today() - timedelta(days=day_span)
start_date = d1.strftime("%Y-%m-%d")

# Select a subset based on ticker, metric and time slice.
dataset_xr_sub = dataset_xr[ticker].sel(
    metric=metric_v, Date=slice(start_date, end_date)
)  # or .loc['2025-08-01':]


# Define line styles and colors to cycle through
line_styles = ["-", "--", ":", "-."]
colors = ["blue", "green", "purple", "orange", "cyan", "magenta", "black"]

# Plot a single stock or side-by-side with an index
if isinstance(ticker, list) and len(ticker) == 2:  # side-by-side

    fig, ax1 = plt.subplots(figsize=(10, 6))
    # xtick = dataset_xr_sub['Date'].dt.strftime("%Y-%m-%d")

    for i, metric in enumerate(dataset_xr_sub.metric.values):
        # Plot the first series on the primary y-axis (left)
        # Cycle through line styles and colors
        style = line_styles[i % len(line_styles)]
        color = colors[i % len(colors)]
        ax1.plot(
            dataset_xr_sub["Date"],
            dataset_xr_sub[ticker[0]].sel(metric=metric),
            linestyle=style,
            color=color,
            label=f"{ticker[0]}[{metric}]",
        )
    ax1.set_xlabel("Date")
    ax1.set_ylabel(ticker[0], color="blue")
    ax1.tick_params(axis="y", labelcolor="blue")

    # Create a secondary y-axis using twinx()
    ax2 = ax1.twinx()

    # Plot the second series on the secondary y-axis (right)
    ax2.plot(
        dataset_xr_sub["Date"],
        dataset_xr_sub[ticker[1]].sel(metric="Close"),
        color="red",
        label=ticker[1],
    )
    ax2.set_ylabel(ticker[1], color="red")
    ax2.tick_params(axis="y", labelcolor="red")

    # Add a title and legend
    plt.title(f"Daily [{metric_v}] movement for {ticker[0]} and {ticker[1]}")
    fig.legend(
        loc="upper left", bbox_to_anchor=(0.1, 0.9)
    )  # Place legend for both series
    plt.savefig("my_plot.png")
    plt.show()

elif isinstance(ticker, list) and len(ticker) == 1:  # individual
    fig, ax1 = plt.subplots(figsize=(10, 6))

    for i, metric in enumerate(dataset_xr_sub.metric.values):
        # Plot the first series on the primary y-axis (left)
        # Cycle through line styles and colors
        style = line_styles[i % len(line_styles)]
        color = colors[i % len(colors)]
        ax1.plot(
            dataset_xr_sub["Date"],
            dataset_xr_sub[ticker[0]].sel(metric=metric),
            linestyle=style,
            color=color,
            label=f"{ticker[0]}[{metric}]",
        )
    ax1.set_xlabel("Date")
    ax1.set_ylabel(ticker[0], color="blue")
    ax1.tick_params(axis="y", labelcolor="blue")

    # Add a title and legend
    plt.title(f"Daily [{metric_v}] movement for {ticker[0]}")
    fig.legend(
        loc="upper left", bbox_to_anchor=(0.1, 0.9)
    )  # Place legend for both series
    plt.savefig("my_plot.png")
    plt.show()


ticker = "AMZN"
ticker = "AAL"
ticker = "NBIS"
ticker = "CRWV"

df = (
    dataset_xr[ticker]
    .sel(metric=["Close", "High", "Low", "Open", "Volume"])
    .to_pandas()
    .loc["2025-08-01":]
)
# The percentage difference between the intraday High and Low
df["introday_d_p"] = (100 * (df["High"] - df["Low"]) / df["Low"]).round(0).astype(int)
# Subset from a specific date to the latest
df["introday_d_p"]


bins = [0, 2, 5, 10, 15, 100]
labels = ["0-2", "2-5", "5-10", "10-15", "15-100"]
df["introday_v"] = pd.cut(
    df["introday_d_p"], bins=bins, labels=labels, right=True, include_lowest=True
)

df["introday_v"].value_counts().sort_index()

# Introday H and L Delta percent counts (60 days)
#            NBIS   CRWV    AAL     AMZN
# 0-2        0      0       19      44
# 2-5       17      11      32      14
# 5-10      37      40      7       1
# 10-15      5      7       1       0
# 15-100     0      1       0       0


# collect all matplotlib colors
matplotlib_colors = OrderedDict()
# these colors can be called with a single character
matplotlib_colors.update(mcolors.BASE_COLORS)
# the default color cycle colors
matplotlib_colors.update(mcolors.TABLEAU_COLORS)
# named colors also recognized in css
matplotlib_colors.update(mcolors.CSS4_COLORS)
# named colors from the xkcd survey
matplotlib_colors.update(mcolors.XKCD_COLORS)

matplotlib_colors_list = list(matplotlib_colors.keys())
matplotlib_colors_list.remove("w")

plot_historical_price(company_symbol, price_history)
plt.show()

# compare hourly data for an individual stock to a main index

# https://github.com/ranaroussi/yfinance/blob/main/yfinance/tickers.py
import pandas as pd
import yfinance as yf
import seaborn as sns
import matplotlib.pyplot as plt
import xarray as xr

tickers = ["^IXIC", "^DJI", "^GSPC", "NBIS", "CRDW", "IREN"]

price_df = pd.DataFrame()
for i, ticker in enumerate(tickers):

    data = yf.Ticker(ticker).history(period="1d", interval="30m", prepost=True)
    # data['High'].reset_index().rename(columns={'High': ticker})

    ticker_price = data["High"].reset_index(drop=True).round(2).rename(ticker)
    ticker_price.index = data.index.strftime("%H:%M")
    ticker_price.index.name = None

    ticker_price_df = ticker_price.to_frame()
    price_df = pd.concat([price_df, ticker_price_df], axis=1)

inhour_price_df = price_df.loc["09:30":"16:00"]

fig, ax1 = plt.subplots(figsize=(8, 5))
# Plot y1 on the primary axes
sns.lineplot(x=inhour_price_df.index, y=inhour_price_df["^IXIC"], ax=ax1, color="blue")
ax1.set_ylabel("NASDAQ", color="blue")
ax1.tick_params(axis="y", labelcolor="blue")
# Create a secondary axes (twinx)
ax2 = ax1.twinx()

# Plot y2 on the secondary axes
sns.lineplot(x=inhour_price_df.index, y=inhour_price_df["NBIS"], ax=ax2, color="red")
ax2.set_ylabel("NBIS", color="red")
ax2.tick_params(axis="y", labelcolor="red")

plt.savefig("price_comp.png")
plt.close()


import datetime
import os

# Import packages
import yfinance as yf
import pandas as pd
import matplotlib as plt

# Define the ticker list
tickers_list = ["NBIS", "QBTS", "CRWV", "OGN", "WRD", "PONY", "ACHR", "ONTO", "NRG"]
# days back from today
day_span = 31

# Set the start and end date
end_date = datetime.date.today().strftime("%Y-%m-%d")
d1 = datetime.date.today() - datetime.timedelta(days=day_span)
start_date = d1.strftime("%Y-%m-%d")


# Create placeholder for data
data = pd.DataFrame(columns=tickers_list)
# Fetch the data
for ticker in tickers_list:
    data[ticker] = yf.download(ticker, start_date, end_date)["Close"]


################## nasdaqdatalink download ##################

import nasdaqdatalink

mydata = nasdaqdatalink.get("FRED/GDP")


import pandas_datareader.data as web
import pandas as pd
import datetime as dt

df = web.DataReader("GE", "yahoo", start="2019-09-10", end="2019-10-09")

# drop the unnecessary column index level
if len(df.columns.names) > 1:
    df = df.droplevel(level=1, axis=1)
df.head()
df = web.DataReader("005930", "naver", start="2019-09-10", end="2019-10-09")


################## polygon download ##################
from polygon import RESTClient

client = RESTClient(api_key="iNopt7F73wQJt7Nh6_BkTydndWop42C5")

ticker = "AAPL"

# List Aggregates (Bars)
aggs = []
for a in client.list_aggs(
    ticker=ticker,
    multiplier=1,
    timespan="day",
    from_="2023-01-01",
    to="2023-06-13",
    limit=50000,
):
    aggs.append(a)

print(aggs)

# Get Last Trade
trade = client.get_last_trade(ticker=ticker)
print(trade)

# List Trades
trades = client.list_trades(ticker=ticker, timestamp="2022-01-04")
for trade in trades:
    print(trade)

# Get Last Quote
quote = client.get_last_quote(ticker=ticker)
print(quote)

# List Quotes
quotes = client.list_quotes(ticker=ticker, timestamp="2022-01-04")
for quote in quotes:
    print(quote)


data = yf.download(
    tickers="AAL",
    period="1y",  #: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, ytd, max
    interval="1m",
    prepost=True,
)
