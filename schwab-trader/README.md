### A bot for equity monitoring, auto trading, dashboard summary and tracking. 

#### Directory Structure
```Bash
schwab-trader/
├── conf/
│   └── bot/
│       └── conf.yaml          ← main configuration file
├── logs/
│   └── trading.db             ← auto-created SQLite for state & logs
├── src/
│   └── schwab_trader/
│       ├── pipelines/
│       │   └── bot.py
│       ├── config/
│       ├── orders/
│       └── utils/
└── scripts/
    └── bot.py                 ← main entry point
```

#### Quick Start – How to Run the Bot
Make sure you are in the project root, and in the right active Python environment.
```Bash
cd /dev/finance-project/schwab-trader
source .venv/bin/activate
```
Assuming all other requirments are satisfied, including .env (private) with schwab APP credential, pyproject.toml and .venv.

Run the bot (two modes):
```Bash
# CLI mode (recommended for most users – terminal commands + web dashboard)
python3 scripts/bot.py
# or full mode (rich live terminal dashboard + web dashboard)
python3 scripts/bot.py --model full 
```
Open the web dashboard (always available): http://127.0.0.1:8050

Configuration file - `conf/bot/conf.yaml` is the brain of the bot.

```Bash
symbols:
  XYZ:
    buy_target_price: 42.0    # Primary buy trigger price
    limit_sell_price: 42.5    # Preferred fixed profit target (used if > entry)
    buy_drop_pct: 20.0        # % drop from last_buy_price to allow re-buy
    limit_sell_pct: 15.0      # Fallback % gain if limit_sell_price is not higher
    stop_loss_dollar: 5.0     # Fixed $ stop (preferred)
    stop_loss_pct: 15.5       # Fallback % stop (only used if stop_loss_dollar = 0)
    fixed_shares: 400         # How many shares to buy (recommended)
 YZX:
    ...
risk:
  risk_per_trade_pct: 1.0       # (currently unused – fixed_shares takes priority)
  max_positions: 4              # max simultaneous holdings the bot manages
  min_account_equity: 5000.0    # pause if net liq drops below this
  max_daily_loss_pct: 3.0       # pause trading if daily loss exceeds this %
  default_shares: 1             # fallback if no fixed_shares and risk calc fails
```
Key rules the bot follows:

It buys when price ≤ `buy_target_price` or drops `buy_drop_pct`% from your last buy.
On buy: it places a true OCO bracket (limit sell + stop-limit sell).
`limit_sell_price` is used only if it is higher than the actual entry price. Otherwise it falls back to +`limit_sell_pct`. `stop_loss_dollar` takes priority over %. After editing `conf.yaml`, always execute `reload-config` in the CLI. This cancels old brackets and puts new ones with your updated prices.

The bot automatically:
* Buys on trigger (first buy = auto, subsequent buys while holding = manual confirmation)
* Places OCO bracket immediately after buy fill
* Resets auto-buy flag when you sell

Important Notes & Tips
* One automatic buy per position cycle. After you sell, the next buy becomes automatic again.
* fixed_shares always wins over risk-based sizing (risk code is commented out).
* All brackets are OCO (one cancels the other) using STOP_LIMIT for the stop leg (safer).
* Web dashboard updates every 8 seconds.
* Logs and state are saved in logs/trading.db
* If you add/remove symbols, the stream automatically restarts.