import os
import time
from datetime import datetime, timedelta
import pandas as pd
import requests


from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv


load_dotenv()


# ========================= CONFIGURATION =========================
# Paper or Live Trading 
PAPER_TRADING = True        # Set to False for live trading (be careful!)


# Trading Parameters
SYMBOL = "NBIS"
TIMEFRAME = TimeFrame.Minute
FAST_MA = 9
SLOW_MA = 21
QTY = 10                    # Number of shares
CHECK_INTERVAL = 60         # seconds between checks


# Telegram Notifications
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if PAPER_TRADING:
    API_KEY = os.getenv('ALPACA_PAPER_API_KEY')
    SECRET_KEY = os.getenv('ALPACA_PAPER_SECRET_KEY')
    print("🟢 Running in PAPER TRADING mode")
else:
    API_KEY = os.getenv('ALPACA_API_KEY')
    SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
    print("🔴 RUNNING IN LIVE REAL MONEY MODE - BE CAREFUL!")
# ================================================================

# Initialize Alpaca Clients
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=PAPER_TRADING)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)


def send_telegram_message(message: str):
    """Send message to Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured - skipping notification")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Telegram API error: {response.text}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


def get_account_info():
    """Get and display account information"""
    account = trading_client.get_account()
    equity = float(account.equity)
    buying_power = float(account.buying_power)
    
    msg = f"🤖 *Bot Started*\nEquity: `${equity:.2f}`\nBuying Power: `${buying_power:.2f}`\nSymbol: `{SYMBOL}`"
    print(msg)
    send_telegram_message(msg)
    return account


def get_position(symbol):
    """Get current position for a symbol"""
    try:
        return trading_client.get_open_position(symbol)
    except Exception:
        return None  # No open position


def get_bars(symbol, limit=200):
    """Fetch historical bars"""
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TIMEFRAME,
        start=datetime.now() - timedelta(days=10),
        limit=limit
    )
    bars = data_client.get_stock_bars(request_params)
    df = bars.df.reset_index()
    return df


def calculate_signals(df):
    """Calculate SMA crossover signals"""
    if len(df) < SLOW_MA:
        return None
    
    df['fast_ma'] = df['close'].rolling(window=FAST_MA).mean()
    df['slow_ma'] = df['close'].rolling(window=SLOW_MA).mean()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Bullish crossover
    if prev['fast_ma'] <= prev['slow_ma'] and latest['fast_ma'] > latest['slow_ma']:
        return "BUY"
    # Bearish crossover
    elif prev['fast_ma'] >= prev['slow_ma'] and latest['fast_ma'] < latest['slow_ma']:
        return "SELL"
    
    return None


def main():
    print(f"🚀 Starting {SYMBOL} SMA Crossover Bot - {datetime.now()}")
    get_account_info()
    
    while True:
        try:
            df = get_bars(SYMBOL)
            signal = calculate_signals(df)
            
            position = get_position(SYMBOL)
            has_position = position is not None
            current_price = float(df['close'].iloc[-1])
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Print status
            print(f"{timestamp} | {SYMBOL} @ ${current_price:.2f} | Signal: {signal or 'HOLD'} | Position: {has_position}")
            
            # Execute trades
            if signal == "BUY" and not has_position:
                order_data = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=QTY,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                order = trading_client.submit_order(order_data=order_data)
                
                msg = f"🟢 *BUY ORDER SUBMITTED*\n{SYMBOL} × {QTY} @ ~${current_price:.2f}\nOrder ID: `{order.id}`"
                print(msg)
                send_telegram_message(msg)
                
            elif signal == "SELL" and has_position:
                order_data = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=QTY,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                order = trading_client.submit_order(order_data=order_data)
                
                msg = f"🔴 *SELL ORDER SUBMITTED*\n{SYMBOL} × {QTY} @ ~${current_price:.2f}\nOrder ID: `{order.id}`"
                print(msg)
                send_telegram_message(msg)
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            error_msg = f"⚠️ Error: {str(e)}"
            print(error_msg)
            send_telegram_message(error_msg)
            time.sleep(10)


if __name__ == "__main__":
    main()