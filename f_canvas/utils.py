# yfinance API reference https://ranaroussi.github.io/yfinance/reference/index.html

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def fetch_stock_data(ticker, period="6mo", interval="1d"):
    """Fetch historical stock data for a given ticker."""
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    return df
