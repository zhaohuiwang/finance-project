
# config.py
# =============================================================
# 1. Which stocks the bot watches
# =============================================================
SYMBOLS = ['ACHR', 'NBIS', 'IREN']

# =============================================================
# 2. Per-symbol strategy settings
# =============================================================
CONFIG = {
    'ACHR': {
        'buy_target_price': 6.0,      # ← change this based on current price
        'buy_drop_pct': 5.0,            # % drop from last buy price to rebuy
        'limit_sell_pct': 8.0,          # take-profit % above buy price
        'stop_loss_pct': 5.0,           # stop-loss % below buy price
    },
    'NBIS': {
        'buy_target_price': 85.0,
        'buy_drop_pct': 6.0,
        'limit_sell_pct': 12.0,
        'stop_loss_pct': 7.0,
    },
    'IREN': {
        'buy_target_price': 32.0,
        'buy_drop_pct': 7.0,
        'limit_sell_pct': 15.0,
        'stop_loss_pct': 8.0,
    },
}

# =============================================================
# 3. Overall risk management (applies to the whole account)
# =============================================================
RISK_CONFIG = {
    'risk_per_trade_pct': 1.0,      # 1% of total account equity risked per trade
    'max_positions': 3,             # never hold more than 3 symbols at once
    'min_account_equity': 5000.0,   # emergency stop if account drops below this
    'max_daily_loss_pct': 3.0,      # auto-pause buying after 3% daily loss
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

4. Set limit_sell_pct (take-profit):
    Usually 1.5x to 2x your stop-loss % (risk-reward 1:1.5 or better).
    Example: if stop = 5%, limit = 8-12%.


Pro tip: Start conservative for the first week:

Smaller % targets
Lower risk_per_trade_pct (see below)

"""