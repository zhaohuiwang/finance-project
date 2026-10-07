

from finviz.screener import Screener

filters = [
    "exch_nasd",
    "cap_largeover",
]

stocks = Screener(
    filters=filters,
    table="Overview",
    order="ticker"
)

stocks.to_csv("finviz_stocks.csv")


# https://finviz.com/help/screener
# Finviz encodes the screener settings in the URL
# https://github.com/pasie15/claude-trading-skills-marketplace/blob/main/plugins/trading-stock-screeners/skills/finviz-screener/references/finviz_screener_filters.md
from finviz.screener import Screener

url = "https://finviz.com/screener.ashx?v=111&f=cap_largeover,exch_nasd&o=-marketcap"

stocks = Screener.init_from_url(url)

stocks.to_csv("stocks.csv")

'''
Finviz has additional tables such as:

Overview
Valuation
Financial
Ownership
Performance
Technical
'''
stocks = Screener(
    filters=["exch_nasd"],
    table="Financial"
)

stocks.to_csv("financial.csv")


stocks = Screener(
    filters=["exch_nasd"],
    table="Technical"
)

stocks.to_csv("technical.csv")