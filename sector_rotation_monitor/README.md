# Sector Rotation Monitor v1.1

Python toolkit for monitoring **equity sector and industry rotation** across the S&P 500, with an optional **FRED macro overlay**.
Also it is suggested to compare this data to https://finviz.com/groups
## What's new in v1.1

- **12 industry / thematic ETFs** (semiconductors, software, biotech, banks, homebuilders, retail, aerospace, transportation, oil services, …)
- **FRED macro overlay**: unemployment, claims, CPI, yield curve, industrial production, capacity utilization, consumer sentiment → heuristic cycle phase + historically favored/avoided sectors
- Separate rankings, heatmaps, and RRG charts for sectors vs industries
- Config flag `data.include_industries` and CLI `--no-macro`

## Features

| Area | Details |
|------|---------|
| Universe | 11 GICS sector SPDRs + 12 industry ETFs + SPY |
| Performance | 1D / 1W / 1M / 3M / 6M / YTD / 1Y absolute & excess returns |
| Ranking | Weighted composite rank (recent horizons emphasised) |
| RRG | RS-Ratio + RS-Momentum, four quadrants |
| Regime | Cyclical vs defensive excess spread |
| Macro | FRED series → cycle phase + sector preference map |
| Outputs | Rich console, CSV, HTML report, charts |
| Dashboard | Streamlit + Plotly (sectors / industries / all) |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# or 
uv sync

# Equity-only (no FRED key needed)
python main.py --no-macro

# Full run including macro (requires free FRED API key)
export FRED_API_KEY=your_key_here
python main.py

# Force refresh
python main.py --refresh

# Interactive dashboard
python main.py --dashboard

# Outputs go to outputs/ (HTML, CSV, PNGs) — no Streamlit needed.
python main.py --no-macro

# Start dashboard (default: http://127.0.0.1:8501)
streamlit run dashboard.py
# Then open http://127.0.0.1:8501 or http://localhost:8501

# If you need specific port
streamlit run dashboard.py --server.port 8502 --server.address 127.0.0.1
```

Get a free FRED key: https://fred.stlouisfed.org/docs/api/api_key.html

## Industry ETFs included

| Ticker | Name | Parent sector |
|--------|------|---------------|
| SMH, XSD | Semiconductors | XLK |
| IGV | Software | XLK |
| XBI, IBB | Biotech | XLV |
| KBE, KRE | Banks / Regional Banks | XLF |
| XHB | Homebuilders | XLY |
| XRT | Retail | XLY |
| ITA | Aerospace & Defense | XLI |
| XTN | Transportation | XLI |
| XES | Oil Equipment & Services | XLE |

Edit `config/sectors.yaml` to add or remove any ETF.

## FRED macro series

UNRATE, ICSA, CPIAUCSL, CPILFESL, T10Y2Y, DFF, INDPRO, UMCSENT, TCU

The classifier maps these into phases: Early Expansion, Mid Expansion, Late Expansion, Slowdown, Recession / Contraction — then shows classic sector preferences for that phase.

## Project layout

```
sector_rotation_monitor/
├── main.py / dashboard.py
├── config/sectors.yaml
├── src/
│   ├── data_fetcher.py
│   ├── analyzer.py
│   ├── macro.py          # FRED overlay
│   ├── visualizer.py
│   ├── reporter.py
│   └── config_loader.py
├── data/                 # price + FRED caches
└── outputs/              # charts, CSV, HTML
```

## Support / Resistance module

For each sector and industry ETF the tool now computes:

| Component | Description |
|-----------|-------------|
| **SMAs** | 20 / 50 / 200-day simple moving averages |
| **Daily pivots** | Classic floor-trader P, S1–S3, R1–R3 from prior session |
| **Weekly pivots** | Same formula on prior week H/L/C |
| **Nearest S/R** | Closest support below and resistance above (label + distance %) |
| **Status flags** | Above_SMA*, Golden_Stack / Death_Stack, At_Support / At_Resistance |
| **Position** | Breakout, Breakdown, At/Near Support or Resistance, Trend_Support, Mid_Range |

Outputs: console tables, `sr_sectors.csv`, `sr_industries.csv`, `support_resistance.csv`, and HTML sections. Also available as a tab in the Streamlit dashboard.

**Pivot source:** True session High/Low/Close from cached OHLC (`data/sector_ohlc.parquet`). Daily pivots use the prior completed bar; weekly pivots use the prior week’s H/L/C. Falls back to close-based approximation only if OHLC is missing. `Pivot_Source` column shows `ohlc` vs `approx`. Tolerance for "at" a level defaults to 0.5%.

## Disclaimer

Research and educational use only. Not investment advice.
