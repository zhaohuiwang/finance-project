# Guide: Stock Support & Resistance Analyzer

This guide covers **how to run** the project and **how to interpret** every metric, score, alert, and chart so you can turn the output into a practical monitoring and trading process.

> **Disclaimer:** This is educational software, not financial advice. Past reaction rates do not guarantee future results. Always manage risk and do your own research.

---

## Table of Contents

1. [Installation & Setup](#1-installation--setup)
2. [How to Run](#2-how-to-run)
3. [What the System Detects](#3-what-the-system-detects)
4. [Interpreting Levels, Strength & Score](#4-interpreting-levels-strength--score)
5. [ATR Zones](#5-atr-zones)
6. [Multi-Timeframe Alerts](#6-multi-timeframe-alerts)
7. [Volume Profile & Divergence](#7-volume-profile--divergence)
8. [VWAP](#8-vwap)
9. [Back-Test Metrics](#9-back-test-metrics)
10. [Suggested Trading & Monitoring Workflow](#10-suggested-trading--monitoring-workflow)
11. [Parameter Tuning](#11-parameter-tuning)
12. [Limitations & Best Practices](#12-limitations--best-practices)

---

## 1. Installation & Setup

```bash
cd stock-sr-analyzer

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
# Or use uv
```

**Requirements:** Python 3.10+, internet access (Yahoo Finance via `yfinance`).

---

## 2. How to Run

### A. Command-Line (batch / scripting)

```bash
# Full analysis on several tickers
python -m src.main --tickers CRWV IREN NBIS APLD --start 2025-01-01 --save --interactive

# Single ticker, tuned ATR & alerts
python -m src.main --tickers IREN --start 2025-01-01 --atr-mult 0.5 --alert-atr 1.0 --save

# Faster run (skip some modules)
python -m src.main --tickers IREN --no-backtest --no-weekly --no-alerts --save
```

**Useful flags**

| Flag | Default | Meaning |
|------|---------|---------|
| `--tickers` | CRWV IREN NBIS APLD | Space-separated symbols |
| `--start` / `--end` | 2025-01-01 / today | Date range |
| `--methods` | swing,fib,kmeans,pivot | Detection algorithms |
| `--atr-mult` | 0.5 | Zone half-width in ATR units |
| `--alert-atr` | 1.0 | Proximity alert threshold (ATR) |
| `--save` | off | Write PNG, HTML, JSON, alerts |
| `--interactive` | off | Also write Plotly HTML |
| `--no-backtest` | – | Skip reaction statistics |
| `--no-weekly` | – | Skip weekly + confluence |
| `--no-vp` | – | Skip volume profile |
| `--no-alerts` | – | Skip alert generation |
| `--no-show` | – | Do not open charts |

**Outputs** (with `--save`) go to `plots/`:

- `<TICKER>_sr_levels.png` – static chart  
- `<TICKER>_sr_interactive.html` – interactive chart (open in browser)  
- `<TICKER>_levels.json` – all levels + zones  
- `<TICKER>_alerts.txt` – multi-timeframe alerts  
- `<TICKER>_vp_divergence.txt` – volume-profile divergences (if any)

### B. Streamlit Dashboard (interactive UI)

```bash
streamlit run src/dashboard.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

**Sidebar controls**

- **Tickers** – comma-separated list (e.g. `CRWV,IREN,NBIS,APLD,CIFR`)
- **Start date**
- **Detection methods** – check/uncheck swing, kmeans, fib, pivot
- **Weekly + Confluence**, **Volume Profile**, **Back-test** – toggles
- **ATR zone multiplier** – slider
- **Alert proximity (ATR)** – slider
- Click **Run Analysis**

Each ticker gets its own tab with KPIs, alerts, chart, levels table, and back-test.

---

## 3. What the System Detects

| Method | Idea | Best for |
|--------|------|----------|
| **Swing + clustering** | Local highs/lows clustered into zones | Oscillating / range-bound stocks |
| **K-Means** | Unsupervised clustering of extrema | Dense price areas |
| **Fibonacci** | Retracements of recent major swing | After sharp legs up/down |
| **Pivot points** | Classic floor-trader pivots | Short-term reference |
| **Weekly levels** | Same detectors on weekly OHLC | Higher-timeframe structure |
| **Confluence** | Level appears on both daily *and* weekly | Highest-conviction zones |
| **Volume Profile** | POC, Value Area High/Low, high-volume nodes | Where real volume traded |
| **VWAP** | Volume-weighted average price | Dynamic “fair value” |
| **ATR zones** | Level expanded by ± (mult × ATR) | Realistic support/resistance *bands* |

These names (CRWV, IREN, NBIS, APLD, etc.) have often traded in **ranges with repeated oscillations**. Horizontal levels + volume nodes tend to matter more than pure trendlines in that regime.

---

## 4. Interpreting Levels, Strength & Score

### Level fields

| Field | Meaning |
|-------|---------|
| **Price** | Center of the level / zone |
| **Kind** | `support`, `resistance`, or `both` |
| **TF (timeframe)** | `daily`, `weekly`, or `confluence` |
| **Strength** | Raw touch / cluster size (+ boosts from weekly, VP, confluence) |
| **Score** | 0–100 composite from historical reaction back-test (see §9) |
| **Method** | How it was found (e.g. `swing+vp`, `confluence(kmeans+weekly_kmeans)`) |

### How to rank levels (priority order)

1. **Confluence** + high Score (≥ 60–70)  
2. **Weekly** levels with decent Score  
3. **Daily** levels near high-volume nodes (method contains `+vp`)  
4. Pure daily levels with low Score – treat as secondary

### Strength vs Score

- **Strength** = “how many times price touched this area” (structural).  
- **Score** = “when it was touched, how often and how far did price bounce?” (behavioral).

A level can have high strength but mediocre Score (many touches, weak bounces). Prefer levels that are strong on **both**.

### Distance

In the CLI table, **Dist%** is how far the level is from the last close.  
In alerts, distance is also shown in **ATR units** (more stable across volatility regimes).

---

## 5. ATR Zones

Each level is expanded into a zone:

```
zone_low  = price − (atr_mult × ATR(14))
zone_high = price + (atr_mult × ATR(14))
```

Default `atr_mult = 0.5`.

**Why zones, not lines?**  
Support/resistance are areas, not exact prices. ATR adapts the width to current volatility.

**Interpretation**

- Price **inside** a high-Score support zone → watch for bounce or breakdown.  
- Price **approaching** a resistance zone from below → watch for rejection or breakout.  
- Wider mult (0.8–1.0) → more forgiving on very volatile names.  
- Tighter mult (0.3–0.4) → stricter definition of “at the level”.

---

## 6. Multi-Timeframe Alerts

### Severity

| Tag | Meaning | Suggested response |
|-----|---------|-------------------|
| **ACTION** | Confluence / high-Score level nearby, or a potential break | Prioritize attention; consider entry/exit plan |
| **WATCH** | Ordinary proximity or recent touch | Monitor; no forced action |
| **INFO** | Informational only | Log and move on |

### Alert types

- **Proximity** – price within `--alert-atr` ATRs of a level.  
- **Recent touch** – level was tested in the last few bars; watching for bounce.  
- **Potential BREAK** – price has pushed through the zone; trend may be changing.

**Practical rule of thumb**

- Multiple **ACTION** alerts on the **same** confluence support → high-interest long watch.  
- **ACTION** break of confluence support on expanding volume → respect the break; wait for retest.  
- Isolated **WATCH** on a weak daily level → ignore or low priority.

---

## 7. Volume Profile & Divergence

### Core VP concepts

| Term | Meaning |
|------|---------|
| **POC** | Point of Control – price with the most volume (fair-value magnet) |
| **VAH / VAL** | Value Area High / Low – band containing ~70% of volume |
| **HVN** | High-volume node – strong acceptance |
| **LVN** | Low-volume node – price often moves quickly through |

Price tends to **revert toward POC** in balance and **accept outside the Value Area** when a new trend starts.

### Divergence signals (detailed)

| Signal | What it means | Bias | How to use |
|--------|---------------|------|------------|
| **Bearish POC divergence** | Price prints a higher high while the rolling POC is flat or falling | Rally is not attracting volume at higher prices → possible exhaustion | Prefer fading strength near resistance; avoid chasing longs |
| **Bullish POC divergence** | Price prints a lower low while the rolling POC is flat or rising | Selloff is not attracting volume at lower prices → possible exhaustion | Prefer buying dips near support; avoid chasing shorts |
| **Volume exhaustion** | New swing high/low on clearly below-average volume | Move lacks participation | Lower confidence in continuation; wait for confirmation |
| **VA rejection** | Price spikes outside VAH/VAL then closes back inside | Failed acceptance of new value | Classic mean-reversion toward POC |

**Core idea:** In a healthy trend, value (POC) migrates *with* price. When price runs away from value without POC following, the move is “thin” and more likely to revert.

Use divergence as a **warning / filter**, not a standalone entry. Highest value when it appears **at** a high-Score confluence S/R zone.

---

## 7b. Order Flow Proxies (from OHLCV)

True order flow needs tick or bid/ask data. This project builds **practical proxies** from standard OHLCV:

| Tool | Approximation | Signal |
|------|---------------|--------|
| **Volume Delta** | Up-volume − Down-volume (close vs open, or close vs prior close) | Net buying/selling pressure per bar |
| **CVD (Cumulative Volume Delta)** | Running sum of delta | Trend of aggressive participation |
| **Delta divergence** | Price HH + CVD lower high (bearish); price LL + CVD higher low (bullish) | Exhaustion similar to classic divergence |
| **Absorption** | High volume + small range | Large participation, little progress → possible absorption |
| **Swing imbalance** | Weak/opposite delta at swing high or low | High/low not confirmed by volume pressure |
| **Stacked imbalance** | Several consecutive bars with strong same-sign delta | Persistent one-sided pressure |

### Interpreting order-flow signals

| Signal | Interpretation | Suggested stance |
|--------|----------------|------------------|
| **Bearish delta divergence** | Price higher, cumulative buying pressure weaker | Caution on longs; stronger near resistance |
| **Bullish delta divergence** | Price lower, cumulative selling pressure weaker | Caution on shorts; stronger near support |
| **Absorption** | Big volume, tiny range | Possible turning point; wait for direction of next bars |
| **Imbalance at high** | New high on weak/negative delta | High may be vulnerable |
| **Imbalance at low** | New low on weak/positive delta | Low may be vulnerable |

**Important limitations**

- Daily OHLCV delta is a **proxy**, not footprint/order-flow data from a DOM.
- Up/down split assumes close>open ≈ buying pressure (reasonable but imperfect).
- Best used as **confirmation** of S/R + VP divergence, not alone.

**Combined high-conviction setup example**

1. Price enters confluence support ATR zone (Score ≥ 60).  
2. Bullish POC or delta divergence present (or no bearish divergence).  
3. Optional: absorption or positive imbalance near the low.  
4. Invalidation still = close beyond far side of the ATR zone.

---

## 8. VWAP (Volume-Weighted Average Price)

VWAP is the volume-weighted average of price over a period. It answers: “Where did the bulk of traded volume actually clear?”

### VWAP bands

VWAP ± 1σ and ± 2σ (volume-aware standard deviation of typical price vs VWAP).

| Zone | Interpretation |
|------|----------------|
| **inside_1_std** | Near fair value |
| **between_upper_1_and_2** / **lower** | Extended; mean-reversion candidates in ranges |
| **above_upper_2** / **below_lower_2** | Stretched; higher chance of pullback *or* strong trend continuation |

In a **range**, fades of ±2σ toward VWAP are common. In a **strong trend**, price can walk the outer band.

### Variants in this project

| Variant | Definition | Typical use |
|---------|------------|-------------|
| **Cumulative VWAP** | From the first bar of your loaded range to now | Fair value for the whole study period |
| **Rolling VWAP (20 / 50)** | VWAP over last N bars | Shorter-term dynamic pivot |
| **Anchored VWAP (from swing low)** | VWAP starting at the most recent major low | Trend support after a bottom |
| **Anchored VWAP (from swing high)** | VWAP starting at the most recent major high | Trend resistance after a top |

CLI prints these values; charts plot cumulative VWAP; Streamlit shows the same line.

### How to read VWAP

- **Price above VWAP** → average participant is long vs that period’s volume → constructive for longs.  
- **Price below VWAP** → average participant is short vs that period → more defensive.  
- **In a range:** VWAP often acts as a mean-reversion magnet (fade extremes back to VWAP).  
- **In a trend:** price can ride one side of VWAP for a long time; a close back through VWAP is a stronger regime signal.  
- **Anchored VWAP from swing low:** holding above it supports the bounce narrative; losing it weakens the bounce.  
- **Anchored VWAP from swing high:** rejecting it supports continuation of the decline.

**Combine with S/R:** support + price reclaiming / holding above VWAP is generally more constructive than support while price remains deep below VWAP.

---

## 8b. Footprint Charts & Tick Data (what is / isn’t available)

**Footprint charts** show volume traded **at each price** inside a bar, usually split into buy (ask) vs sell (bid) volume, plus delta and imbalances per row.

### What true footprint needs

- Tick trades with **aggressor side** (buy vs sell), **or**
- Bid/ask volume at price (DOM / L2)

**Yahoo Finance OHLCV does not provide this.** Therefore this project **does not draw footprint charts**.

### What we use instead (proxies)

| Proxy | Role |
|-------|------|
| Volume Profile (POC / VA) | Where volume concentrated over many bars |
| Delta / CVD (close vs open split) | Net pressure proxy |
| Absorption / imbalance | High volume + small range; weak delta at extremes |
| VWAP variants | Volume-weighted fair value |

For real footprints, use a data vendor (e.g. Databento, Polygon, futures feed, or crypto exchange WebSocket trades) and specialized tools (TradingView footprint, Bookmap, Jigsaw, Quantower, or Python libs that consume tick CSVs). See `src/footprint_notes.py` for the data contract.

---

## 8c. Specific Trigger Examples

These are **illustrative process rules**, not guarantees. Always define risk first.

### Example A — Long near confluence support (range regime)

**Conditions (all preferred):**
1. Price enters ATR zone of a **confluence support** with Score ≥ 60.  
2. No active **bearish** POC or delta divergence.  
3. Optional: bullish POC/delta divergence or absorption near the low.  
4. Price holds or reclaims **VWAP** (or anchored VWAP from swing low) on the bounce.  
5. **ACTION** proximity/touch alert on that same support.

**Invalidation:** Daily close below the support zone low (or zone − 0.5 ATR).  
**Target idea:** Next opposing high-Score resistance, or POC / VWAP if mean-reverting.

### Example B — Short near confluence resistance

Mirror of A at confluence resistance: Score ≥ 60, no bullish divergence, optional rejection at VAH, price failing under VWAP.

### Example C — Respect a breakdown

1. **ACTION** “potential BREAK” of confluence support.  
2. Volume on the break bar above recent average (or no bullish exhaustion).  
3. Prefer wait for **retest** of broken support as resistance (price returns into the ATR zone from below and fails).  
4. Invalidation: reclaim and close back above the zone.

### Example D — Fade thin rally into resistance

1. Price approaches confluence resistance (Score ≥ 60).  
2. **Bearish POC divergence** and/or **bearish delta divergence** present.  
3. Optional: VA rejection at VAH or weak delta at the swing high.  
4. Entry interest on rejection structure; stop above zone high.

### Example E — Stand aside

- High-Score levels far from price (> 2–3 ATR) → no action.  
- Conflicting signals (bullish divergence but breaking support on rising volume) → wait.  
- Low Score daily-only levels only → ignore for primary decisions.

---

## 8d. Where to Gauge All Signals & Metrics

Use this map so you always know **where** each piece lives.

### 1. Streamlit dashboard (best overview)

```bash
streamlit run src/dashboard.py
```

| What | Where in UI |
|------|-------------|
| Tickers / dates / ATR / alert settings | **Sidebar** |
| Last price, ATR, VWAP, # levels, # alerts | **KPI row** at top of each ticker tab |
| Multi-TF alerts | **Alerts** section (ACTION / WATCH) |
| VP divergence | **Volume Profile Divergence** section |
| Order-flow proxies | **Order Flow Proxies** section |
| Candles + VWAP + ATR bands + S/R zones | **Interactive chart** |
| Full level list + zone low/high/width/Score | **Levels & ATR Zones** table |
| Touches / win% / Score | **Reaction Back-test** table |

**This is the primary place to “see everything at once.”**

### 2. CLI terminal output

```bash
python -m src.main --tickers IREN --start 2025-01-01 --save
```

Scroll order typically:
1. Levels table (Price, Kind, Str, Score, TF, Method, Dist%)  
2. Back-test table (Touches, Bounces, Win%, AvgBounce, Score)  
3. ATR + VWAP summary line  
4. Multi-timeframe alerts  
5. VP divergence block  
6. Order-flow proxy block  
7. Summary line (last, VWAP, nearest S/R)

### 3. Saved files (`plots/` with `--save`)

| File | Contents |
|------|----------|
| `<T>_sr_levels.png` | Static chart with levels + VWAP |
| `<T>_sr_interactive.html` | Zoomable Plotly chart — open in browser |
| `<T>_levels.json` | Machine-readable levels, scores, ATR, zones |
| `<T>_alerts.txt` | Alert text dump |
| `<T>_vp_divergence.txt` | VP divergence messages (if any) |
| `<T>_order_flow.txt` | Order-flow proxy messages (if any) |

### 4. Recommended daily workflow

1. Open **Streamlit** → set tickers → **Run Analysis**.  
2. For each ticker tab: read **ACTION alerts** → check **VP / order-flow** sections → glance at chart (price vs zones & VWAP).  
3. Open **interactive HTML** if you need to zoom a specific date range.  
4. Optionally re-run CLI with `--save` to archive JSON/alerts for your journal.  
5. Mark only 2–4 priority zones on your execution platform (broker/TradingView).

### 5. What is *not* in this project

- Live footprint / DOM / true bid-ask delta  
- Automated order placement  
- Real-time streaming (batch analysis on demand)

For footprints, use a tick data vendor + dedicated order-flow software; use this project for **swing/daily structure, S/R, VP, VWAP, and OHLCV-based filters**.

---

## 9. Back-Test Metrics

For each level the system looks at historical touches and measures the next ~12 bars:

| Metric | Meaning |
|--------|---------|
| **Touches** | How many distinct tests of the level |
| **Bounces** | Tests that produced a favorable move (up from support, down from resistance) |
| **Win %** | Bounces / Touches |
| **Avg Bounce %** | Average size of favorable moves after a touch |
| **Score (0–100)** | Weighted mix: touch count (30%) + win rate (40%) + avg bounce size (30%) |

### How to use Score

| Score | Rough interpretation |
|-------|----------------------|
| **80–100** | Historically very reliable reactions |
| **60–80** | Useful; worth watching |
| **40–60** | Secondary; need confluence or other confirmation |
| **< 40** | Low priority |

Score is **backward-looking**. A level can stop working when the regime changes (e.g. range → strong trend). Re-run the analysis periodically.

---

## 10. Suggested Trading & Monitoring Workflow

This is a **process**, not a signal service.

### Daily / session routine

1. **Run the analyzer** (CLI or Streamlit) on your watchlist.  
2. **Scan ACTION alerts** first – especially confluence + high Score.  
3. **Mark 2–4 key zones** per ticker on your charting platform (or use the interactive HTML).  
4. **Note VP divergences** – treat as early warnings near those zones.  
5. **Check distance to VWAP** and whether price is inside an ATR zone.

### Example playbook (range / oscillation regime)

**Long bias near support**

- Price enters a **confluence support** ATR zone.  
- Score ≥ 60–70.  
- No active bearish POC divergence / volume exhaustion at the low.  
- Prefer price reclaiming VWAP or holding above it after the bounce.  
- Invalidation: daily close below the zone low (or below zone − 0.5 ATR).

**Short bias near resistance**

- Symmetric rules at confluence resistance.  
- Invalidation: daily close above the zone high.

**Breakout / breakdown**

- **ACTION** “potential BREAK” of a confluence level + expanding volume → respect the break.  
- Wait for a retest of the broken level (old support becomes resistance, or vice versa) before acting, when possible.

### Position & risk ideas (illustrative only)

- Risk a fixed fraction of capital per idea (e.g. 0.5–1%).  
- Stop beyond the far side of the ATR zone (or beyond zone + 0.5 ATR).  
- Scale out toward the next opposing high-Score level or toward POC / VWAP.  
- Reduce size when Score is only moderate or when divergence conflicts with the trade direction.

### Monitoring cadence

| Cadence | Action |
|---------|--------|
| **Daily** | Re-run alerts; update zone proximity |
| **2–3× per week** | Full re-analysis (levels can shift after big swings) |
| **After major news / earnings** | Re-run immediately; structure can change fast |
| **Weekly** | Review which levels still have high Score; drop dead ones |

---

## 11. Parameter Tuning

| Situation | Suggestion |
|-----------|------------|
| Very volatile name (wide daily ranges) | `--atr-mult 0.7`–`1.0`, `--alert-atr 1.2`–`1.5` |
| Quieter period / tighter range | `--atr-mult 0.3`–`0.4`, `--alert-atr 0.6`–`0.8` |
| Want fewer, higher-quality levels | Raise min-strength conceptually by focusing on Score ≥ 60 and confluence only |
| Noisy alerts | Increase `--alert-atr` so only closer approaches fire, or focus on ACTION only |
| Fresh IPO / short history | Shorten `--start`; weekly levels may be sparse – lean on daily + VP |

---

## 12. Limitations & Best Practices

**Limitations**

- Levels are derived from **history**; they fail more often in strong one-way trends.  
- Volume profile is an approximation (bar volume spread across high–low).  
- Back-test Score uses a simple bounce/break definition; it is not a full strategy back-test.  
- Yahoo Finance data can lag or rate-limit; cache helps but is not real-time.  
- No order execution, portfolio management, or brokerage integration.

**Best practices**

- Prefer **confluence + high Score + ATR zone** over any single indicator.  
- Treat divergence as a **filter**, not a trigger.  
- Re-run after large range expansions so Fibonacci and weekly structure stay current.  
- Combine with your own higher-timeframe bias and fundamental view of the name.  
- Journal which levels actually reacted; over time you will learn which methods work best on *your* watchlist.

---

## Quick Reference Card

```
Priority zones     = Confluence + Score ≥ 60–70 + near current price
Entry interest     = Price enters ATR zone of priority support/resistance
Confirmation       = Bounce structure + no conflicting VP divergence
Invalidation       = Close beyond far side of ATR zone
Alerts to act on   = ACTION severity, especially confluence
Alerts to watch    = WATCH proximity / recent touch
Ignore             = Low Score daily-only levels far from price
Re-run             = Daily (alerts) / several times per week (full levels)
```

---

## Support

- CLI help: `python -m src.main --help`  
- Dashboard: edit tickers and parameters in the sidebar, then **Run Analysis**  
- Project layout and feature list: see `README.md`

Use the interactive HTML charts and the Streamlit app to explore; use the JSON/alerts files if you want to pipe results into your own scripts or scanners.
