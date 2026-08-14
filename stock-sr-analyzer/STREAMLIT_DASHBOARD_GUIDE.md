# Streamlit Dashboard Guide — Where to Look for Support & Resistance

This guide maps every section of the Streamlit UI and shows **what values to read** to gauge support and resistance for a stock on a given day or week. It ends with concrete **support** and **resistance** examples.

Run the dashboard:

```bash
cd stock-sr-analyzer
source .venv/bin/activate   # if you use a venv
streamlit run src/dashboard.py
```

Open the URL shown (usually `http://localhost:8501`). Set tickers in the sidebar, click **Run Analysis**, then open the tab for the stock you care about.

---

## 1. Layout (top → bottom)

```
┌─ Sidebar (left) ─────────────────────────────┐
│ Settings: tickers, dates, methods, ATR, …    │
│ [Run Analysis]                               │
└──────────────────────────────────────────────┘

┌─ Main area ──────────────────────────────────┐
│ Tabs: one tab per ticker (e.g. IREN | NBIS)  │
│                                              │
│ 1) KPI row (5 metrics)                       │
│ 2) Captions (VWAP bands + order-flow summary)│
│ 3) Multi-Timeframe Alerts                    │
│ 4) Volume Profile Divergence                 │
│ 5) Order Flow Proxies                        │
│ 6) Chart (candles + VWAP + bands + S/R zones)│
│ 7) Table: Levels & ATR Zones                 │
│ 8) Table: Reaction Back-test                 │
└──────────────────────────────────────────────┘
```

---

## 2. Sidebar (inputs only)

| Control | Purpose |
|---------|---------|
| **Tickers (comma-separated)** | Symbols to analyze (e.g. `CRWV,IREN,NBIS,APLD`) |
| **Start date** | History window |
| **Detection methods** | swing / kmeans / fib / pivot |
| **Weekly + Confluence** | Higher-timeframe levels |
| **Volume Profile** | POC / VA enrichment |
| **Reaction Back-test** | Score table on/off |
| **ATR zone multiplier** | Width of S/R bands (default `0.5` = ±0.5×ATR) |
| **Alert proximity (ATR)** | How close price must be to fire an alert |
| **Run Analysis** | Required after changing settings |

The sidebar does not show S/R results—only settings.

---

## 3. Per-ticker tab — where each signal lives

### 3.1 KPI row (five metrics at the top)

| On-screen label | Meaning | Use for S/R |
|-----------------|---------|-------------|
| **Last Close** | Latest close | Compare to zone low/high |
| **ATR(14)** | Average true range | Zone width and “normal” move size |
| **VWAP** | Cumulative volume-weighted average price | Dynamic fair value |
| **Levels kept** | Number of filtered levels | Sanity check |
| **Alerts** | Number of proximity/break alerts | If > 0, read the Alerts section |

**Glance first:** Last Close, ATR, VWAP.

---

### 3.2 Captions (directly under KPIs)

**VWAP bands caption** (example):

```text
VWAP bands: zone=inside_1_std | VWAP=39.63 | dist=12.65% | ±1σ [22.02, 57.24]
```

| Field | Meaning |
|-------|---------|
| **zone** | `inside_1_std`, `between_upper_1_and_2`, `above_upper_2`, `between_lower_1_and_2`, `below_lower_2` |
| **VWAP** | Cumulative VWAP |
| **dist** | % distance of last price from VWAP |
| **±1σ [low, high]** | Inner band edges |

**Order-flow caption** (example):

```text
Order-flow (20d): pressure=sell | up=49% dn=51% | net_delta=-20.7M | cvd_chg=-114M
```

| Field | Meaning |
|-------|---------|
| **pressure** | Net buy vs sell bias (~20 days) |
| **up / dn %** | Up- vs down-volume share (proxy) |
| **net_delta / cvd_chg** | Direction of participation |

Use captions as **context**, not as the S/R price itself.

---

### 3.3 Section: Multi-Timeframe Alerts

Example line:

```text
🔴 ACTION – Price is 0.16 ATR below resistance (confluence, str=15)
   `45.28` | -0.16 ATR | score=96 | confluence
```

| Piece | Meaning |
|-------|---------|
| 🔴 / 🟡 | ACTION vs WATCH |
| Message | Proximity, recent touch, or potential break |
| `` `45.28` `` | **Level price** (the support or resistance) |
| `±0.16 ATR` | Distance from last close |
| `score=96` | Historical reaction quality |
| `confluence` / `weekly` / `daily` | Timeframe |

**For S/R today/this week:** prioritize **ACTION** rows whose level is your nearest support or resistance.

---

### 3.4 Section: Volume Profile Divergence

Appears only when signals exist. Example:

```text
🔴 bullish_poc – Bullish POC divergence: price lower low … while POC rising …
```

**Role:** filter — does volume/POC **agree** with defending support or rejecting resistance?

---

### 3.5 Section: Order Flow Proxies

Example:

```text
🔴 stacked_imbalance – Stacked sell imbalance: 5 consecutive bars …
🟡 imbalance – Weak/negative delta at swing high 61.53 …
```

**Role:** filter — stacked sell into support weakens a long idea; weak delta at a swing high questions that high as strong resistance hold, etc.

---

### 3.6 Section: Chart

Interactive Plotly chart (zoom, pan, hover).

| Visual | What it is | S/R use |
|--------|------------|---------|
| Candlesticks | OHLC | Price path |
| Orange solid line | VWAP | Fair value |
| Orange dashed | VWAP ±1σ | Inner band |
| Orange dotted | VWAP ±2σ | Outer band |
| Light blue fill | ±1 ATR around close | Volatility context |
| Horizontal lines | Level centers | Core S/R prices |
| Shaded horizontal bands | ATR **zones** around levels | Real S/R *area* |
| Line style | Solid ≈ weekly/confluence; dashed ≈ daily | Prefer solid |
| Color | Green-ish support / red-ish resistance / blue both | Role |
| Right-side labels | Level price | Exact number |
| Bottom panel | Volume | Context |

**How to read for S/R:**

1. Last candle vs **green shaded** zones below → nearest supports.  
2. Last candle vs **red shaded** zones above → nearest resistances.  
3. Prefer **solid** bands (weekly/confluence).  
4. Note VWAP and whether price is stretched on outer VWAP bands.

---

### 3.7 Table: Levels & ATR Zones (main S/R table)

| Column | Use |
|--------|-----|
| **Price** | Center of the level |
| **Zone Low** | Bottom of ATR band |
| **Zone High** | Top of ATR band |
| **Width %** | Zone width in percent |
| **Kind** | support / resistance / both |
| **TF** | **confluence** > weekly > daily |
| **Strength** | Touch/cluster size |
| **Score** | 0–100 reaction quality |
| **Method** | Source (`confluence(...)`, `swing+vp`, …) |

**Workflow:**

1. Prefer rows with **TF = confluence** (or weekly) and **Score ≥ 60**.  
2. Nearest **support**: Kind = support (or both), Zone still relevant below/at price.  
3. Nearest **resistance**: Kind = resistance (or both), Zone relevant above/at price.  
4. Operational band = **Zone Low → Zone High** (not a single tick).

---

### 3.8 Table: Reaction Back-test (top levels)

| Column | Meaning |
|--------|---------|
| **Price** | Level |
| **Kind** | support / resistance |
| **Touches** | Historical tests |
| **Bounces** | Favorable reactions |
| **Win %** | Bounce rate |
| **Avg Bounce %** | Typical favorable move |
| **Score** | Composite 0–100 |

Use to confirm that a level from the levels table **behaved** like S/R historically.

---

## 4. Suggested reading order (one ticker)

1. KPI row — Last, ATR, VWAP  
2. Captions — VWAP band zone + OF pressure  
3. Alerts — ACTION lines → note level prices  
4. Chart — those prices as shaded zones vs last candle  
5. Levels & ATR Zones table — Zone Low/High, TF, Score  
6. Back-test table — Score / Win %  
7. VP Divergence + Order Flow — agree/disagree only  

---

## 5. Priority rules (short)

| Priority | Prefer |
|----------|--------|
| 1 | **Confluence** + Score ≥ 60–70 |
| 2 | **Weekly** + solid Score |
| 3 | Daily near high-volume nodes (`+vp` in Method) |
| 4 | Weak daily-only levels far from price → ignore for primary S/R |

**Day:** nearest high-priority support below and resistance above.  
**Week:** lean on weekly + confluence only when possible.

---

## 6. Worked examples

Numbers below are **illustrative** (shaped like real dashboard output). Always use the live values from your Run Analysis.

### Example A — Support case (buying interest / bounce watch)

**Setup (fictional ticker XYZ, last close = 44.65, ATR ≈ 4.0)**

| Source on dashboard | What you see |
|---------------------|--------------|
| KPI | Last Close **44.65**, ATR **4.04**, VWAP **39.63** |
| VWAP caption | zone=`inside_1_std`, dist to VWAP ≈ +12.6% |
| OF caption | pressure=`sell` (mild) — slight caution |
| Alerts | 🔴 ACTION: Price is **0.03 ATR above support** `` `44.54` `` score=96 TF=**daily** |
| Alerts | 🔴 ACTION: confluence support interest near `` `40.89` `` score=100 (farther) |
| Chart | Green shaded band roughly **42.5–46.5** around 44.5; price sitting in upper half of band |
| Levels table | Price **44.54**, Kind **support**, TF **daily**, Zone Low **42.5**, Zone High **46.5**, Score **96** |
| Levels table | Price **40.89**, Kind **support**, TF **confluence**, Zone Low **38.9**, Zone High **42.9**, Score **100** |
| Back-test | 44.54: Touches 21, Win% 90%, Score 96 |
| VP / OF | No active *bearish* POC divergence at the low; no stacked sell *into* 44.5 right now |

**How to gauge support for this day**

- **Primary near-term support band:** ~**42.5 – 46.5** centered on **44.54** (daily, Score 96). Price is already in/near this zone → active test.  
- **Stronger structural support below:** ~**38.9 – 42.9** at **40.89** (confluence, Score 100). Relevant if 44.5 fails.  
- **Conviction:** High on 44.5 for a *reaction* watch (score + alert); confluence 40.89 is the “line in the sand” for the week if the near zone breaks.  
- **Filter note:** Mild sell pressure in the 20d caption → prefer confirmation (hold/reclaim of zone, or bounce structure) before treating 44.5 as a hard floor.  
- **Invalidation (process rule):** daily close **below Zone Low** of the zone you are using (e.g. below ~42.5 for the near support, or below ~38.9 for the confluence floor).

**One-sentence summary:**  
Support is first the **44.54 daily zone (42.5–46.5, Score 96)** currently under price; next major support is **confluence 40.89 (38.9–42.9, Score 100)**.

---

### Example B — Resistance case (rejection / fade or break watch)

**Setup (same last = 44.65, ATR ≈ 4.0)**

| Source on dashboard | What you see |
|---------------------|--------------|
| KPI | Last **44.65**, ATR **4.04**, VWAP **39.63** (price above VWAP) |
| VWAP caption | still `inside_1_std` (not yet extreme on outer band) |
| Alerts | 🔴 ACTION: Price is **0.16 ATR below resistance** `` `45.28` `` score=96 TF=**confluence** |
| Alerts | 🟡 WATCH: recent touch of resistance near `` `47.22` `` score=98 |
| Chart | Red shaded band ~**43.3–47.3** around 45.28; price just under / into lower edge of band |
| Levels table | Price **45.28**, Kind **resistance**, TF **confluence**, Zone Low **43.3**, Zone High **47.3**, Score **96** |
| Levels table | Price **49.91**, Kind **resistance**, TF **confluence**, Zone Low **47.9**, Zone High **51.9**, Score **100** (overhead) |
| Back-test | 45.28: high Win% / Score ~96 |
| VP / OF | Optional: bearish POC or stacked buy imbalance *into* 45–47 would strengthen a **rejection** idea; absence means wait for price action |

**How to gauge resistance for this day**

- **Primary resistance band:** ~**43.3 – 47.3** centered on **45.28** (confluence, Score 96). Price is within ~0.16 ATR → active test of resistance.  
- **Next resistance above:** ~**47.9 – 51.9** at **49.91** if 45.28 is accepted (break and hold above Zone High).  
- **Conviction:** High that **45.28 confluence** is the level that matters *today*; Score and TF both support it.  
- **Two-sided watch:**  
  - **Rejection:** fail inside/under the zone → resistance holds.  
  - **Break:** daily close **above Zone High (~47.3)** → resistance may flip; then 49.91 becomes the next reference.  
- **VWAP context:** price already above VWAP → upside has some participation behind it; a break of 45.28 is more plausible than if price were deeply below VWAP, but confluence resistance still deserves respect until broken.

**One-sentence summary:**  
Resistance is first the **45.28 confluence zone (43.3–47.3, Score 96)** immediately overhead; next major resistance is **49.91 confluence** if that zone is cleared.

---

### Example C — Same stock, “both sides” snapshot (day)

| Role | Level (Price) | Zone (Low–High) | TF | Score | Dashboard cues |
|------|---------------|-----------------|----|-------|----------------|
| **Support** | 44.54 | 42.5 – 46.5 | daily | 96 | ACTION alert, green band on chart, in levels table |
| **Support (deeper)** | 40.89 | 38.9 – 42.9 | confluence | 100 | Levels table + chart lower green band |
| **Resistance** | 45.28 | 43.3 – 47.3 | confluence | 96 | ACTION alert, red band on chart |
| **Resistance (higher)** | 49.91 | 47.9 – 51.9 | confluence | 100 | Levels table above |

**Trading-process reading (not advice):**  
Price is **between** near support 44.54 and near resistance 45.28 — a tight coil. The **week’s** more important map is still **40.89 support** and **45.28 / 49.91 resistance** on confluence. Use alerts + chart position to see which edge is being tested *today*.

---

## 7. Copy-paste checklist (Streamlit)

```
[ ] Sidebar: correct tickers → Run Analysis → open ticker tab
[ ] KPI: Last Close, ATR, VWAP
[ ] Captions: VWAP zone + OF pressure
[ ] Alerts: list ACTION level prices (support vs resistance)
[ ] Chart: green bands below / red bands above last candle (prefer solid)
[ ] Levels table: confluence/weekly, Score ≥ 60, Zone Low–High
[ ] Back-test: confirm Score / Win% on those prices
[ ] VP + Order Flow: any conflict with the bounce/rejection idea?
[ ] Write down: primary support zone, primary resistance zone, invalidation (close beyond far side of zone)
```

---

## 8. Related docs

| File | Contents |
|------|----------|
| `README.md` | Setup, features, CLI |
| `GUIDE.md` | Full metric interpretation, triggers, workflow |
| `STREAMLIT_DASHBOARD_GUIDE.md` | This file — UI map + S/R examples |

---

*Not financial advice. Levels and scores are historical analytics only; always manage risk.*
