"""
https://www.cnn.com/markets/fear-and-greed
This script fetches the current Fear & Greed Index and its components from CNN,and also retrieves historical data to plot the index over time.

"""

from pathlib import Path
import requests
import pandas as pd
import matplotlib.pyplot as plt

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
    "Origin": "https://www.cnn.com",
}


class FearGreedClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_all_data(self):
        r = self.session.get(URL, timeout=10)
        r.raise_for_status()
        return r.json()

    # -----------------------------
    # Core data helpers
    # -----------------------------
    def get_indicator_data(self):
        data = self.fetch_all_data()

        keys = [
            "fear_and_greed",
            "market_momentum_sp500",
            "stock_price_strength",
            "stock_price_breadth",
            "put_call_options",
            "market_volatility_vix",
            "safe_haven_demand",
            "junk_bond_demand",
        ]

        return {k: (data[k]["score"], data[k]["rating"]) for k in keys}

    def get_fg_historical_data(self):
        data = self.fetch_all_data()
        hist = data["fear_and_greed_historical"]["data"]

        df = pd.DataFrame(hist)
        df["date"] = pd.to_datetime(df["x"], unit="ms")
        df = df.rename(columns={"y": "fear_greed"})
        return df[["date", "fear_greed"]]


# -----------------------------
# Plotting
# -----------------------------
def plot_historical_data(df, output_dir="output/cnn_market_info"):
    plt.figure(figsize=(12, 5))
    plt.plot(df["date"], df["fear_greed"], linewidth=1.5)

    plt.title("Fear & Greed Index (Historical)")
    plt.ylabel("Index (0-100)")
    plt.xlabel("Date")
    plt.grid(True, alpha=0.3)

    # sentiment bands
    plt.axhspan(0, 24, color="red", alpha=0.1)
    plt.axhspan(25, 44, color="orange", alpha=0.1)
    plt.axhspan(45, 55, color="gray", alpha=0.1)
    plt.axhspan(56, 74, color="green", alpha=0.1)
    plt.axhspan(75, 100, color="darkgreen", alpha=0.1)

    # save
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / "fear_greed.png"
    plt.savefig(file_path, dpi=200, bbox_inches="tight")
    plt.close()

    print(f"Saved plot to {file_path}")


# -----------------------------
#
# -----------------------------
if __name__ == "__main__":
    client = FearGreedClient()

    try:
        current = client.get_indicator_data()

        message = (
            f"CNN Fear & Greed Index: {current['fear_and_greed'][0]:.0f} ({current['fear_and_greed'][1].upper()})\n"
            "Ranges: Extreme Fear (0-24), Fear (25-44), Neutral (45-55), "
            "Greed (56-74), Extreme Greed (75-100)"
        )

        print(message)

        for k, v in current.items():
            print(f"  - {k.replace('_', ' ').title()}: {v[0]:.0f}, {v[1].upper()}")

        df = client.get_fg_historical_data()
        plot_historical_data(df)

    except Exception as e:
        print(f"Error: {e}")
