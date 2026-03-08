# -*- coding: utf-8 -*-
"""
Created on Mon Nov 16 08:36:09 2020
                                            apikey
https://polygon.io/dashboard            'iNopt7F73wQJt7Nh6_BkTydndWop42C5'
https://financialmodelingprep.com       '5676aaad598799aa4e148c12b5a89579' 
https://www.quandl.com/tools/python     '-cX3tJSzssBhA8qVBx-x' 
https://www.alphavantage.co/documentation/    'ULYU44MP5XVLBFAX'           5 API requests per minute and 500 requests per day
 


https://financialmodelingprep.com/developer/docs

https://github.com/antoinevulcain/Financial-Modeling-Prep-API
https://financialmodelingprep.com/developer/docs


apikey = '5676aaad598799aa4e148c12b5a89579' # my free trial API key

# demo run(apikey appended to the url), or past the url link to the web bar
test = requests.get('https://financialmodelingprep.com/api/v3/'\
                    'profile/AAPL?apikey=demo')  

# or make a parameters dictionary and pass it to the .get() function
params = dict(apikey='demo')  

# Requests will go ahead and add the parameters to the URL for us.
test = requests.get('https://financialmodelingprep.com/api/v3/'\
                    'profile/AAPL',
                    params=params)
print(test.url)         # the parameters was added to the URL 
print(test.encoding)    # educated guesses by request based on the HTTP headers
test.encoding = 'ISO-8859-1' # 
     
if test:    # test if a request responded successfully
    print('Response OK')
else:
    print('Response Failed')
    
test.status_code

1XX - Information
2XX - Success
3XX - Redirect
4XX - Client Error (you messed up)
5XX - Server Error (they messed up)

# apply the .json() method on the response object to parse the data as JSON
# or a list of dictionary, here the list has only one element
print(test.json()[0]['symbol']) 

Note to the url link: 
The ? indicates the start of the query string. Within the query string
you have a set of key=value pairs, each separated by an &

"""

import requests
import pandas as pd

apikey = "demo"


# a function to pull all of the information from Financial Modeling Prep
def getdata(stock):
    # Company Quote Group of Items
    company_quote = requests.get(
        f"https://financialmodelingprep.com/api/v3/quote/{stock}"
    )
    company_quote = company_quote.json()
    share_price = float("{0:.2f}".format(company_quote[0]["price"]))

    # Balance Sheet Group of Items
    BS = requests.get(f"https://financialmodelingprep.com/api/v3/financials/'\
        'balance-sheet-statement/{stock}?period=quarter")
    BS = BS.json()

    # Total Debt
    debt = float("{0:.2f}".format(float(BS["financials"][0]["Total debt"]) / 10**9))
    # Total Cash
    cash = float(
        "{0:.2f}".format(
            float(BS["financials"][0]["Cash and short-term investments"]) / 10**9
        )
    )

    # Income Statement Group of Items
    IS = requests.get(f"https://financialmodelingprep.com/api/v3/financials/'\
                      'income-statement/{stock}?period=quarter")
    IS = IS.json()

    # Most Recent Quarterly Revenue
    qRev = float("{0:.2f}".format(float(IS["financials"][0]["Revenue"]) / 10**9))

    # Company Profile Group of Items
    company_info = requests.get(f"https://financialmodelingprep.com/api/v3/'\
                                'company/profile/{stock}")
    company_info = company_info.json()
    # Chief Executive Officer
    ceo = company_info["profile"]["ceo"]

    return (share_price, cash, debt, qRev, ceo)


# Automation and Scale
# The last things we need to do now are to fill out our stock tickers and
# apply the function to all of the tickers.

tickers = (
    "AAPL",
    "MSFT",
    "GOOG",
    "T",
    "CSCO",
    "INTC",
    "ORCL",
    "AMZN",
    "FB",
    "TSLA",
    "NVDA",
)

data = map(getdata, tickers)


df = pd.DataFrame(
    data, columns=["Total Cash", "Total Debt", "Q3 2019 Revenue", "CEO"], index=tickers
)
print(df)

# Writing to Excel
writer = pd.ExcelWriter("example.xlsx")
df.to_excel(writer, "Statistics")
writer.save()


"""
params = dict(apikey='demo')
test = requests.get('https://financialmodelingprep.com/api/v3/profile/AAPL',
                    params=params)
print(test.json()[0]['symbol'])
 
when we make the parameters dictionary and pass it to the .get() function. 
Requests will go ahead and add the parameters to the URL for us.


test = requests.get('https://financialmodelingprep.com/api/v3/profile/AAPL?apikey=demo')  

print(test.json()[0]['symbol']) 
"""


"""



"""


"""
Intraday Data
"""

import requests

# replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
url = "https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo"
r = requests.get(url)
data = r.json()

print(data)


### INTRADAY TIME SERIES DATA
from alpha_vantage.timeseries import TimeSeries
import pandas as pd
import matplotlib.pyplot as plt

alpha_vantage_api_key = "-cX3tJSzssBhA8qVBx-x"


def pull_intraday_time_series_alpha_vantage(
    alpha_vantage_api_key, ticker_name, data_interval="15min"
):
    """
    Pull intraday time series data by stock ticker name.
    Args:
        alpha_vantage_api_key: Str. Alpha Vantage API key.
        ticker_name: Str. Ticker name that we want to pull.
        data_interval: String. Desired data interval for the data.
        Can be '1min', '5min', '15min', '30min', '60min'.
    Outputs:
        data: Dataframe. Time series data, including
        open, high, low, close, and datetime values.
        metadata: Dataframe. Metadata associated with the time series.
    """
    # Generate Alpha Vantage time series object
    ts = TimeSeries(key=alpha_vantage_api_key, output_format="pandas")
    # Retrieve the data for the past sixty days (outputsize = full)
    data, meta_data = ts.get_intraday(
        ticker_name, outputsize="full", interval=data_interval
    )
    data["date_time"] = data.index
    return data, meta_data


def plot_data(df, x_variable, y_variable, title):
    """
    Plot the x- and y- variables against each other, where
    the variables are columns in
    a pandas dataframe
    Args:
        df: Pandas dataframe, containing x_variable and y_variable columns.
        x_variable: String. Name of x-variable column
        y_variable: String. Name of y-variable column
        title: String. Desired title name in the plot.
    Outputs:
        Plot in the console.
    """
    fig, ax = plt.subplots()
    ax.plot_date(
        df[x_variable], df[y_variable], marker="", linestyle="-", label=y_variable
    )
    fig.autofmt_xdate()
    plt.title(title)
    plt.show()


#### EXECUTE IN MAIN FUNCTION ####
ts_data, ts_metadata = pull_intraday_time_series_alpha_vantage(
    alpha_vantage_api_key, ticker_name="GOOGL"
)
# Plot the high prices
plot_data(
    df=ts_data,
    x_variable="date_time",
    y_variable="2. high",
    title="High Values, Google Stock, 15 Minute Data",
)


### DAILY TIME SERIES DATA
from alpha_vantage.timeseries import TimeSeries
import pandas as pd
import matplotlib.pyplot as plt

alpha_vantage_api_key = "-cX3tJSzssBhA8qVBx-x"


def pull_daily_time_series_alpha_vantage(
    alpha_vantage_api_key, ticker_name, output_size="compact"
):
    """
    Pull daily time series by stock ticker name.
    Args:
        alpha_vantage_api_key: Str. Alpha Vantage API key.
        ticker_name: Str. Ticker name that we want to pull.
        output_size: Str. Can be "full" or "compact". If "compact", then the past 100 days of data
        is returned. If "full" the complete time series is returned (could be 20 years' worth of data!)
    Outputs:
        data: Dataframe. Time series data, including open, high, low, close, and datetime values.
        metadata: Dataframe. Metadata associated with the time series.
    """
    # Generate Alpha Vantage time series object
    ts = TimeSeries(key=alpha_vantage_api_key, output_format="pandas")
    data, meta_data = ts.get_daily_adjusted(ticker_name, outputsize=output_size)
    data["date_time"] = data.index
    return data, meta_data


#### EXECUTE IN MAIN FUNCTION ####
# Pull daily data for Berkshire Hathaway
ts_data, ts_metadata = pull_daily_time_series_alpha_vantage(
    alpha_vantage_api_key, ticker_name="BRK.B", output_size="compact"
)
# Plot the high prices
plot_data(
    df=ts_data,
    x_variable="date_time",
    y_variable="2. high",
    title="High Values, Berkshire Hathaway Stock, Daily Data",
)
