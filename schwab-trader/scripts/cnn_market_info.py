"""
CNN Fear & Greed Index

Fetches the current CNN Fear & Greed Index and its component indicators,
downloads the complete historical time series, saves the data as a CSV
lookup table, and generates a historical chart.

Data source:
https://www.cnn.com/markets/fear-and-greed
"""

from pathlib import Path
from typing import Any, Final, Self
import logging

import matplotlib.pyplot as plt
import pandas as pd
import requests

LOGGER = logging.getLogger(__name__)

URL: Final = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

HEADERS: Final = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
    "Origin": "https://www.cnn.com",
}

OUTPUT_DIR: Final = Path("outputs/cnn_market_info")
CSV_FILENAME: Final = "fear_greed.csv"
PLOT_FILENAME: Final = "fear_greed.png"


def _create_output_dir(output_dir: Path) -> Path:
    """
    Create the output directory if it does not already exist.

    Args:
        output_dir: Directory to create.

    Returns:
        The output directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


class FearGreedClient:
    """Client for retrieving CNN Fear & Greed Index data."""

    def __init__(self, timeout: int = 10) -> None:
        """
        Initialize the client.

        Args:
            timeout: HTTP request timeout in seconds.
        """
        self.timeout = timeout
        self.session: requests.Session = requests.Session()
        self.session.headers.update(HEADERS)

    def __enter__(self) -> Self:
        """Return the client for use in a context manager. Is couples with __exit__() and are called automatically within the Python's with statement or explicitly by try-except-finally block."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the HTTP session."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    def _fetch_all_data(self) -> dict[str, Any]:
        """
        Fetch the raw JSON payload from CNN.

        Returns:
            Parsed JSON response.

        Raises:
            requests.HTTPError: If the HTTP request fails.
        """
        response = self.session.get(URL, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_indicator_data(self) -> dict[str, tuple[float, str]]:
        """
        Retrieve the current Fear & Greed Index and all component indicators.

        Returns:
            Dictionary mapping indicator names to (score, rating).
        """
        data = self._fetch_all_data()

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

        return {
            key: (
                float(data[key]["score"]),
                str(data[key]["rating"]),
            )
            for key in keys
        }

    def get_historical_data(self) -> pd.DataFrame:
        """
        Retrieve the historical Fear & Greed Index.

        Returns:
            DataFrame containing:

                date : datetime64[ns]
                fear_greed : float
        """
        data = self._fetch_all_data()

        df = pd.DataFrame(data["fear_and_greed_historical"]["data"])

        df["date"] = pd.to_datetime(df["x"], unit="ms")

        df = (
            df.rename(columns={"y": "fear_greed"})[["date", "fear_greed"]]
            .sort_values("date")
            .reset_index(drop=True)
        )

        return df


def save_historical_data(
    df: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """
    Save historical data as a CSV lookup table.

    Args:
        df: Historical Fear & Greed data.
        output_dir: Destination directory.

    Returns:
        Path to the CSV file.
    """
    output_dir = _create_output_dir(output_dir)

    csv_path = output_dir / CSV_FILENAME

    (
        df.set_index("date").to_csv(
            csv_path,
            date_format="%Y-%m-%d",
        )
    )

    return csv_path


def plot_historical_data(
    df: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """
    Plot the historical Fear & Greed Index.

    Args:
        df: Historical Fear & Greed data.
        output_dir: Destination directory.

    Returns:
        Path to the saved PNG figure.
    """
    output_dir = _create_output_dir(output_dir)

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(
        df["date"],
        df["fear_greed"],
        linewidth=1.5,
        label="Fear & Greed",
    )

    ax.set_title("CNN Fear & Greed Index (Historical)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Index")
    ax.set_ylim(0, 100)

    ax.grid(True, alpha=0.30)

    ax.axhspan(0, 24, color="red", alpha=0.10)
    ax.axhspan(25, 44, color="orange", alpha=0.10)
    ax.axhspan(45, 55, color="gray", alpha=0.10)
    ax.axhspan(56, 74, color="green", alpha=0.10)
    ax.axhspan(75, 100, color="darkgreen", alpha=0.10)

    fig.tight_layout()

    plot_path = output_dir / PLOT_FILENAME

    fig.savefig(
        plot_path,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close(fig)  # Destroy figure, release it from the momory

    return plot_path


def main() -> None:
    """Run the application."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    with FearGreedClient() as client:
        indicators = client.get_indicator_data()
        history = client.get_historical_data()

    score, rating = indicators["fear_and_greed"]

    LOGGER.info(
        "CNN Fear & Greed Index: %.0f (%s)",
        score,
        rating.upper(),
    )

    LOGGER.info(
        "Ranges: Extreme Fear (0-24), Fear (25-44), "
        "Neutral (45-55), Greed (56-74), Extreme Greed (75-100)"
    )

    for name, (value, sentiment) in indicators.items():
        LOGGER.info(
            "%-30s %5.0f  %s",
            name.replace("_", " ").title(),
            value,
            sentiment.upper(),
        )

    csv_path = save_historical_data(history)
    plot_path = plot_historical_data(history)

    LOGGER.info("Saved historical data : %s", csv_path)
    LOGGER.info("Saved historical plot : %s", plot_path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOGGER.exception("Failed to retrieve CNN Fear & Greed data.")
