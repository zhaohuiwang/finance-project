


"""


Applies smart filters:
DAYS_BACK - Lookback period for price and volatility calculations
MIN_PRICE - Minimum price ($5+)
MIN_AVG_VOLUME - Minimum average daily volume (500k+ shares)
MAX_VOLATILITY - Maximum volatility (default 60%)
MIN_PCT_CHANGE_5D - Minimum percentage change over 5 days

Main Output:
Top Momentum + Low-Moderate Volatility list (best for swing trading)
Full filtered dataset
Two CSV files saved automatically

"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from alpaca.data import ScreenerClient, StockHistoricalDataClient
from alpaca.data.requests import (
    MarketMoversRequest,
    MostActivesRequest,
    StockBarsRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient


# ====================== CONFIG ======================
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")

# Screening parameters
DAYS_BACK = 30
MIN_PRICE = 5.0
MIN_AVG_VOLUME = 500_000
MAX_VOLATILITY = 60      # Annualized volatility %
MIN_PCT_CHANGE_5D = 8    # For momentum filter

# Batch size to respect rate limits
BATCH_SIZE = 100
# ===================================================

trading_client = TradingClient(API_KEY, API_SECRET, paper=False)  # Change to False for live
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
screener_client = ScreenerClient(API_KEY, API_SECRET)


def get_most_active(limit=100):
    req = MostActivesRequest(top=limit)
    response = screener_client.get_most_actives(req)
    return [stock.symbol for stock in response.most_actives]


def get_top_gainers(limit=50):
    req = MarketMoversRequest(top=limit)
    response = screener_client.get_market_movers(req)
    return [stock.symbol for stock in response.gainers]


def get_top_losers(limit=50):
    req = MarketMoversRequest(top=limit)
    response = screener_client.get_market_movers(req)
    return [stock.symbol for stock in response.losers]


def get_tradable_assets():
    assets = trading_client.get_all_assets()
    df = pd.DataFrame([{
        'symbol': a.symbol,
        'name': a.name,
        'tradable': a.tradable,
        'status': a.status,
        'exchange': a.exchange
    } for a in assets if a.tradable and a.status == 'active'])
    print(f"Found {len(df)} tradable US stocks")
    return df['symbol'].tolist()

def calculate_metrics(symbols, timeframe=TimeFrame.Day):
    end = datetime.now()
    start = end - timedelta(days=DAYS_BACK + 10)  # Extra buffer
    
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=timeframe,
        start=start,
        end=end,
        limit=500
    )
    
    bars = data_client.get_stock_bars(request)
    df = bars.df
    
    results = []
    
    for symbol in symbols:
        try:
            if symbol not in df.index.get_level_values(0):
                continue
                
            sym_df = df.xs(symbol, level=0).sort_index()
            if len(sym_df) < 10:
                continue
                
            closes = sym_df['close']
            highs = sym_df['high']
            lows = sym_df['low']
            volumes = sym_df['volume']
            
            # Price Movement
            pct_1d = (closes.iloc[-1] / closes.iloc[-2] - 1) * 100 if len(closes) >= 2 else 0
            pct_5d = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) >= 6 else 0
            pct_30d = (closes.iloc[-1] / closes.iloc[-min(31, len(closes))]- 1) * 100 if len(closes) >= 2 else 0
            
            # Volatility
            daily_returns = closes.pct_change().dropna()
            hist_vol = daily_returns.std() * np.sqrt(252) * 100   # Annualized
            
            # # ATR % (Average True Range)
            # tr = np.maximum(highs - lows, 
            #                np.maximum(abs(highs - closes.shift()), 
            #                          abs(lows - closes.shift())))
            # atr = tr.mean()
            # atr_pct = (atr / closes.mean()) * 100
            
            # The standard ATR calculation
            prev_close = closes.shift(1)

            tr = pd.concat([
                highs - lows,
                (highs - prev_close).abs(),
                (lows - prev_close).abs()
            ], axis=1).max(axis=1)

            atr = tr.rolling(14).mean().iloc[-1]
            atr_pct = (atr / closes.mean()) * 100
            
            # Relative Volume
            rel_volume = (
                volumes.iloc[-1] /
                volumes.mean()
            )
            results.append({
                'symbol': symbol,
                'price': round(closes.iloc[-1], 2),
                'pct_1d': round(pct_1d, 2),
                'pct_5d': round(pct_5d, 2),
                'pct_30d': round(pct_30d, 2),
                'vol_30d': round(hist_vol, 2),
                'atr_pct': round(atr_pct, 2),
                'avg_volume': int(volumes.mean()),
                'last_volume': int(volumes.iloc[-1]),
                'rel_volume': round(rel_volume, 2)
            })
        except Exception as e:
            print(f"{symbol}: {e}")
            continue
    
    return pd.DataFrame(results)

# ====================== MAIN ======================
if __name__ == "__main__":
    print("Starting Alpaca Stock Screener...")
    
    # # 1. Get all tradable symbols
    # symbols = get_tradable_assets()
    # # crypto assets are typically represented as trading pairs with a slash (e.g., BTC/USD), so we can filter them out
    # stock_symbols = [s for s in symbols if "/" not in s]
    # crypto_symbols = [s for s in symbols if "/" in s]
    
    
    # 1. Get top movers from screener to prioritize
    most_active = get_most_active(100)
    top_gainers = get_top_gainers(50)

    stock_symbols = list(
        set(most_active + top_gainers)
    )
    
    
    # 2. Screen in batches
    all_results = []
    for i in range(0, len(stock_symbols), BATCH_SIZE):
        batch = stock_symbols[i:i+BATCH_SIZE]
        print(f"Processing batch {i//BATCH_SIZE + 1}/{(len(stock_symbols)//BATCH_SIZE)+1}...")
        
        batch_df = calculate_metrics(batch)
        all_results.append(batch_df)
        
        #time.sleep(1)  # Be gentle with rate limits
    
    screen_df = pd.concat(all_results, ignore_index=True)
    
    # ====================== FILTERS ======================
    filtered = screen_df[
        (screen_df['price'] >= MIN_PRICE) &
        (screen_df['avg_volume'] >= MIN_AVG_VOLUME) &
        (screen_df['vol_30d'] <= MAX_VOLATILITY) &
        (screen_df['rel_volume'] >= 1.5)
        ].copy()
    
    # Example strategies:
    filtered['momentum_score'] = (filtered['pct_5d'] /filtered['vol_30d'])
    
    momentum_low_vol = (
        filtered[(filtered['pct_5d'] >= MIN_PCT_CHANGE_5D)].sort_values('momentum_score', ascending=False))
    
    gap_up_today = filtered[filtered['pct_1d'] >= 8].sort_values('pct_1d', ascending=False)
    
    high_vol_movers = filtered[filtered['vol_30d'] >= 50].sort_values('pct_5d', ascending=False)
    
    # ====================== OUTPUT ======================
    print(f"\n=== RESULTS ===")
    print(f"Total screened: {len(screen_df)}")
    print(f"Passed filters: {len(filtered)}")
    print(f"\nTop Momentum + Reasonable Volatility:")
    print(momentum_low_vol.head(15)[['symbol', 'price', 'pct_5d', 'vol_30d', 'atr_pct', 'avg_volume']])
    
    output_dir = Path.cwd() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    momentum_low_vol.to_csv(f"{output_dir}/momentum_low_vol_{timestamp}.csv", index=False)
    filtered.to_csv(f"{output_dir}/full_screen_{timestamp}.csv", index=False)
    
    print(f"\nFiles saved: momentum_low_vol_{timestamp}.csv")