


# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/scripts/agent_trader.py
# ================================================================================

"""
Multi-Agent Trading Bot with ATR Trailing Stops
"""

"""
Multi-Agent Trading Bot

Three Claude agents collaborate on every trading decision:

  Signal Agent  → analyzes MA crossover + RSI, returns BUY/SELL/HOLD + reasoning
  Risk Agent    → checks daily loss, cooldowns, position size; approves or rejects
  Execution Agent → submits Alpaca bracket/sell orders via tool use, retries intelligently

Run:  uv run scripts/agent_trader.py

Pricing: Claude Opus 4.7 — $5.00/1M input, $25.00/1M output

Cost per loop iteration (60s interval, 1 symbol)
Call	    When	Input tokens	Output tokens	Cost
Signal Agent	Every iteration	~250	~100	~$0.004
Risk Agent	Signal ≠ HOLD (~20%)	~700	~120	~$0.007
Execution Agent (+ thinking)	Trade fires (~5%)	~3,500	~2,500	~$0.08–0.15
Daily cost (390 iterations, 1 symbol, 6.5hr trading day)
Component	Qty	Unit cost	Daily
Signal checks	390	$0.004	~$1.55
Risk checks (20 non-HOLD)	20	$0.007	~$0.14
Executions (1–2 trades)	2	$0.10	~$0.20
Total			~$1.90/day
Monthly: ~$40/month per symbol. With 3 symbols: ~$120/month.

Compare to simple_ma.py
simple_ma.py costs $0 — it's purely deterministic.
 77
How to cut costs 10×
The signal and risk agents are called on every iteration but their reasoning is straightforward. Swap them to claude-haiku-4-5 ($1.00/$5.00 per 1M — 5× cheaper on output):

In src/agents/signal_agent.py and src/agents/risk_agent.py, change:
model="claude-opus-4-7",
to:
model="claude-haiku-4-5",
Keep claude-opus-4-7 only in execution_agent.py where the retry reasoning actually benefits from the best model. This drops the monthly cost to ~$10–15/month for 1 symbol.
"""



import os
import time
import socket

import pytz
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient, NewsClient

from config import load_config
from utils.logger import setup_logging, get_logger
from utils.notify import send_telegram_message
from utils.trade_log import init_trade_log, log_trade
from utils.orders import get_position, update_atr_trailing_stop
from utils.risk import DailyLossGuard, StopLossCooldown
from utils.market import is_market_open
from agents.signal_agent import SignalAgent
from agents.risk_agent import RiskAgent
from agents.execution_agent import ExecutionAgent

socket.setdefaulttimeout(15)
_orig_getaddrinfo = socket.getaddrinfo
def _force_ipv4(*args, **kwargs):
    return [r for r in _orig_getaddrinfo(*args, **kwargs) if r[0] == socket.AF_INET]
socket.getaddrinfo = _force_ipv4

setup_logging()
logger = get_logger(__name__)

load_dotenv()
cfg = load_config()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if cfg.trading.paper_trading:
    API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_PAPER_SECRET_KEY")
    logger.info("Running in PAPER TRADING mode (multi-agent + ATR)")
else:
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    logger.warning("RUNNING IN LIVE REAL MONEY MODE - BE CAREFUL!")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=cfg.trading.paper_trading)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
news_client = NewsClient(API_KEY, SECRET_KEY)
NY_TZ = pytz.timezone("America/New_York")


def notify(message: str) -> None:
    logger.info(message)
    send_telegram_message(message, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)


def manage_trailing_stops() -> None:
    """Update ATR trailing stops."""
    if not cfg.risk.trailing_stop_enabled:
        return
    for symbol in cfg.trading.symbols:
        try:
            if get_position(trading_client, symbol):
                update_atr_trailing_stop(trading_client, data_client, symbol, cfg)
        except Exception as e:
            logger.error(f"Trailing stop failed for {symbol}: {e}")


def trade_symbol(symbol: str, signal_agent, risk_agent, execution_agent, cooldown):
    # ... (existing logic remains mostly unchanged) ...
    position = get_position(trading_client, symbol)
    has_position = position is not None
    cooldown.update(symbol, has_position)

    signal_result = signal_agent.analyze(symbol)
    signal = signal_result["signal"]
    confidence = signal_result["confidence"]
    reasoning = signal_result["reasoning"]

    logger.info(f"{symbol}: signal={signal} confidence={confidence:.0%}")

    if signal == "HOLD":
        return

    risk_result = risk_agent.evaluate(symbol, signal, has_position)
    if not risk_result["approved"]:
        return

    qty = risk_result["qty"]
    base_price = risk_result["base_price"]

    if signal == "BUY":
        if has_position:
            return
        result = execution_agent.execute_buy(symbol, qty, base_price)
        if result["success"]:
            log_trade(cfg.trading.log_file, symbol, "BUY", qty, base_price, "Agent + ATR Trail")
            notify(f"🟢 *BUY (agent)*\n{symbol} × {qty} @ ~${base_price:.2f}")
    elif signal == "SELL":
        if not has_position:
            return
        cooldown.record_signal_sell(symbol)
        result = execution_agent.execute_sell(symbol)
        if result["success"]:
            log_trade(cfg.trading.log_file, symbol, "SELL", float(position.qty), base_price or 0, "Agent Exit")


def main() -> None:
    init_trade_log(cfg.trading.log_file)
    logger.info(f"Starting Multi-Agent Bot with ATR Trailing Stops — symbols: {cfg.trading.symbols}")

    loss_guard = DailyLossGuard(trading_client, cfg.risk.daily_max_loss_pct)
    cooldown = StopLossCooldown(trading_client, cfg.risk.stop_loss_cooldown_minutes)

    signal_agent = SignalAgent(data_client, news_client, cfg)
    risk_agent = RiskAgent(trading_client, data_client, cfg, loss_guard, cooldown)
    execution_agent = ExecutionAgent(trading_client, data_client, cfg)

    notify(f"🤖 *Multi-Agent Bot + ATR Started*\nEquity: `${float(trading_client.get_account().equity):,.2f}`")

    while True:
        if not is_market_open(cfg.trading.trade_only_market_hours):
            time.sleep(60)
            continue

        if loss_guard.is_halted():
            time.sleep(60)
            continue

        for symbol in cfg.trading.symbols:
            try:
                trade_symbol(symbol, signal_agent, risk_agent, execution_agent, cooldown)
            except Exception as e:
                logger.error(f"{symbol} agent error: {e}", exc_info=True)

        manage_trailing_stops()          # ← ATR Trailing Stop Management
        time.sleep(cfg.trading.check_interval)


if __name__ == "__main__":
    main()