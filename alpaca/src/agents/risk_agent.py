"""Risk Agent — asks Claude to approve a trade given account state, sector RS, and earnings."""
import json
from datetime import date

import anthropic
import yfinance as yf

from utils.logger import get_logger
from utils.market import get_latest_ask

logger = get_logger(__name__)

_SYSTEM = """You are a trading risk manager for an automated momentum bot.

You will receive a proposed trade and the current risk state, including sector relative
strength and proximity to earnings. Your job is to decide whether to proceed and, for
BUY orders, how many shares to buy.

Hard rules you must always enforce:
1. NEVER approve a BUY if daily_loss_halted is true.
2. NEVER approve a BUY if stop_loss_cooldown_active is true.
3. NEVER approve a BUY if there is already an open position.
4. NEVER approve a BUY within earnings_blackout_days of the next earnings date.
5. NEVER approve a BUY if calculated qty would be 0 or less.
6. For SELL: only approve if a position actually exists.

Soft rules to weigh:
- If sector_relative_strength_5d is strongly negative (< -0.05), treat as an
  additional bearish signal and raise the bar for BUY approval.
- If sector_relative_strength_5d is strongly positive (> 0.05), treat as confirmation.

Position sizing formula:
  risk_based    = floor((equity × risk_per_trade) / (entry_price × stop_loss_pct))
  position_cap  = floor((equity × max_position_pct) / entry_price)
  bp_cap        = floor(buying_power / (entry_price × 1.02))
  qty           = max(1, min(risk_based, position_cap, bp_cap))

Respond with your decision and clear reasoning."""


def _get_sector_relative_strength(symbol: str, sector_etf: str | None) -> float | None:
    """Return 5-day return of symbol minus 5-day return of sector ETF. None on failure."""
    if not sector_etf:
        return None
    try:
        sym = yf.download(symbol, period="5d", interval="1d", auto_adjust=True, progress=False)
        etf = yf.download(sector_etf, period="5d", interval="1d", auto_adjust=True, progress=False)
        if len(sym) < 2 or len(etf) < 2:
            return None
        sym_ret = float(sym["Close"].iloc[-1] / sym["Close"].iloc[0] - 1)
        etf_ret = float(etf["Close"].iloc[-1] / etf["Close"].iloc[0] - 1)
        return round(sym_ret - etf_ret, 4)
    except Exception as e:
        logger.debug(f"sector RS fetch failed for {symbol}/{sector_etf}: {e}")
        return None


def _get_days_to_earnings(symbol: str) -> int | None:
    """Return calendar days until the next earnings date. None if unavailable."""
    try:
        cal = yf.Ticker(symbol).calendar
        if cal is None:
            return None
        # calendar may be a dict with 'Earnings Date' key or a DataFrame
        if hasattr(cal, "get"):
            dates = cal.get("Earnings Date") or []
        elif hasattr(cal, "loc"):
            dates = cal.loc["Earnings Date"].tolist() if "Earnings Date" in cal.index else []
        else:
            return None
        if not dates:
            return None
        earn_date = dates[0]
        if hasattr(earn_date, "date"):
            earn_date = earn_date.date()
        days = (earn_date - date.today()).days
        return int(days)
    except Exception as e:
        logger.debug(f"earnings fetch failed for {symbol}: {e}")
        return None


class RiskAgent:
    """Gathers risk context including sector RS and earnings, delegates approval to Claude."""

    def __init__(self, trading_client, data_client, cfg, loss_guard, cooldown) -> None:
        self._trading = trading_client
        self._data = data_client
        self._cfg = cfg
        self._loss_guard = loss_guard
        self._cooldown = cooldown
        self._client = anthropic.Anthropic()

    def evaluate(self, symbol: str, signal: str, has_position: bool) -> dict:
        """Return {"approved": bool, "qty": int|None, "base_price": float|None, "reasoning": str}."""
        r = self._cfg.risk
        t = self._cfg.trading

        try:
            account = self._trading.get_account()
            equity = float(account.equity)
            buying_power = float(account.buying_power)
        except Exception as e:
            logger.warning(f"[risk] could not fetch account: {e}")
            return {"approved": False, "qty": None, "base_price": None, "reasoning": f"Account fetch failed: {e}"}

        live_ask = get_latest_ask(self._data, symbol)
        sector_etf = t.sector_etfs.get(symbol)
        sector_rs = _get_sector_relative_strength(symbol, sector_etf)
        days_to_earnings = _get_days_to_earnings(symbol) if t.earnings_blackout_days > 0 else None

        context = {
            "symbol": symbol,
            "proposed_signal": signal,
            "account": {"equity": round(equity, 2), "buying_power": round(buying_power, 2)},
            "live_ask": live_ask,
            "position": {"open": has_position},
            "daily_loss_halted": self._loss_guard.is_halted(),
            "stop_loss_cooldown_active": self._cooldown.is_cooling_down(symbol),
            "sector": {
                "etf": sector_etf,
                "relative_strength_5d": sector_rs,
                "note": "positive = symbol outperforming sector; negative = underperforming",
            },
            "earnings": {
                "days_to_next": days_to_earnings,
                "blackout_days": t.earnings_blackout_days,
            },
            "risk_params": {
                "risk_per_trade": r.risk_per_trade,
                "max_position_pct": r.max_position_pct,
                "stop_loss_pct": r.stop_loss_pct,
                "take_profit_pct": r.take_profit_pct,
                "daily_max_loss_pct": r.daily_max_loss_pct,
            },
        }

        response = self._client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "approved": {"type": "boolean"},
                            "qty": {"type": ["integer", "null"]},
                            "base_price": {"type": ["number", "null"]},
                            "reasoning": {"type": "string"},
                        },
                        "required": ["approved", "qty", "base_price", "reasoning"],
                        "additionalProperties": False,
                    },
                }
            },
            messages=[{"role": "user", "content": f"Evaluate this trade:\n{json.dumps(context, indent=2)}"}],
        )

        text = next(b.text for b in response.content if b.type == "text")
        result = json.loads(text)
        status = "APPROVED" if result["approved"] else "REJECTED"
        logger.info(f"[risk] {symbol}: {status} — {result['reasoning'][:100]}")
        return result
