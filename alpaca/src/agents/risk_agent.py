"""Risk Agent — asks Claude to approve or reject a trade given account and risk state."""
import json

import anthropic

from utils.logger import get_logger
from utils.market import get_latest_ask

logger = get_logger(__name__)

_SYSTEM = """You are a trading risk manager for an automated momentum bot.

You will receive a proposed trade (BUY or SELL) and the current risk state.
Your job is to decide whether to proceed and, for BUY orders, how many shares to buy.

Rules you must enforce:
1. NEVER approve a BUY if daily_loss_halted is true.
2. NEVER approve a BUY if stop_loss_cooldown_active is true.
3. NEVER approve a BUY if there is already an open position.
4. NEVER approve a BUY if calculated qty would be 0 or less.
5. For SELL: only approve if a position actually exists.
6. Position sizing formula (shares, then bounded):
     risk_based    = floor((equity × risk_per_trade) / (entry_price × stop_loss_pct))
     position_cap  = floor((equity × max_position_pct) / entry_price)
     bp_cap        = floor(buying_power / (entry_price × 1.02))
     qty           = max(1, min(risk_based, position_cap, bp_cap))

Respond with your decision and clear reasoning."""


class RiskAgent:
    """Gathers risk context and delegates the approval decision to Claude."""

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

        try:
            account = self._trading.get_account()
            equity = float(account.equity)
            buying_power = float(account.buying_power)
        except Exception as e:
            logger.warning(f"[risk] could not fetch account: {e}")
            return {"approved": False, "qty": None, "base_price": None, "reasoning": f"Account fetch failed: {e}"}

        live_ask = get_latest_ask(self._data, symbol)

        context = {
            "symbol": symbol,
            "proposed_signal": signal,
            "account": {
                "equity": round(equity, 2),
                "buying_power": round(buying_power, 2),
            },
            "live_ask": live_ask,
            "position": {"open": has_position},
            "daily_loss_halted": self._loss_guard.is_halted(),
            "stop_loss_cooldown_active": self._cooldown.is_cooling_down(symbol),
            "risk_params": {
                "risk_per_trade": r.risk_per_trade,
                "max_position_pct": r.max_position_pct,
                "stop_loss_pct": r.stop_loss_pct,
                "take_profit_pct": r.take_profit_pct,
                "daily_max_loss_pct": r.daily_max_loss_pct,
            },
        }

        response = self._client.messages.create(
            model="claude-opus-4-7",
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
