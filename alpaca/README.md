# Alpaca SMA Crossover Trading Bot

A momentum trading bot for Alpaca Markets using a Simple Moving Average (SMA) crossover strategy with RSI filtering, bracket orders, and built-in risk controls. Two bots are available — a zero-cost deterministic version and a Claude-powered multi-agent version.

---

## Project Structure

```
alpaca/
├── conf/
│   └── config.yaml             # All tunable parameters (shared by both bots)
├── scripts/
│   ├── simple_ma.py            # Deterministic bot — zero API cost
│   └── agent_trader.py         # Multi-agent bot — Claude-powered reasoning
├── src/
│   ├── config.py               # Pydantic config models + loader
│   ├── agents/
│   │   ├── signal_agent.py     # Claude analyzes MA, RSI, volume, and live news
│   │   ├── risk_agent.py       # Claude checks risk, sector strength, earnings
│   │   └── execution_agent.py  # Claude submits orders via tool use
│   └── utils/
│       ├── logger.py           # Logging setup
│       ├── market.py           # Market hours, bar data, live ask
│       ├── notify.py           # Telegram notifications
│       ├── orders.py           # Order sizing, position queries, cancellation
│       ├── risk.py             # DailyLossGuard, StopLossCooldown
│       ├── signals.py          # RSI, SMA crossover, volume check, uptrend test
│       └── trade_log.py        # CSV trade log
├── .env                        # API keys (never commit)
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
ANTHROPIC_API_KEY=sk-ant-... # only needed for agent_trader.py
```

### 3. Configure the bot

Edit `conf/config.yaml` — no code changes required. Both bots share this file.

```yaml
trading:
  paper_trading: true          # false for live real-money trading
  trade_only_market_hours: false
  symbols: ["NBIS"]            # one or more tickers
  timeframe: "minute"
  check_interval: 60           # seconds between each loop iteration
  log_file: "trade_log.csv"
  sector_etfs:                 # maps each symbol to its sector ETF (agent_trader.py only)
    NBIS: "AIQ"                # used for sector relative-strength calculation
  earnings_blackout_days: 2    # skip BUY within N days of earnings (agent_trader.py only)

strategy:
  fast_ma: 3                   # fast SMA window
  slow_ma: 8                   # slow SMA window
  rsi_period: 14
  rsi_max_for_buy: 75          # skip BUY if RSI >= this
  volume_min_ratio: 1.0        # BUY only if volume >= X × 20-bar avg (0 to disable)
  use_5m_confirmation: true    # require 5-min uptrend before 1-min BUY (simple_ma.py)

risk:
  risk_per_trade: 0.01         # 1% of equity per trade
  max_position_pct: 0.10       # max 10% of equity in any single position
  stop_loss_pct: 0.015         # 1.5% fixed stop loss
  trailing_stop_pct: 0.03      # reserved — not active in current bracket order setup
  take_profit_pct: 0.06        # 6% take profit
  daily_max_loss_pct: 0.03     # halt trading if equity drops 3% in one day
  stop_loss_cooldown_minutes: 30  # block re-entry for 30m after a stop fires
```

### 4. Run

```bash
# Deterministic bot — free, fast, identical decisions every run
uv run scripts/simple_ma.py

# Multi-agent bot — Claude-powered reasoning with live news and sector context
uv run scripts/agent_trader.py
```

---

## How It Works — `simple_ma.py`

### Startup

1. Config loaded from `conf/config.yaml` and validated by Pydantic.
2. API keys read from `.env` — paper or live depending on `paper_trading`.
3. Alpaca clients initialized; `DailyLossGuard` and `StopLossCooldown` created.
4. CSV trade log created if it doesn't exist.
5. Startup message with current equity sent to Telegram.

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
│    → run trade_symbol() (per-symbol error isolation)      │
└───────────────────────────────────────────────────────────┘
```

### Per-Symbol Logic

#### Step 1 — Fetch 1-minute bars
Fetches the last 400 1-minute OHLCV bars from Alpaca (up to 10 days back).

#### Step 2 — Calculate signal with filters

```
fast_ma = rolling mean of close over fast_ma bars (3)
slow_ma = rolling mean of close over slow_ma bars (8)
rsi     = 14-period RSI on close prices

Initial signal:
  BUY  → fast_ma just crossed ABOVE slow_ma AND RSI < 75
  SELL → fast_ma just crossed BELOW slow_ma
  HOLD → no crossover

Volume filter (if volume_min_ratio > 0):
  Suppress BUY if current_volume < volume_min_ratio × 20-bar average
  SELL signals are never suppressed by volume

5-minute uptrend confirmation (if use_5m_confirmation = true):
  Fetch 50 × 5-min bars and check fast_ma > slow_ma on the latest bar
  Suppress BUY if the higher timeframe is not in an uptrend
```

Both filters eliminate low-quality crossovers — volume confirmation catches thin-market noise, and 5-min confirmation avoids counter-trend entries on the 1-min chart.

#### Step 3 — Check position and cooldown
- Queries Alpaca for an open position.
- Detects bracket stop-loss exits via `StopLossCooldown.update()`.
- Suppresses BUY if still within the 30-minute cooldown window.

#### Step 4 — BUY execution

**Reference price**: fetches live ask; uses `max(live_ask, bar_close)` to match Alpaca's internal `base_price` for bracket validation.

**Position sizing** — three caps, smallest wins:
```
risk_based     = (equity × risk_per_trade) / (entry_price × stop_loss_pct)
position_based = (equity × max_position_pct) / entry_price
buying_power   = buying_power / (entry_price × 1.02)

qty = max(1, min(risk_based, position_based, buying_power))
```

**Take profit**: `base_price × 1.06`. If Alpaca rejects with error `42210000` (tp < base_price + 0.01, common in paper trading where data feed prices lag), the bot parses the actual `base_price` from the error and retries once.

**Bracket order**:
```
Market BUY @ market price
  ├── Take profit: limit SELL at +6%   ← auto-cancels stop if hit
  └── Stop loss:  stop  SELL at -1.5% ← auto-cancels TP if hit
```

#### Step 5 — SELL execution
1. Marks the exit in `StopLossCooldown` so it isn't mistaken for a bracket stop.
2. Cancels any open bracket legs.
3. Submits a market SELL for the full position.

---

### Risk Controls Summary

| Control | Behaviour |
|---------|-----------|
| **Volume confirmation** | BUY suppressed if current volume < 1.0 × 20-bar average |
| **5-min uptrend** | BUY suppressed if 5-min fast MA ≤ slow MA |
| **Position sizing** | Three-cap formula: risk, concentration, and buying power |
| **Stop loss** | Fixed 1.5% bracket leg — managed automatically by Alpaca |
| **Take profit** | Fixed 6% bracket leg — managed automatically by Alpaca |
| **Daily loss limit** | Halts all trading if equity falls 3% in one day; resets next morning |
| **Stop-loss cooldown** | Blocks re-entry for 30 minutes after a bracket stop fires |
| **Error isolation** | Per-symbol error handling; one bad ticker doesn't stop the others |

---

### Notifications & Trade Log

Telegram alerts are sent on startup, every BUY/SELL, daily loss limit hit, and unhandled errors.

Every trade is appended to `trade_log.csv`:
```
timestamp, symbol, action, qty, price, reason, note
2026-05-17 14:32:01, NBIS, BUY, 30, 217.86, SMA Crossover + RSI, TP=231.13
2026-05-17 15:10:44, NBIS, SELL, 30, 220.40, SMA Crossover Exit,
```

---

## How It Works — `agent_trader.py`

The multi-agent bot runs the same risk infrastructure as `simple_ma.py` but replaces the deterministic signal and execution logic with three Claude agents that collaborate on each trading decision.

### Three-Agent Pipeline (per symbol, per loop)

```
Position check → StopLossCooldown.update()
        │
        ▼
  Signal Agent  (claude-haiku-4-5)
  ─────────────────────────────────
  Inputs:  1-min MA crossover, RSI, volume ratio, last 5 Alpaca news headlines
  Output:  BUY / SELL / HOLD  +  confidence score  +  reasoning text
        │
        │  (skips Risk and Execution agents if HOLD)
        ▼
   Risk Agent   (claude-haiku-4-5)
  ─────────────────────────────────
  Inputs:  signal, account equity/BP, daily loss state, cooldown state,
           sector ETF relative strength (5-day), days to next earnings
  Output:  approved / rejected  +  qty  +  base_price  +  reasoning text
        │
        │  (stops here if rejected)
        ▼
 Execution Agent  (claude-opus-4-7 + adaptive thinking)
  ─────────────────────────────────────────────────────
  Tools:   get_live_ask, submit_bracket_buy, cancel_open_orders, submit_market_sell
  Output:  order confirmation or error details
```

### What Each Agent Uses

**Signal Agent** — reads market data and live news to determine direction:
- 1-minute SMA crossover and RSI (same as `simple_ma.py`)
- Volume ratio vs 20-bar average
- Last 5 headlines from the **Alpaca News API** (Benzinga feed, real-time, no extra cost or key — uses your existing Alpaca credentials). Claude can hold a signal if news is contradictory or bearish.

**Risk Agent** — decides whether to act and at what size:
- Account equity and buying power
- `DailyLossGuard` and `StopLossCooldown` state
- **Sector relative strength**: 5-day return of the symbol minus its sector ETF (configured in `sector_etfs`). Strongly negative relative strength raises Claude's bar for approval.
- **Earnings proximity**: days until next earnings fetched via yfinance. Claude hard-rejects BUY within `earnings_blackout_days` (default 2).

**Execution Agent** — submits the order and handles edge cases:
- Fetches live ask price before computing bracket levels
- Handles the `42210000` take-profit validation error: Claude reads the error, extracts Alpaca's actual `base_price`, recomputes prices, and retries once

### News Data Source

The Signal Agent uses the **Alpaca News API** (same credentials as trading — no separate subscription needed). This is a real-time Benzinga feed filtered to market-relevant stories for your specific symbols. It is more reliable than yfinance, which scrapes Yahoo Finance and breaks silently when the page structure changes.

For reference, professional data sources by tier:

| Tier | Provider | Cost |
|------|----------|------|
| Institutional | Bloomberg, Refinitiv, Dow Jones Newswires | $10k–$24k/year |
| Quant funds | RavenPack, Benzinga Pro API, Intrinio | $500–$5k/month |
| Retail / indie | **Alpaca News (this bot)**, Polygon.io | Free–$200/month |
| Free | SEC EDGAR RSS (filing alerts) | Free |

---

## Choosing a Bot

| | `simple_ma.py` | `agent_trader.py` |
|---|---|---|
| **Cost** | **$0** | ~$15/month per symbol |
| **Latency per loop** | ~2s | ~8–15s (3 Claude API calls) |
| **Signal inputs** | Price + volume | Price + volume + live news |
| **Risk inputs** | Code-enforced rules | Rules + sector RS + earnings |
| **Decision explanation** | Single log line | Full natural-language reasoning |
| **Execution retry** | Regex-based (built-in) | Claude reasons through the retry |
| **Reliability** | Alpaca API only | Alpaca + Anthropic API both required |
| **Consistency** | 100% deterministic | May vary slightly on identical data |

**Use `simple_ma.py`** as the default. For a pure MA+RSI strategy the decisions are nearly identical; the deterministic bot is faster, cheaper, and has no external API dependency.

**Use `agent_trader.py`** when the extra inputs (news, sector context, earnings) can genuinely change the decision — which is the case when a crossover coincides with a major headline or the stock is days from reporting earnings.

### Cost breakdown — `agent_trader.py`

Signal and Risk agents use `claude-haiku-4-5` ($1.00 / $5.00 per 1M tokens).
Execution agent uses `claude-opus-4-7` ($5.00 / $25.00 per 1M tokens).

**Per loop iteration (1 symbol):**

| Agent | Model | Called when | Est. cost |
|-------|-------|-------------|-----------|
| Signal Agent | Haiku 4.5 | Every iteration | ~$0.001 |
| Risk Agent | Haiku 4.5 | Signal ≠ HOLD (~20%) | ~$0.002 |
| Execution Agent + thinking | Opus 4.7 | Trade fires (~5%) | ~$0.10 |

**Daily (390 iterations, 6.5hr day, 1 symbol):**

| Component | Qty | Cost |
|-----------|-----|------|
| Signal checks | 390 | ~$0.40 |
| Risk checks | ~20 | ~$0.04 |
| Executions (1–2 trades) | 2 | ~$0.20 |
| **Total** | | **~$0.65 / day** |

**Monthly: ~$15 / symbol. With 3 symbols: ~$45 / month.**

---

## Switching Between Paper and Live Trading

Change one line in `conf/config.yaml`:

```yaml
paper_trading: false   # true = paper, false = live
```

No code changes required. Ensure both sets of API keys are in `.env`.
