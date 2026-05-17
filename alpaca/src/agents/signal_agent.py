"""Signal Agent — asks Claude to reason about MA crossover and RSI data."""
import json

import anthropic

from utils.market import get_bars
from utils.signals import calculate_rsi
from utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM = """You are a quantitative trading signal analyst for momentum strategies.

You will receive current market indicators for a symbol. Determine the signal:
- BUY  : fast MA just crossed ABOVE slow MA on the latest bar, AND RSI < rsi_max_for_buy
- SELL : fast MA just crossed BELOW slow MA on the latest bar (RSI not required)
- HOLD : no fresh crossover, or conditions not met

A crossover is only valid when the relationship flipped between the previous and current bar.
Be precise — analyze the numbers, don't generalise."""


class SignalAgent:
    """Fetches market indicators and delegates signal reasoning to Claude."""

    def __init__(self, data_client, cfg) -> None:
        self._data_client = data_client
        self._cfg = cfg
        self._client = anthropic.Anthropic()

    def analyze(self, symbol: str) -> dict:
        """Return {"signal": "BUY"|"SELL"|"HOLD", "confidence": float, "reasoning": str}."""
        s = self._cfg.strategy
        df = get_bars(self._data_client, symbol, self._cfg.trading.alpaca_timeframe)
        df = df.copy()

        fast = df["close"].rolling(window=s.fast_ma).mean()
        slow = df["close"].rolling(window=s.slow_ma).mean()
        rsi = calculate_rsi(df, s.rsi_period)

        context = {
            "symbol": symbol,
            "current_price": round(float(df["close"].iloc[-1]), 4),
            "fast_ma": {
                "window": s.fast_ma,
                "prev_bar": round(float(fast.iloc[-2]), 4),
                "curr_bar": round(float(fast.iloc[-1]), 4),
            },
            "slow_ma": {
                "window": s.slow_ma,
                "prev_bar": round(float(slow.iloc[-2]), 4),
                "curr_bar": round(float(slow.iloc[-1]), 4),
            },
            "rsi": {
                "period": s.rsi_period,
                "value": round(float(rsi.iloc[-1]), 2),
                "max_for_buy": s.rsi_max_for_buy,
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
                            "signal": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
                            "confidence": {"type": "number"},
                            "reasoning": {"type": "string"},
                        },
                        "required": ["signal", "confidence", "reasoning"],
                        "additionalProperties": False,
                    },
                }
            },
            messages=[{"role": "user", "content": f"Analyze:\n{json.dumps(context, indent=2)}"}],
        )

        text = next(b.text for b in response.content if b.type == "text")
        result = json.loads(text)
        logger.info(
            f"[signal] {symbol}: {result['signal']} "
            f"(confidence={result['confidence']:.2f}) — {result['reasoning'][:100]}"
        )
        return result
