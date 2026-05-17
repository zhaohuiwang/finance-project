"""Execution Agent — uses Claude with Alpaca tools to submit orders and handle retries."""
import json

import anthropic
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType

from utils.logger import get_logger
from utils.market import get_latest_ask
from utils.orders import cancel_open_orders, get_position

logger = get_logger(__name__)

_SYSTEM = """You are a trade execution agent for an Alpaca paper/live trading bot.

Your job: execute the order you are given using the provided tools, then confirm.

For BUY bracket orders:
1. Call get_live_ask to confirm the current market price.
2. Compute tp_price = base_price × (1 + take_profit_pct). It MUST be > live_ask + 0.01.
   If not, set tp_price = live_ask + 0.02.
3. Compute stop_price = base_price × (1 - stop_loss_pct).
4. Call submit_bracket_buy with the final prices.
5. If you receive a 42210000 error, extract the base_price from the error JSON,
   recompute tp_price and stop_price using that base_price, then retry once.

For SELL orders:
1. Call cancel_open_orders first to remove bracket legs.
2. Call submit_market_sell with the position qty.

Always confirm the outcome clearly."""

_BUY_TOOLS = [
    {
        "name": "get_live_ask",
        "description": "Get the current ask price for a symbol.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "submit_bracket_buy",
        "description": "Submit a bracket market BUY order with a take-profit limit leg and a stop-loss leg.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "qty": {"type": "integer"},
                "tp_price": {"type": "number", "description": "Take-profit limit price (must be > live_ask + 0.01)"},
                "stop_price": {"type": "number", "description": "Stop-loss price"},
            },
            "required": ["symbol", "qty", "tp_price", "stop_price"],
        },
    },
]

_SELL_TOOLS = [
    {
        "name": "cancel_open_orders",
        "description": "Cancel all open orders (bracket legs) for a symbol.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "submit_market_sell",
        "description": "Sell all shares of a symbol at market price.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "qty": {"type": "number"},
            },
            "required": ["symbol", "qty"],
        },
    },
]


class ExecutionAgent:
    """Uses Claude + Alpaca tools to submit orders with intelligent retry handling."""

    def __init__(self, trading_client, data_client, cfg) -> None:
        self._trading = trading_client
        self._data = data_client
        self._cfg = cfg
        self._client = anthropic.Anthropic()

    # ── tool execution ────────────────────────────────────────────────────────

    def _run_tool(self, name: str, inputs: dict) -> str:
        r = self._cfg.risk
        try:
            if name == "get_live_ask":
                ask = get_latest_ask(self._data, inputs["symbol"])
                return json.dumps({"ask": ask})

            if name == "submit_bracket_buy":
                order = MarketOrderRequest(
                    symbol=inputs["symbol"],
                    qty=inputs["qty"],
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                    order_class="bracket",
                    take_profit={"limit_price": inputs["tp_price"]},
                    stop_loss={"stop_price": inputs["stop_price"]},
                )
                result = self._trading.submit_order(order)
                return json.dumps({"order_id": str(result.id), "status": str(result.status)})

            if name == "cancel_open_orders":
                n = cancel_open_orders(self._trading, inputs["symbol"])
                return json.dumps({"cancelled": n})

            if name == "submit_market_sell":
                order = MarketOrderRequest(
                    symbol=inputs["symbol"],
                    qty=inputs["qty"],
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                )
                result = self._trading.submit_order(order)
                return json.dumps({"order_id": str(result.id), "status": str(result.status)})

            return json.dumps({"error": f"unknown tool: {name}"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── agentic loop ──────────────────────────────────────────────────────────

    def _run_loop(self, user_message: str, tools: list) -> str:
        """Run the Claude tool-use loop; return Claude's final text response."""
        messages = [{"role": "user", "content": user_message}]

        for _ in range(8):  # safety cap on iterations
            response = self._client.messages.create(
                model="claude-opus-4-7",
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=tools,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                return next((b.text for b in response.content if b.type == "text"), "done")

            if response.stop_reason != "tool_use":
                return f"unexpected stop_reason: {response.stop_reason}"

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._run_tool(block.name, block.input)
                    logger.info(f"[exec] tool {block.name}({block.input}) → {result[:120]}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

        return "execution loop limit reached"

    # ── public interface ──────────────────────────────────────────────────────

    def execute_buy(self, symbol: str, qty: int, base_price: float) -> dict:
        """Execute a bracket BUY. Returns {"success": bool, "details": str}."""
        r = self._cfg.risk
        prompt = (
            f"Execute a bracket BUY for {symbol}:\n"
            f"- Shares: {qty}\n"
            f"- Base price: ${base_price:.4f}\n"
            f"- Stop loss pct: {r.stop_loss_pct} → stop ≈ ${base_price * (1 - r.stop_loss_pct):.2f}\n"
            f"- Take profit pct: {r.take_profit_pct} → tp ≈ ${base_price * (1 + r.take_profit_pct):.2f}\n"
        )
        details = self._run_loop(prompt, _BUY_TOOLS)
        success = "error" not in details.lower() and "fail" not in details.lower()
        return {"success": success, "details": details}

    def execute_sell(self, symbol: str) -> dict:
        """Execute a market SELL. Returns {"success": bool, "details": str}."""
        position = get_position(self._trading, symbol)
        if position is None:
            return {"success": False, "details": "no open position found"}

        qty = float(position.qty)
        prompt = f"Close the {symbol} position: cancel bracket legs then market-sell {qty} shares."
        details = self._run_loop(prompt, _SELL_TOOLS)
        success = "error" not in details.lower() and "fail" not in details.lower()
        return {"success": success, "details": details}
