# Alpaca SMA Crossover Trading Bot

A momentum trading bot for Alpaca Markets using a Simple Moving Average (SMA) crossover strategy with RSI filtering, bracket orders, and built-in risk controls.

---

## Project Structure

```
alpaca/
├── conf/
│   └── config.yaml          # All tunable parameters
├── scripts/
│   └── simple_ma.py         # Entry point — main loop
├── src/
│   ├── config.py            # Pydantic config models + loader
│   └── utils/
│       ├── logger.py        # Logging setup
│       ├── market.py        # Market hours, bar data, live ask
│       ├── notify.py        # Telegram notifications
│       ├── orders.py        # Order sizing, position queries, cancellation
│       ├── risk.py          # DailyLossGuard, StopLossCooldown
│       ├── signals.py       # RSI + SMA crossover signal generation
│       └── trade_log.py     # CSV trade log
├── .env                     # API keys (never commit)
└── pyproject.toml
```

---

## Setup

### 1. Install dependencies

```bash
cd alpaca
uv sync
```

### 2. Configure API keys

Copy `.env.example` to `.env` and fill in your keys:

```bash
ALPACA_PAPER_API_KEY=...
ALPACA_PAPER_SECRET_KEY=...
ALPACA_API_KEY=...           # only needed for live trading
ALPACA_SECRET_KEY=...        # only needed for live trading
TELEGRAM_TOKEN=...           # optional — for trade alerts
TELEGRAM_CHAT_ID=...         # optional — for trade alerts
```

### 3. Configure the bot

Edit `conf/config.yaml` — no code changes required:

```yaml
trading:
  paper_trading: true          # false for live real-money trading
  trade_only_market_hours: false
  symbols: ["NBIS"]            # one or more tickers
  timeframe: "minute"
  check_interval: 60           # seconds between each loop iteration
  log_file: "trade_log.csv"

strategy:
  fast_ma: 3                   # fast SMA window
  slow_ma: 8                   # slow SMA window
  rsi_period: 14
  rsi_max_for_buy: 75          # skip BUY if RSI >= this

risk:
  risk_per_trade: 0.01         # 1% of equity per trade
  stop_loss_pct: 0.015         # 1.5% fixed stop loss
  trailing_stop_pct: 0.03      # reserved — not active in bracket orders
  take_profit_pct: 0.06        # 6% take profit
  daily_max_loss_pct: 0.03     # halt trading if equity drops 3% in one day
  stop_loss_cooldown_minutes: 30  # block re-entry for 30m after a stop fires
```

### 4. Run

```bash
uv run scripts/simple_ma.py
```

---

## How It Works — End to End

### Startup

1. Config is loaded from `conf/config.yaml` and validated by Pydantic (invalid values raise an error immediately).
2. API keys are read from `.env` — paper or live keys depending on `paper_trading`.
3. Alpaca `TradingClient` and `StockHistoricalDataClient` are initialized.
4. `DailyLossGuard` and `StopLossCooldown` are created for the session.
5. The CSV trade log is created if it doesn't exist.
6. A startup message with current account equity is sent to Telegram.

---

### Main Loop (every `check_interval` seconds)

```
┌─ Market hours check ──────────────────────────────────────┐
│  If trade_only_market_hours=true and outside 9:30–16:00   │
│  ET → sleep 60s and restart loop                          │
└───────────────────────────────────────────────────────────┘
┌─ Daily loss guard ────────────────────────────────────────┐
│  If today's equity drop ≥ daily_max_loss_pct              │
│  → send Telegram alert, sleep 60s, restart loop           │
│  Resets automatically at start of each new day            │
└───────────────────────────────────────────────────────────┘
┌─ Per-symbol iteration ────────────────────────────────────┐
│  For each symbol in symbols[]:                            │
│    → run trade_symbol() (errors are caught per-symbol,    │
│      so one bad ticker doesn't block the others)          │
└───────────────────────────────────────────────────────────┘
```

---

### Per-Symbol Logic (`trade_symbol`)

#### Step 1 — Fetch market data
Fetches the last 400 1-minute OHLCV bars from Alpaca (up to 10 days back).

#### Step 2 — Calculate signals
```
fast_ma = rolling mean of close prices over fast_ma bars (3)
slow_ma = rolling mean of close prices over slow_ma bars (8)
rsi     = 14-period RSI on close prices

BUY  signal: fast_ma just crossed ABOVE slow_ma AND RSI < 75
SELL signal: fast_ma just crossed BELOW slow_ma
HOLD:        no crossover detected
```

#### Step 3 — Check position and cooldown
- Queries Alpaca for an open position in this symbol.
- Calls `StopLossCooldown.update()` to detect if a bracket stop fired since last iteration.
- If a BUY signal exists but the symbol is in cooldown → skip entry, log remaining time.

#### Step 4 — BUY execution (if signal = BUY, no open position, not cooling down)

**Reference price**: fetches the live ask price. Uses `max(live_ask, bar_close)` to match Alpaca's internal `base_price` used for bracket order validation.

**Position sizing** — three independent caps, smallest wins:
```
risk_based     = (equity × risk_per_trade) / stop_distance   ← primary sizing
position_based = (equity × max_position_pct) / entry_price   ← concentration limit
buying_power   = buying_power / entry_price                   ← liquidity constraint

qty = max(1, min(risk_based, position_based, buying_power))
```

**Take profit price**:
```
tp_price = base_price × (1 + take_profit_pct)  →  e.g. +6%
```
If the first order submission fails with Alpaca error `42210000` (tp < base_price + 0.01 — common in paper trading where data feed prices lag real market prices), the bot parses the actual `base_price` from the error response and retries once with a corrected `tp_price`.

**Bracket order submitted**:
```
Market BUY @ market price
  ├── Take profit: limit SELL at +6%   ← auto-cancels stop if hit
  └── Stop loss:  stop  SELL at -1.5% ← auto-cancels TP if hit
```
Alpaca manages both exit legs. Whichever fills first cancels the other.

#### Step 5 — SELL execution (if signal = SELL, open position exists)

1. Records the sell in `StopLossCooldown` so it isn't mistaken for a stop-loss exit.
2. Cancels any open bracket legs (take-profit / stop-loss orders) for this symbol.
3. Submits a market SELL for the full position size.

---

### Risk Controls Summary

| Control | Behaviour |
|---------|-----------|
| **Position sizing** | Risk 1% of equity per trade; size adjusted by stop distance and buying power |
| **Stop loss** | Fixed at 1.5% below entry, set as bracket leg — managed automatically by Alpaca |
| **Take profit** | Fixed at 6% above entry, set as bracket leg — managed automatically by Alpaca |
| **Daily loss limit** | Halts all trading if equity falls 3% in a single day; resets next morning |
| **Stop-loss cooldown** | Blocks re-entry for 30 minutes after a bracket stop fires, preventing whipsawing |
| **Error isolation** | Errors on one symbol are caught and logged without stopping other symbols |

---

### Notifications

Every significant event sends a Telegram message (if configured):
- Bot startup with current equity
- BUY order placed (symbol, qty, price, TP)
- SELL order placed (symbol, qty, price)
- Daily loss limit reached
- Any unhandled error

---

### Trade Log

Every BUY and SELL is appended to `trade_log.csv`:

```
timestamp, symbol, action, qty, price, reason, note
2026-05-16 14:32:01, NBIS, BUY, 30, 217.86, SMA Crossover + RSI, TP=231.13
2026-05-16 15:10:44, NBIS, SELL, 30, 220.40, SMA Crossover Exit,
```

---

### Switching Between Paper and Live Trading

Change one line in `conf/config.yaml`:

```yaml
paper_trading: false   # true = paper, false = live
```

No code changes required. Ensure both sets of API keys are in `.env`.
