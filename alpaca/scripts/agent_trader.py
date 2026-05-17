"""
Multi-Agent Trading Bot

Three Claude agents collaborate on every trading decision:

  Signal Agent  → analyzes MA crossover + RSI, returns BUY/SELL/HOLD + reasoning
  Risk Agent    → checks daily loss, cooldowns, position size; approves or rejects
  Execution Agent → submits Alpaca bracket/sell orders via tool use, retries intelligently

Run:  uv run scripts/agent_trader.py
"""
import os
import time
import socket

import pytz
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

from config import load_config
from utils.logger import setup_logging, get_logger
from utils.notify import send_telegram_message
from utils.trade_log import init_trade_log, log_trade
from utils.orders import get_position
from utils.risk import DailyLossGuard, StopLossCooldown
from utils.market import is_market_open
from agents.signal_agent import SignalAgent
from agents.risk_agent import RiskAgent
from agents.execution_agent import ExecutionAgent

# Prefer IPv4 to avoid connectivity issues on dual-stack systems
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
    logger.info("Running in PAPER TRADING mode (multi-agent)")
else:
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    logger.warning("RUNNING IN LIVE REAL MONEY MODE - BE CAREFUL!")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=cfg.trading.paper_trading)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
NY_TZ = pytz.timezone("America/New_York")


def notify(message: str) -> None:
    logger.info(message)
    send_telegram_message(message, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)


def trade_symbol(
    symbol: str,
    signal_agent: SignalAgent,
    risk_agent: RiskAgent,
    execution_agent: ExecutionAgent,
    cooldown: StopLossCooldown,
) -> None:
    """Run one full agent pipeline iteration for a single symbol."""

    # ── 1. position state (needed by both risk agent and cooldown) ────────────
    position = get_position(trading_client, symbol)
    has_position = position is not None
    cooldown.update(symbol, has_position)

    # ── 2. signal agent ───────────────────────────────────────────────────────
    signal_result = signal_agent.analyze(symbol)
    signal = signal_result["signal"]
    confidence = signal_result["confidence"]
    reasoning = signal_result["reasoning"]

    logger.info(
        f"{symbol}: signal={signal} confidence={confidence:.0%} | {reasoning[:80]}"
    )

    if signal == "HOLD":
        return

    # ── 3. risk agent ─────────────────────────────────────────────────────────
    risk_result = risk_agent.evaluate(symbol, signal, has_position)

    if not risk_result["approved"]:
        logger.info(f"{symbol}: trade rejected — {risk_result['reasoning'][:80]}")
        return

    qty = risk_result["qty"]
    base_price = risk_result["base_price"]

    # ── 4. execution agent ────────────────────────────────────────────────────
    if signal == "BUY":
        if has_position:
            logger.info(f"{symbol}: already in position, skipping BUY")
            return
        result = execution_agent.execute_buy(symbol, qty, base_price)
        if result["success"]:
            log_trade(cfg.trading.log_file, symbol, "BUY", qty, base_price,
                      "Agent: SMA + RSI", f"tp_pct={cfg.risk.take_profit_pct}")
            notify(
                f"🟢 *BUY (agent)*\n{symbol} × {qty} @ ~${base_price:.2f}\n"
                f"_{reasoning[:120]}_"
            )
        else:
            logger.error(f"{symbol}: BUY execution failed — {result['details']}")
            notify(f"⚠️ BUY failed for {symbol}: {result['details'][:100]}")

    elif signal == "SELL":
        if not has_position:
            logger.info(f"{symbol}: no position to sell")
            return
        cooldown.record_signal_sell(symbol)
        result = execution_agent.execute_sell(symbol)
        if result["success"]:
            current_price = base_price or 0.0
            log_trade(cfg.trading.log_file, symbol, "SELL", float(position.qty),
                      current_price, "Agent: SMA crossover exit")
            notify(
                f"🔴 *SELL (agent)*\n{symbol}\n_{reasoning[:120]}_"
            )
        else:
            logger.error(f"{symbol}: SELL execution failed — {result['details']}")
            notify(f"⚠️ SELL failed for {symbol}: {result['details'][:100]}")


def main() -> None:
    init_trade_log(cfg.trading.log_file)
    logger.info(f"Starting multi-agent bot — symbols: {cfg.trading.symbols}")

    # Shared stateful guards
    loss_guard = DailyLossGuard(trading_client, cfg.risk.daily_max_loss_pct)
    cooldown = StopLossCooldown(trading_client, cfg.risk.stop_loss_cooldown_minutes)

    # Instantiate agents (one set, shared across all symbols)
    signal_agent = SignalAgent(data_client, cfg)
    risk_agent = RiskAgent(trading_client, data_client, cfg, loss_guard, cooldown)
    execution_agent = ExecutionAgent(trading_client, data_client, cfg)

    account = trading_client.get_account()
    notify(
        f"🤖 *Multi-Agent Bot Started*\n"
        f"Equity: `${float(account.equity):,.2f}`\n"
        f"Symbols: {', '.join(cfg.trading.symbols)}"
    )

    while True:
        if not is_market_open(cfg.trading.trade_only_market_hours):
            logger.info("Outside market hours — waiting")
            time.sleep(60)
            continue

        if loss_guard.is_halted():
            logger.warning("Daily loss limit reached — trading halted for today")
            notify(f"⚠️ Daily loss limit ({cfg.risk.daily_max_loss_pct:.1%}) reached")
            time.sleep(60)
            continue

        for symbol in cfg.trading.symbols:
            try:
                trade_symbol(symbol, signal_agent, risk_agent, execution_agent, cooldown)
            except Exception as e:
                logger.error(f"{symbol} agent error: {e}", exc_info=True)
                notify(f"⚠️ {symbol} agent error: {e}")

        time.sleep(cfg.trading.check_interval)


if __name__ == "__main__":
    main()
