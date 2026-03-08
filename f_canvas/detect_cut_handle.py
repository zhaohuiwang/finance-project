import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def fetch_stock_data(ticker, period="6mo", interval="1d"):
    """Fetch historical stock data for a given ticker."""
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    return df


def detect_cup_and_handle(
    df,
    min_cup_duration=20,
    max_cup_duration=120,
    min_handle_duration=5,
    max_handle_duration=20,
):
    """Detect Cup and Handle pattern in the stock data."""
    # Ensure we have enough data
    if len(df) < min_cup_duration + min_handle_duration:
        return False, None

    # Get closing prices and volumes
    prices = df["Close"].values
    volumes = df["Volume"].values
    dates = df.index

    # Step 1: Find the cup (U-shaped pattern)
    # Look for a peak, trough, and recovery to near the initial peak
    for i in range(len(prices) - max_cup_duration, len(prices) - min_cup_duration):
        # Potential start of the cup (left peak)
        left_peak = prices[i]
        left_peak_idx = i

        # Find the trough (lowest point after left peak)
        trough_idx = np.argmin(prices[i : i + max_cup_duration]) + i
        trough = prices[trough_idx]
        if trough_idx == i or trough_idx >= len(prices) - min_handle_duration:
            continue

        # Find the right peak (recovery after trough)
        right_peak_idx = (
            np.argmax(prices[trough_idx : trough_idx + max_cup_duration]) + trough_idx
        )
        right_peak = prices[right_peak_idx]
        if right_peak_idx >= len(prices) - min_handle_duration:
            continue

        # Check if the pattern forms a cup
        cup_depth = left_peak - trough
        cup_recovery = right_peak - trough
        if (
            cup_depth < 0.2 * left_peak or cup_depth > 0.5 * left_peak
        ):  # Cup depth 20-50%
            continue
        if (
            abs(right_peak - left_peak) > 0.1 * left_peak
        ):  # Right peak should be close to left peak
            continue
        if (right_peak_idx - left_peak_idx) < min_cup_duration or (
            right_peak_idx - left_peak_idx
        ) > max_cup_duration:
            continue

        # Check volume: lower at trough, higher during recovery
        avg_volume_trough = np.mean(volumes[trough_idx - 5 : trough_idx + 5])
        avg_volume_recovery = np.mean(volumes[trough_idx:right_peak_idx])
        if avg_volume_recovery <= avg_volume_trough:
            continue

        # Step 2: Find the handle (consolidation after right peak)
        handle_prices = prices[right_peak_idx:]
        if len(handle_prices) < min_handle_duration:
            continue

        handle_low_idx = np.argmin(handle_prices[:max_handle_duration]) + right_peak_idx
        handle_low = prices[handle_low_idx]
        handle_duration = handle_low_idx - right_peak_idx

        # Check handle criteria
        handle_depth = right_peak - handle_low
        if handle_depth > 0.5 * cup_depth:  # Handle should be shallow
            continue
        if (
            handle_duration < min_handle_duration
            or handle_duration > max_handle_duration
        ):
            continue

        # Check volume: lower during handle
        avg_volume_handle = np.mean(volumes[right_peak_idx:handle_low_idx])
        if avg_volume_handle >= avg_volume_recovery:
            continue

        # Step 3: Check for breakout
        recent_prices = prices[handle_low_idx:]
        if len(recent_prices) == 0:
            continue
        recent_high = np.max(recent_prices)
        recent_high_idx = np.argmax(recent_prices) + handle_low_idx
        recent_volume = (
            np.mean(volumes[recent_high_idx - 5 : recent_high_idx + 5])
            if recent_high_idx + 5 < len(volumes)
            else volumes[-1]
        )

        if recent_high > right_peak and recent_volume > avg_volume_handle:
            return True, {
                "left_peak": left_peak,
                "trough": trough,
                "right_peak": right_peak,
                "handle_low": handle_low,
                "breakout_price": recent_high,
                "cup_start_date": dates[left_peak_idx],
                "cup_end_date": dates[right_peak_idx],
                "handle_end_date": dates[handle_low_idx],
                "breakout_date": dates[recent_high_idx],
            }

    return False, None


def scan_stocks(tickers, period="6mo"):
    """Scan a list of stocks for Cup and Handle patterns."""
    results = []
    for ticker in tickers:
        try:
            df = fetch_stock_data(ticker, period)
            found, details = detect_cup_and_handle(df)
            if found:
                results.append({"ticker": ticker, "details": details})
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    return results


def main():
    # Example list of stocks (S&P 500 tickers or customize as needed)
    tickers = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "TSLA",
        "NVDA",
        "JPM",
        "WMT",
        "PG",
        "KO",
        "JOBY",
        "ACHR",
        "PONY",
        "WRD",
        "QBTS",
        "IONQ",
        "HON",
        "MRVL",
        "ARRY",
        "APLD",
        "CRWV",
        "NBIS",
        "PLTR",
        "CRWD",
        "HIMS",
        "OGN",
        "UNH",
        "RGC",
        "KLTO",
    ]

    print("Scanning stocks for Cup and Handle patterns...")
    results = scan_stocks(tickers)

    if not results:
        print("No Cup and Handle patterns found.")
    else:
        print("\nStocks with potential Cup and Handle patterns:")
        for result in results:
            ticker = result["ticker"]
            details = result["details"]
            print(f"\nTicker: {ticker}")
            print(
                f"Left Peak: ${details['left_peak']:.2f} on {details['cup_start_date'].date()}"
            )
            print(f"Trough: ${details['trough']:.2f}")
            print(
                f"Right Peak: ${details['right_peak']:.2f} on {details['cup_end_date'].date()}"
            )
            print(
                f"Handle Low: ${details['handle_low']:.2f} on {details['handle_end_date'].date()}"
            )
            print(
                f"Breakout Price: ${details['breakout_price']:.2f} on {details['breakout_date'].date()}"
            )
            print(
                f"Estimated Price Target: ${details['right_peak'] + (details['right_peak'] - details['trough']):.2f}"
            )


if __name__ == "__main__":
    main()
