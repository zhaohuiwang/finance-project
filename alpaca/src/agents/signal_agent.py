"""Signal Agent — asks Claude to reason about MA crossover, RSI, and recent news."""

import json
from datetime import datetime, timezone

import anthropic
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest

from utils.market import get_bars
from utils.signals import calculate_rsi
from utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM = """You are a quantitative trading signal analyst for momentum strategies.

You will receive current market indicators and recent news headlines for a symbol.
Determine the signal:
- BUY  : fast MA just crossed ABOVE slow MA on the latest bar, AND RSI < rsi_max_for_buy,
         AND news does not present a strong near-term bearish risk
- SELL : fast MA just crossed BELOW slow MA on the latest bar (RSI not required),
         OR negative news materially changes the near-term outlook
- HOLD : no fresh crossover, conditions not met, or news makes the signal unreliable

A crossover is only valid when the relationship flipped between the previous and current bar.
Weight recent news that is directly about the company more heavily than sector/macro news.
Be precise — cite specific numbers and headlines in your reasoning."""


def _fetch_news(news_client: NewsClient, symbol: str, max_items: int = 5) -> list[dict]:
    """Fetch recent headlines from the Alpaca News API. Returns [] on any failure."""
    try:
        news_set = news_client.get_news(NewsRequest(symbols=symbol, limit=max_items))
        items = news_set.data.get("news", [])
        result = []
        for item in items:
            age_h = round(
                (datetime.now(timezone.utc) - item.created_at).total_seconds() / 3600, 1
            )
            result.append(
                {
                    "headline": item.headline,
                    "source": item.source,
                    "age_hours": age_h,
                    "summary": (item.summary or "")[:200],
                }
            )
        return result
    except Exception as e:
        logger.debug(f"Alpaca news fetch failed for {symbol}: {e}")
        return []


class SignalAgent:
    """Fetches market indicators + Alpaca news and delegates signal reasoning to Claude."""

    def __init__(self, data_client, news_client: NewsClient, cfg) -> None:
        self._data_client = data_client
        self._news_client = news_client
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

        vol_ratio = None
        if "volume" in df.columns:
            avg_vol = df["volume"].rolling(window=20).mean().iloc[-1]
            if avg_vol > 0:
                vol_ratio = round(float(df["volume"].iloc[-1] / avg_vol), 2)

        news = _fetch_news(self._news_client, symbol)

        current_price = float(df["close"].iloc[-1])

        context = {
            "symbol": symbol,
            "current_price": round(current_price, 4),
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
            "volume_ratio_vs_20bar_avg": vol_ratio,
            "recent_news": news,
        }

        response = self._client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "signal": {
                                "type": "string",
                                "enum": ["BUY", "SELL", "HOLD"],
                            },
                            "confidence": {"type": "number"},
                            "reasoning": {"type": "string"},
                        },
                        "required": ["signal", "confidence", "reasoning"],
                        "additionalProperties": False,
                    },
                }
            },
            messages=[
                {
                    "role": "user",
                    "content": f"Analyze:\n{json.dumps(context, indent=2)}",
                }
            ],
        )

        text = next(b.text for b in response.content if b.type == "text")
        result = json.loads(text)
        result["current_price"] = current_price
        logger.info(
            f"[signal] {symbol}: {result['signal']} "
            f"(confidence={result['confidence']:.2f}) — {result['reasoning'][:100]}"
        )
        return result
