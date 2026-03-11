# config.py
# =============================================================
# 1. Which stocks the bot watches
# =============================================================
SYMBOLS = ["ACHR", "NBIS", "IREN", "USAR"]

# =============================================================
# 2. Per-symbol strategy settings
# =============================================================
CONFIG = {
    "ACHR": {
        "buy_target_price": 6.0,  # ← change this based on current price
        "buy_drop_pct": 5.0,  # % drop from last buy price to rebuy
        "limit_sell_pct": 8.0,  # take-profit % above buy price
        "stop_loss_pct": 5.0,  # stop-loss % below buy price
        "fixed_shares": 10,  # ← 0: risk-based | > 0, fixed manual quantity
    },
    "IREN": {
        "buy_target_price": 32.0,
        "buy_drop_pct": 7.0,
        "limit_sell_pct": 15.0,
        "stop_loss_pct": 8.0,
        "fixed_shares": 10,
    },
    "NBIS": {
        "buy_target_price": 85.0,
        "buy_drop_pct": 6.0,
        "limit_sell_pct": 12.0,
        "stop_loss_pct": 7.0,
        "fixed_shares": 10,
    },
    "USAR": {
        "buy_target_price": 18.0,
        "buy_drop_pct": 5.0,
        "limit_sell_pct": 10.0,
        "stop_loss_pct": 5.0,
        "fixed_shares": 10,
    },
}

# =============================================================
# 3. Overall risk management (applies to the whole account)
# =============================================================
RISK_CONFIG = {
    "risk_per_trade_pct": 1.0,  # 1% of total account equity risked per trade
    "max_positions": 4,  # never hold more than 4 symbols at once
    "min_account_equity": 5000.0,  # emergency stop if account drops below this
    "max_daily_loss_pct": 3.0,  # auto-pause buying after 3% daily loss
}


"""
1. Check current price (use Schwab, Yahoo Finance, etc).
2. Decide your buy zone:
    buy_target_price = absolute price you're happy to buy at (usually 5-12% below current price).
    OR leave it high and rely only on buy_drop_pct (the bot will wait for a pullback from your last buy).

3. Set stop_loss_pct based on volatility:
    Calm stock (ACHR): 4-6%
    Medium (NBIS): 6-8%
    Wild stock (IREN): 8-10%
    "stopPrice" or stop loss order in the OCO is set round(buy_price * (1 - cfg["stop_loss_pct"] / 100), 2)

4. Set limit_sell_pct (take-profit):
    Usually 1.5x to 2x your stop-loss % (risk-reward 1:1.5 or better).
    Example: if stop = 5%, limit = 8-12%.


Pro tip: Start conservative for the first week:

Smaller % targets
Lower risk_per_trade_pct (see below)

RISK_CONFIG (protects your whole account)
Setting    Recommended starting value  When to change     What it does
risk_per_trade_pct  0.5-1.0 Increase only after you're profitable   Max % of your account you risk on one trade (dynamic share sizing)

max_positions   2-3 Never go above 4    Max number of stocks you can hold at the same time
min_account_equity  $5,000 or whatever you can lose Set to 20% of your total capital    Hard floor — bot stops trading if account drops below this
max_daily_loss_pct  2.0-3.0   Great safety net    Auto-pauses new buys if you lose this much in one day
"""


def get_account_snapshot(self):
    now = time.time()
    if (
        self._equity_cache is not None
        and self._buying_power_cache is not None
        and (now - self._equity_cache_time) < CACHE_TTL_SECONDS
    ):
        return self._equity_cache, self._buying_power_cache

    try:
        acc = self.client.account_details(self.account_hash).json()
        balances = acc.get("securitiesAccount", {}).get("currentBalances", {})
        equity = float(
            balances.get("liquidationValue") or balances.get("equity") or 0.0
        )
        bp = float(balances.get("buyingPower") or 0.0)

        self._equity_cache = equity
        self._equity_cache_time = now
        self._buying_power_cache = bp
        self._buying_power_cache_time = now

        return equity, bp
    except Exception as e:
        console.print(f"[dim red]Account snapshot failed: {e}[/dim red]")
        return (
            self._equity_cache if self._equity_cache is not None else 10000.0,
            self._buying_power_cache if self._buying_power_cache is not None else 0.0,
        )
