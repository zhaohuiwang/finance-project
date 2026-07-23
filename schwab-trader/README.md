# Schwab Trading Bot

— `bot3.py` -- Version 3

An automated equity trading bot for Schwab brokerage accounts that runs a
**rules-based, mean-reversion (dip-buying) strategy**: it buys a symbol when the
price falls to a configured target (or drops a set percentage below the previous
buy), then immediately protects the fill with a bracketed exit that takes profit
at a limit price or cuts losses at a stop. Each symbol is traded on its own
independent cycle — one automatic entry, one protective exit — with account-level
risk guards (minimum equity, maximum concurrent positions) gating every order.
`bot3.py` is the entry point; it loads a YAML config, starts the trading engine,
and — depending on the mode — serves a live web dashboard and/or an interactive
terminal CLI. It supports three run modes: **full** (bot + web dashboard),
**cli** (bot + terminal commands), and **headless** (bot only, ideal for a
server/systemd deployment).

## How It Works — Strategy, Technicals & Algorithm

**Strategy (mean reversion / dip buying).** For each configured symbol the bot
watches the live price and enters a **market buy** of `fixed_shares` when either
condition is met:

- `price <= buy_target_price` — an absolute entry level, or
- `price <= last_buy_price * (1 - buy_drop_pct / 100)` — a relative re-entry after
  the price has fallen a further `buy_drop_pct`% below the last recorded buy
  (`last_buy_price` is loaded from SQLite, so it survives restarts).

**Exit (OCO protective bracket).** The instant a buy fills, the bot submits a
**One-Cancels-Other (OCO)** exit so the position is never left unhedged:

- **Take-profit leg** — a limit sell at `limit_sell_price`.
- **Stop-loss leg** — a stop-limit sell with stop
  `buy_target_price * (1 - stop_loss_pct / 100)` and a limit 1% below that stop
  (to improve fill odds on a fast move).
- **Fast-market shortcut** — if the price is already `≥ limit_sell_price * 1.01`
  when the bracket would be placed, the bot skips the bracket and fires an
  immediate market sell to capture the gain.

Filling either leg cancels the other, closes the position, re-enables the
symbol's auto-buy flag, and the cycle restarts.

**Technical stack.** Python ≥ 3.13; [`schwabdev`](../github-lib/schwabdev) for the
Schwab REST + WebSocket API; a [Dash](https://dash.plotly.com/) / Bootstrap web
dashboard; [Rich](https://rich.readthedocs.io/) for terminal output; Pydantic v2
for config validation; and SQLite for state and an audit log.

**Algorithm — event-driven reconciliation.** The engine (`bot3_pipeline.py`) is a
**declarative state machine** rather than a linear script. It combines a real-time
event stream with a periodic safety-net poll:

1. **Streaming (`unified_receiver`)** — a Schwab WebSocket feed delivers
   `LEVELONE_EQUITIES` price ticks (kept in `current_market_prices`) and
   `ACCT_ACTIVITY` fill events. On a fill the bot updates holdings, writes the
   transaction and per-symbol state to SQLite, and immediately re-evaluates the
   symbol.
2. **Reconciliation (`ensure_orders`)** — the core loop. For each symbol it
   compares the *desired* state against the *actual* holdings/open-orders and
   converges them: no position + no working buy + trigger met → place a buy;
   holding + no working sell → place the OCO bracket. Because it reconciles rather
   than reacts, a missed tick or a restart simply heals on the next pass.
3. **Polling (`monitor_logic`)** — a background thread runs `ensure_orders` for
   every symbol every 15 seconds, re-syncs holdings from the account, and resets
   the daily P/L baseline at each new trading day (`trading_paused` clears too).
4. **Risk gate (`risk_checks_pass`)** — every buy is vetoed if trading is paused,
   if account equity is below `min_account_equity` (which also latches the bot to
   paused), or if open positions already reach `max_positions`.
5. **Idempotency guards** — a 25-second per-symbol placement cooldown
   (`can_place_order`), a 30-second open-orders cache, and duplicate buy/sell
   detection prevent double-submits from the overlapping stream and poll paths.
6. **Hot reload (`reload_config`)** — reloads the YAML, cancels all working orders
   per symbol, and re-runs reconciliation so new prices take effect without a
   restart.

## Requirements

- Python ≥ 3.13, dependencies managed with [`uv`](https://github.com/astral-sh/uv)
- A `.env` file (not committed) at the project root with Schwab app credentials:
  ```
  app_key=...
  app_secret=...
  callback_url=...
  ```
- `schwabdev` (local editable install) stores OAuth tokens at `~/.schwabdev/tokens.db`.
  The refresh token expires **every 7 days** and requires manual re-authentication.

## Quick Start

```bash
cd /home/zhaohuiwang/dev/finance-project/schwab-trader
source .venv/bin/activate
uv sync                     # install/sync dependencies

cd scripts
python3 bot3.py             # default: full mode (bot + web dashboard)
```

Then open the dashboard in your browser: **http://127.0.0.1:8050**
(auto-refreshes every 8 seconds).

## Usage

```bash
# Default mode (bot + dashboard)
python3 bot3.py

# Change the dashboard port
python3 bot3.py --port 8080

# Bot + interactive CLI only (no dashboard)
python3 bot3.py --mode cli

# Bot only, no dashboard — ideal for production / VPS / systemd / tmux
python3 bot3.py --mode headless

# Show help
python3 bot3.py --help
```

| Flag       | Choices / Default              | Description                                          |
|------------|--------------------------------|------------------------------------------------------|
| `--mode`   | `full` (default), `cli`, `headless` | `full` = bot + dashboard, `cli` = bot + CLI, `headless` = bot only |
| `--port`   | `8050`                         | Dashboard port (full mode only)                      |

The bot loads its config from `../conf/simple_bot_config.yaml` (relative to the
script) via `TradingConfig.load_from_file()`.

### Interactive CLI commands

In `full` and `cli` modes (when running in an interactive terminal), a `>` prompt
accepts:

| Command   | Action                                                          |
|-----------|-----------------------------------------------------------------|
| `stop`    | Stop the bot and exit                                           |
| `reload`  | Reload `simple_bot_config.yaml` (re-applies triggers/brackets)  |
| `status`  | Print current equity and number of open positions              |

The web dashboard also has a **Reload Config** button that triggers the same
reload without touching the terminal.

## Configuration — `conf/simple_bot_config.yaml`

```yaml
symbols:
  CRWV:
    buy_target_price: 81.5     # primary buy trigger price
    limit_sell_price: 84.8     # preferred fixed profit target (used if > entry)
    buy_drop_pct: 10.0         # % drop from last_buy_price to allow a re-buy
    limit_sell_pct: 8.0        # fallback % gain if limit_sell_price is not higher
    stop_loss_dollar: 5.0      # fixed $ stop below entry (preferred)
    stop_loss_pct: 8.0         # fallback % stop (used only if stop_loss_dollar = 0)
    fixed_shares: 700          # shares to buy per trade

risk:
  risk_per_trade_pct: 1.0      # currently unused — fixed_shares takes priority
  max_positions: 4             # max simultaneous holdings the bot manages
  min_account_equity: 5000.0   # pause if net liquidation drops below this
  max_daily_loss_pct: 3.0      # pause trading if daily loss exceeds this %
  default_shares: 1            # fallback if fixed_shares is missing

auto_shutdown_after_close: false  # auto-shutdown after market close
shutdown_buffer_minutes: 2        # minutes after 4:00 PM ET to shut down
shutdown_on_weekends: true
```

**Trading rules the bot follows:**

- Buys when `price <= buy_target_price` **or** the price drops `buy_drop_pct`% from
  the last buy price.
- On a filled buy it immediately places a true **OCO bracket** (limit-sell leg +
  stop-limit-sell leg).
- `limit_sell_price` is used only if it exceeds the actual entry price; otherwise it
  falls back to `entry * (1 + limit_sell_pct/100)`.
- `stop_loss_dollar` takes priority over `stop_loss_pct`.
- One **automatic** buy per position cycle; while still holding, further buys require
  manual confirmation. The auto-buy flag resets after a sell.
- After editing the config, run `reload` in the CLI (or click **Reload Config**) —
  this cancels old brackets and resubmits with the updated prices.

## Dashboard

The `full` mode dashboard (`dashboard.py`, Dash + Bootstrap DARKLY theme) shows:

- **All Account Holdings** — price, today's % change, shares, avg buy, P/L %, market value
- **Managed Positions** — the symbols from the config with their triggers
- **Open Orders** — live orders with ID, side, price, qty, type, duration
- **Account Summary** — equity, cash, buying power, day-trading BP
- A status footer with equity, daily P/L, risk used, and active/paused state

## Running as a systemd service (headless)

For an always-on deployment, run in `headless` mode under systemd.

1. Create the service file:
   ```bash
   sudo nano /etc/systemd/system/schwab-bot.service
   ```
   ```ini
   [Unit]
   Description=Schwab Trading Bot
   After=network.target
   Wants=network.target

   [Service]
   Type=simple
   User=zhaohuiwang
   WorkingDirectory=/home/zhaohuiwang/dev/finance-project/schwab-trader
   ExecStart=/home/zhaohuiwang/dev/finance-project/schwab-trader/.venv/bin/python /home/zhaohuiwang/dev/finance-project/schwab-trader/scripts/bot3.py --mode headless
   Environment=PYTHONUNBUFFERED=1
   EnvironmentFile=/home/zhaohuiwang/dev/finance-project/.env
   Restart=always
   RestartSec=5
   StandardOutput=journal
   StandardError=journal
   Nice=10
   CPUSchedulingPolicy=idle

   [Install]
   WantedBy=multi-user.target
   ```

2. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now schwab-bot.service
   ```

**Managing the service:**

```bash
sudo systemctl start   schwab-bot.service    # start
sudo systemctl stop    schwab-bot.service    # stop
sudo systemctl restart schwab-bot.service    # restart
sudo systemctl status  schwab-bot.service    # current status

journalctl -u schwab-bot.service -f          # live logs
journalctl -u schwab-bot.service -n 50       # last 50 log lines

sudo systemctl enable  schwab-bot.service    # auto-start on boot
sudo systemctl disable schwab-bot.service    # disable auto-start
sudo systemctl is-enabled schwab-bot.service # check auto-start state
```

**Removing the service:**

```bash
sudo systemctl stop schwab-bot.service
sudo systemctl disable schwab-bot.service
sudo rm /etc/systemd/system/schwab-bot.service
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

## Notes

- `fixed_shares` always wins over risk-based sizing (risk sizing code is commented out).
- All brackets are OCO (one-cancels-the-other) using `STOP_LIMIT` for the stop leg.
- The web dashboard refreshes every 8 seconds.
- Transactions and per-symbol state are persisted to a SQLite DB (survives restarts).
- If the token DB is locked, find and kill the holding process:
  ```bash
  lsof ~/.schwabdev/tokens.db   # find the PID
  kill <pid>
  ```
