# Alpaca SMA Crossover Trading Bot

A momentum trading bot for Alpaca Markets using a Simple Moving Average (SMA) crossover strategy with RSI filtering, bracket orders, and built-in risk controls. Three bots are available — choose the one that fits your needs.

---

## Project Structure

```
alpaca/
├── conf/
│   └── config.yaml             # All tunable parameters (shared by all bots)
├── scripts/
│   ├── ma_trader.py            # Deterministic bot — zero API cost
│   ├── smart_ma_trader.py             # Recommended — deterministic execution + Claude signal
│   └── agent_trader.py         # Full multi-agent bot — all three stages use Claude
├── src/
│   ├── config.py               # Pydantic config models + loader
│   ├── agents/
│   │   ├── signal_agent.py     # Claude analyzes MA, RSI, volume, and Alpaca news
│   │   ├── risk_agent.py       # Claude checks risk, sector strength, earnings
│   │   └── execution_agent.py  # Claude submits orders via tool use
│   └── utils/
│       ├── atr.py
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
ANTHROPIC_API_KEY=sk-ant-... # needed for smart_ma_trader.py and agent_trader.py
```

### 3. Configure the bot

Edit `conf/config.yaml` — no code changes required. All bots share this file.

```yaml
trading:
  paper_trading: true          # false for live real-money trading
  trade_only_market_hours: false
  symbols: ["NBIS"]            # one or more tickers
  timeframe: "minute"
  check_interval: 60           # seconds between each loop iteration
  log_file: "trade_log.csv"
  sector_etfs:                 # maps each symbol to its sector ETF (agent_trader.py only)
    NBIS: "AIQ"
  earnings_blackout_days: 2    # skip BUY within N days of earnings (agent_trader.py only)

strategy:
  fast_ma: 3                   # fast SMA window
  slow_ma: 8                   # slow SMA window
  rsi_period: 14
  rsi_max_for_buy: 75          # skip BUY if RSI >= this
  volume_min_ratio: 1.0        # BUY only if volume >= X × 20-bar avg (0 to disable)
  use_5m_confirmation: true    # require 5-min uptrend before 1-min BUY (ma_trader.py only)
  min_signal_confidence: 0.65  # skip signal if Claude confidence < this (smart_ma_trader.py only)

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
# Zero cost — fully deterministic
uv run scripts/ma_trader.py

# Recommended — Claude signal with deterministic execution (~$0.40/day)
uv run scripts/smart_ma_trader.py

# Full multi-agent — all three stages use Claude (~$0.65/day)
uv run scripts/agent_trader.py
```

---

## Choosing a Bot

| | `ma_trader.py` | `smart_ma_trader.py` | `agent_trader.py` |
|---|---|---|---|
| **Cost** | **$0** | ~$0.40/day | ~$0.65/day |
| **Claude calls / iter** | 0 | 1 (Haiku) | 0–3 (Haiku + Opus) |
| **Signal** | Deterministic math | Claude: MA + RSI + vol + news | Claude: MA + RSI + vol + news |
| **Confidence filter** | — | Yes — skip if < 65% | — |
| **Risk check** | Deterministic code | Deterministic code | Claude: + sector RS + earnings |
| **Execution** | Deterministic code | Deterministic code | Claude + tool use |
| **Requires** | Alpaca keys | Alpaca + Anthropic keys | Alpaca + Anthropic keys |
| **Consistency** | 100% deterministic | Deterministic execution | May vary |

**`smart_ma_trader.py` is the recommended default.** It is the practical sweet spot:
- Only one Haiku call per iteration (cheap and fast)
- Claude adds genuine value on the signal — it weighs live news alongside the MA/RSI math and skips low-confidence signals
- All execution, position sizing, and risk logic remains deterministic and reliable

**`ma_trader.py`** if you want zero API cost and fully reproducible behaviour.

**`agent_trader.py`** if you want Claude to also reason about sector strength and earnings proximity when deciding whether to act on a signal.

---

## How It Works — `ma_trader.py`

### Startup

1. Config loaded and validated by Pydantic.
2. API keys read from `.env`; Alpaca clients initialized.
3. `DailyLossGuard` and `StopLossCooldown` created for the session.
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
└───────────────────────────────────────────────────────────┘
┌─ Per-symbol iteration ────────────────────────────────────┐
│  For each symbol — errors caught per-symbol               │
└───────────────────────────────────────────────────────────┘
```

### Per-Symbol Logic

#### Step 1 — Fetch 1-minute bars
Last 400 1-minute OHLCV bars from Alpaca (up to 10 days back).

#### Step 2 — Calculate signal with filters

```
fast_ma = rolling mean of close over fast_ma bars (3)
slow_ma = rolling mean of close over slow_ma bars (8)
rsi     = 14-period RSI on close prices

Initial signal:
  BUY  → fast_ma just crossed ABOVE slow_ma AND RSI < 75
  SELL → fast_ma just crossed BELOW slow_ma
  HOLD → no crossover

Volume filter (volume_min_ratio > 0):
  Suppress BUY if current_volume < volume_min_ratio × 20-bar average
  SELL is never suppressed by volume

5-minute uptrend confirmation (use_5m_confirmation = true):
  Fetch 50 × 5-min bars; suppress BUY if fast_ma ≤ slow_ma on latest 5-min bar
```

#### Step 3 — Position and cooldown check
Queries open position; detects bracket stop-loss exits; suppresses BUY during cooldown.

#### Step 4 — BUY execution

**Reference price**: `max(live_ask, bar_close)` — matches Alpaca's internal `base_price`.

**Position sizing** — three caps, smallest wins:
```
risk_based     = (equity × risk_per_trade) / (entry_price × stop_loss_pct)
position_based = (equity × max_position_pct) / entry_price
buying_power   = buying_power / (entry_price × 1.02)
qty = max(1, min(risk_based, position_based, buying_power))
```

**Bracket order**:
```
Market BUY @ market price
  ├── Take profit: limit SELL at +6%
  └── Stop loss:  stop  SELL at -1.5%
```

If Alpaca rejects with error `42210000` (tp < base_price + 0.01, common in paper trading), the bot parses the actual `base_price` from the error and retries once.

#### Step 5 — SELL execution
Marks the exit in `StopLossCooldown`, cancels open bracket legs, submits market SELL.

---

### Risk Controls Summary

| Control | Behaviour |
|---------|-----------|
| **Volume confirmation** | BUY suppressed if current volume < 1.0 × 20-bar average |
| **5-min uptrend** | BUY suppressed if 5-min fast MA ≤ slow MA |
| **Position sizing** | Three-cap formula: risk, concentration, buying power |
| **Stop loss** | Fixed 1.5% bracket leg — managed by Alpaca |
| **Take profit** | Fixed 6% bracket leg — managed by Alpaca |
| **Daily loss limit** | Halts all trading if equity falls 3% in one day; resets next morning |
| **Stop-loss cooldown** | Blocks re-entry for 30 minutes after a bracket stop fires |
| **Error isolation** | Per-symbol error handling; one bad ticker doesn't stop the others |

---

### Notifications & Trade Log

Telegram alerts on startup, every BUY/SELL, daily loss limit hit, and unhandled errors.

Every trade appended to `trade_log.csv`:
```
timestamp, symbol, action, qty, price, reason, note
2026-05-17 14:32:01, NBIS, BUY, 30, 217.86, SMA Crossover + RSI, TP=231.13
2026-05-17 15:10:44, NBIS, SELL, 30, 220.40, SMA Crossover Exit,
```

---

## How It Works — `smart_ma_trader.py`

`smart_ma_trader.py` keeps the full execution stack of `ma_trader.py` unchanged and replaces only the signal step with a Claude call.

### What changes vs `ma_trader.py`

| Step | `ma_trader.py` | `smart_ma_trader.py` |
|------|---------------|---------------|
| Signal | Deterministic MA + RSI + volume + 5-min | Claude (MA + RSI + volume + news) |
| Confidence filter | — | Skip signal if confidence < `min_signal_confidence` (0.65) |
| Position sizing | Deterministic | Identical |
| Order submission | Deterministic + regex retry | Identical |
| Risk guards | Deterministic | Identical |

### Signal Agent

The `SignalAgent` (claude-haiku-4-5) receives:
- Current MA crossover values (prev and current bar for both fast and slow MA)
- RSI value vs threshold
- Volume ratio vs 20-bar average
- Last 5 headlines from the **Alpaca News API** — real-time Benzinga feed, filtered to your symbol, no extra cost or key (uses existing Alpaca credentials)

Claude returns `BUY / SELL / HOLD` plus a confidence score (0–1) and a reasoning sentence. If confidence is below `min_signal_confidence` (default 0.65), the signal is treated as HOLD regardless of direction.

**Example log output:**
```
2026-05-17 14:31:02 | INFO | [signal] NBIS: BUY (confidence=0.82) — Bullish 3/8 MA crossover confirmed, RSI 68.4 below threshold, volume 1.4× average. No adverse headlines in last 12h.
2026-05-17 14:32:02 | INFO | NBIS @ $217.86 | Signal: BUY (82%) | Bullish 3/8 MA crossover...
```

### Cost

One Haiku call per loop iteration, whether or not a trade fires:

| Qty | Unit cost | Daily (1 symbol) |
|-----|-----------|-----------------|
| 390 signal checks | ~$0.001 | **~$0.40** |

Monthly: **~$9 / symbol**.

---

## How It Works — `agent_trader.py`

All three pipeline stages — signal, risk, and execution — use Claude.

### Three-Agent Pipeline (per symbol, per loop)

```
Position check → StopLossCooldown.update()
        │
        ▼
  Signal Agent  (claude-haiku-4-5)
  ─────────────────────────────────────────────────────────
  Inputs:  1-min MA crossover, RSI, volume ratio,
           last 5 Alpaca News headlines
  Output:  BUY / SELL / HOLD + confidence + reasoning
        │
        │  stops here if HOLD
        ▼
   Risk Agent   (claude-haiku-4-5)
  ─────────────────────────────────────────────────────────
  Inputs:  signal, account equity/BP, daily loss state,
           cooldown state, sector ETF relative strength (5-day),
           days to next earnings
  Output:  approved/rejected + qty + base_price + reasoning
        │
        │  stops here if rejected
        ▼
 Execution Agent  (claude-opus-4-7 + adaptive thinking)
  ─────────────────────────────────────────────────────────
  Tools:   get_live_ask, submit_bracket_buy,
           cancel_open_orders, submit_market_sell
  Output:  order confirmation or error details
```

### What the Risk Agent adds over `smart_ma_trader.py`

- **Sector relative strength**: 5-day return of the symbol minus its sector ETF (configured in `sector_etfs`). Strongly negative RS raises the bar for approval.
- **Earnings proximity**: days until next earnings via yfinance. Claude hard-rejects BUY within `earnings_blackout_days` (default 2) of the next report.

### News Data Source

All three bots that use Claude rely on the **Alpaca News API** — a real-time Benzinga feed filtered to your symbols, included in your Alpaca subscription. This is more reliable than yfinance, which scrapes Yahoo Finance and silently breaks when the page structure changes.

Professional data source tiers for reference:

| Tier | Provider | Cost |
|------|----------|------|
| Institutional | Bloomberg, Refinitiv, Dow Jones Newswires | $10k–$24k/year |
| Quant funds | RavenPack, Benzinga Pro API, Intrinio | $500–$5k/month |
| Retail / indie | **Alpaca News (this bot)**, Polygon.io | Free–$200/month |
| Free | SEC EDGAR RSS (filing alerts) | Free |

### Cost

| Agent | Model | Called when | Est. cost/call |
|-------|-------|-------------|---------------|
| Signal Agent | Haiku 4.5 | Every iteration | ~$0.001 |
| Risk Agent | Haiku 4.5 | Signal ≠ HOLD (~20%) | ~$0.002 |
| Execution Agent + thinking | Opus 4.7 | Trade fires (~5%) | ~$0.10 |

**Daily (390 iterations, 1 symbol): ~$0.65. Monthly: ~$15 / symbol.**

---

## Switching Between Paper and Live Trading

Change one line in `conf/config.yaml`:

```yaml
paper_trading: false   # true = paper, false = live
```

No code changes required. Ensure both sets of API keys are in `.env`.
