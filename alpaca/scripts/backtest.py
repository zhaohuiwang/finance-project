import yfinance as yf
import pandas as pd

SYMBOL = "AAPL"
WINDOW = 20
THRESHOLD = 2.0

def backtest(symbol):
    df = yf.download(symbol, period="5d", interval="1m")

    df = df.dropna()
    df["max_20"] = df["High"].rolling(WINDOW).max()

    df["drop_pct"] = (df["max_20"] - df["Close"]) / df["max_20"] * 100

    df["signal"] = df["drop_pct"] >= THRESHOLD

    trades = df[df["signal"]]

    print(f"Total signals: {len(trades)}")
    print(trades[["Close", "drop_pct"]].tail())

    return df

if __name__ == "__main__":
    backtest(SYMBOL)