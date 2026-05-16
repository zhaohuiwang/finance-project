import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time
import requests
import pandas as pd
import socket
import pytz
import csv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame



socket.setdefaulttimeout(15)
original_getaddrinfo = socket.getaddrinfo
def force_ipv4_getaddrinfo(*args, **kwargs):
    responses = original_getaddrinfo(*args, **kwargs)
    return [res for res in responses if res[0] == socket.AF_INET]
socket.getaddrinfo = force_ipv4_getaddrinfo

load_dotenv()

"""
Overall Strategy: SMA Crossover
This bot uses a Simple Moving Average (SMA) Crossover strategy:
Fast MA = 9-minute SMA
Slow MA = 21-minute SMA

Core Idea:
When the faster moving average crosses above the slower one → Uptrend starting → Buy
When the faster moving average crosses below the slower one → Downtrend starting → Sell

RSI (Relative Strength Index) is a popular momentum oscillator that measures the speed and change of price movements on a scale of 0 to 100.

RSI > 70 → Stock is Overbought (price rose too fast, possible pullback)
RSI < 30 → Stock is Oversold (price fell too fast, possible bounce)

"""
# ========================= CONFIGURATION =========================
"""
FAST_MA - [3, 5, 9] the smaller the more responsive but also more noise; 3 is very aggressive, 5 is a good balance for minute bars, 9 is smoother but slower to react
SLOW_MA - [8, 14, 21] the larger the smoother but also slower to react; 8 is very responsive, 14 is a good balance for minute bars, 21 is smoother but may lag more

CHECK_INTERVAL - seconds between checks [30, 60, 120] - 30s is more responsive but may hit rate limits; 60s is a good balance for minute bars; 120s is safer but less responsive

RSI_MAX_FOR_BUY - Only buy if RSI < [70, 75, 80] the higher the more aggressive (buys in stronger uptrends but risks more overbought entries)

"""

# Paper or Live Trading 
PAPER_TRADING = True        # Set to False for live trading (be careful!)
# Market Hours Control
TRADE_ONLY_MARKET_HOURS = False   # ← Change to False if you want 24/7 trading

# Trading Parameters
SYMBOL = "NBIS"
TIMEFRAME = TimeFrame.Minute
FAST_MA = 3
SLOW_MA = 8
QTY = None                   # Will be calculated dynamically

CHECK_INTERVAL = 60

RSI_PERIOD = 14
RSI_MAX_FOR_BUY = 75  
   
LOG_FILE = "trade_log.csv"

# Risk Management
RISK_PER_TRADE = 0.01        # 1% of account per trade (recommended)
STOP_LOSS_PCT = 0.015        # 1.5% initial stop
TRAILING_STOP_PCT = 0.03     # 3% trailing stop
TAKE_PROFIT_PCT = 0.06       # Set to None if you want to use only trailing stop

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

NY_TZ = pytz.timezone('America/New_York')

def init_trade_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'symbol', 'action', 'qty', 'price', 'reason', 'note'])


def log_trade(symbol: str, action: str, qty: float, price: float, reason: str, note: str = ""):
    timestamp = datetime.now(NY_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, symbol, action, qty, f"{price:.2f}", reason, note])
    print(f"📝 Logged: {action} {qty} {symbol} @ ${price:.2f}")


def is_market_open():
    if not TRADE_ONLY_MARKET_HOURS:
        return True
    now = datetime.now(NY_TZ)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload, timeout=15)
    except:
        pass


def calculate_quantity(entry_price: float, stop_loss_pct: float):
    try:
        account = trading_client.get_account()
        equity = float(account.equity)
        buying_power = float(account.buying_power)

        risk_amount = equity * RISK_PER_TRADE
        stop_distance = entry_price * stop_loss_pct

        shares = int(risk_amount / stop_distance) if stop_distance > 0 else 10
        shares = max(1, min(shares, 200))
        max_by_bp = int(buying_power / (entry_price * 1.02))

        final_qty = min(shares, max_by_bp)
        print(f"Equity: ${equity:,.2f} | Risk: ${risk_amount:.2f} | Qty: {final_qty}")
        return final_qty
    except:
        return 10


def get_account_info():
    account = trading_client.get_account()
    msg = f"🤖 *Bot Started*\nEquity: `${float(account.equity):.2f}`\nRisk per Trade: {RISK_PER_TRADE*100}%"
    print(msg)
    send_telegram_message(msg)


def get_position(symbol):
    try:
        return trading_client.get_open_position(symbol)
    except:
        return None


def get_bars(symbol, limit=400):
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=datetime.now() - timedelta(days=10),
        limit=limit
    )
    bars = data_client.get_stock_bars(request_params)
    return bars.df.reset_index()


def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_signals(df):
    if len(df) < max(SLOW_MA, RSI_PERIOD + 10):
        return None, None
    df['fast_ma'] = df['close'].rolling(window=FAST_MA).mean()
    df['slow_ma'] = df['close'].rolling(window=SLOW_MA).mean()
    df['rsi'] = calculate_rsi(df, RSI_PERIOD)
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    signal = None
    if (prev['fast_ma'] <= prev['slow_ma'] and latest['fast_ma'] > latest['slow_ma']):
        if latest['rsi'] < RSI_MAX_FOR_BUY:
            signal = "BUY"
    elif (prev['fast_ma'] >= prev['slow_ma'] and latest['fast_ma'] < latest['slow_ma']):
        signal = "SELL"
    
    return signal, latest.get('rsi')


def main():
    init_trade_log()
    print(f"🚀 Starting Enhanced {SYMBOL} Bot - {datetime.now()}")
    get_account_info()

    while True:
        try:
            if TRADE_ONLY_MARKET_HOURS and not is_market_open():
                print(f"{datetime.now(NY_TZ).strftime('%H:%M:%S')} | Outside Market Hours")
                time.sleep(60)
                continue

            df = get_bars(SYMBOL)
            signal, current_rsi = calculate_signals(df)
            
            position = get_position(SYMBOL)
            has_position = position is not None
            current_price = float(df['close'].iloc[-1])

            # Fixed RSI display
            rsi_display = f"{current_rsi:.1f}" if current_rsi is not None else "N/A"

            print(f"{datetime.now().strftime('%H:%M:%S')} | {SYMBOL} @ ${current_price:.2f} | "
                  f"RSI: {rsi_display} | Signal: {signal or 'HOLD'}")

            if signal == "BUY" and not has_position:
                entry_price = current_price
                qty = calculate_quantity(entry_price, STOP_LOSS_PCT)
                
                tp_price = round(entry_price * (1 + TAKE_PROFIT_PCT), 2) if TAKE_PROFIT_PCT else None
                if tp_price and tp_price < entry_price + 0.05:
                    tp_price = round(entry_price + 0.05, 2)

                order_config = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=qty,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                    order_class="bracket",
                    take_profit=dict(limit_price=tp_price) if tp_price else None,
                    stop_loss=dict(
                        stop_price=round(entry_price * (1 - STOP_LOSS_PCT), 2),
                        trail_percent=TRAILING_STOP_PCT * 100
                    )
                )
                order = trading_client.submit_order(order_config)
                log_trade(SYMBOL, "BUY", qty, entry_price, "SMA Crossover + RSI", f"TP={tp_price}")

                msg = f"🟢 *BUY + Dynamic Risk*\n{SYMBOL} × {qty} @ ~${entry_price:.2f}"
                print(msg)
                send_telegram_message(msg)

            elif signal == "SELL" and has_position:
                qty = float(position.qty)
                order_config = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=qty,
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                    )
                order = trading_client.submit_order(order_config)
                log_trade(SYMBOL, "SELL", qty, current_price, "SMA Crossover Exit")

                msg = f"🔴 *SELL (Exit)*\n{SYMBOL} × {qty} @ ~${current_price:.2f}"
                print(msg)
                send_telegram_message(msg)

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"⚠️ Error: {e}")
            send_telegram_message(f"⚠️ Error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()