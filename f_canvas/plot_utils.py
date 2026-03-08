"""
13 Essential Python Libraries for Free Market Data Everyone Should Know

https://www.linkedin.com/pulse/13-essential-python-libraries-free-market-data-everyone-kevin-meneses-u71jf/
1. yfinance
2. pandas-datareader
3. Theta Data
4. Alpha Vantage
5. Finnhub
6. Nasdaq Data Link (formerly Quandl)
7. Twelve Data
8. IBApi
9. Polygon.io
10. Alpaca-py
11. Tradier
12. marketstack
13. Tiingo


"""

from datetime import datetime
from typing import Dict, Optional, Union, List
from collections import OrderedDict
import numpy as np

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set()

import yfinance as yf


def get_matplotlib_colors() -> List[str]:
    """
    Get a list of all matplotlib colors except white.
    Returns:
        List[str]: a list of all matplotlib colors except white
    """
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
    return matplotlib_colors_list


def query_company_stock_price(company_symbol: Dict) -> Dict:
    # Let's call the API & get stock data
    price_history = OrderedDict()
    for company, symble in company_symbol.items():
        price_history[company] = yf.download(
            tickers=symble, start=start_date, end=end_date
        ).reset_index()

        # drop the unnecessary column index level
        if len(price_history.columns.names) > 1:
            price_history.droplevel(level=1, axis=1)

        price_history[company].name = company


def plot_historical_price(
    company_symbol: Dict,
    price_history: Dict,
    plot_save_path: Union["stock.png", None] = None,
) -> Optional[plt.Axes]:
    """
    Plot stock historical prices
    Args:
        price_history (Dict): A dictionary with key:value as company_name:dataframe_of_historical_price.
        plot_save_path ["stock.png", None]: specify whether to save the output plot or just display it.

    Returns:
        Optional[plt.Axes]: matplotlib plot to be saved or displayed.
    """
    # Let's make the graph more informative
    timestamp = datetime.today().strftime("%Y%m%d%H%M%S")
    plt.figure(figsize=(14, 5))
    sns.set_style("ticks")
    matplotlib_colors_list = get_matplotlib_colors()
    for i, (company, code) in enumerate(company_symbol.items()):
        a_df = price_history[company]
        sns.lineplot(
            data=a_df,
            x="Date",
            y="Close",
            color=matplotlib_colors_list[i],
            label=a_df.name,
        )

    # # First case of COVID-19 was reported in "December 2019" in Wuhan.
    # plt.axvspan(
    #     xmin=pd.to_datetime("2019-12-1"),
    #     xmax=pd.to_datetime("2022"),
    #     color="dimgray",
    #     alpha=0.25,
    # )

    # plt.text(
    #     x=pd.to_datetime("2019-12-1"),
    #     y=meta["High"].max() + 5,
    #     size="medium",
    #     s="*highlighted area shows the COVID-19 period",
    # )

    # # First COVID-19 case was reported in the US on "January 30, 2020"
    # plt.vlines(
    #     x=pd.to_datetime("2020-1-30"),
    #     color="red",
    #     ymin=apple["High"].min(),
    #     ymax=meta["High"].max() - 5,
    # )

    # s1 = "The day first Covid case reported in the US"
    # s2 = "and the stock prices started to increase after \nan initial decrease till the end of pandemic"
    # plt.annotate(
    #     text=s1 + "\n" + s2,
    #     xy=(pd.to_datetime("2020-1-30"), meta["High"].mean()),
    #     xytext=(pd.to_datetime("2018-1-1"), 300),
    #     size="medium",
    #     arrowprops=dict(facecolor="black", shrink=0.05),
    # )

    plt.title(
        "Stock Prices From {0} to {1}".format(start_date, end_date),
        c="brown",
        alpha=0.8,
        size="xx-large",
    )
    sns.despine()
    plt.ylabel("Stock Price")

    # plt.legend(loc=(0.05,0.95),ncol=5,frameon=False, prop={'size': 14})
    plt.legend(frameon=False, prop={"size": 14})

    if plot_save_path != None:
        plt.savefig(plot_save_path.replace(".", f"_{timestamp}."), bbox_inches="tight")
    else:
        plt.show()

    plt.close()
    plt.clf()
