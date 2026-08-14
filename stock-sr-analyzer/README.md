# Stock Support & Resistance Analyzer

Algorithmic support/resistance detection and filters for oscillating / range-bound stocks (e.g. CRWV, IREN, NBIS, APLD and similar names).

**Full how-to and interpretation:** see [`GUIDE.md`](GUIDE.md).

---

## Feature Matrix

| Feature | CLI | Streamlit |
|---------|:---:|:---------:|
| Swing / K-Means / Fibonacci / Pivot S/R | ✅ | ✅ |
| Weekly levels + daily/weekly **confluence** | ✅ | ✅ |
| Volume Profile (POC, Value Area) | ✅ | ✅ |
| **Volume Profile divergence** (POC migration, exhaustion, VA rejection) | ✅ | ✅ |
| **VWAP** (cumulative, rolling, anchored from swings) | ✅ | ✅ |
| **VWAP bands** (±1σ / ±2σ) | ✅ | ✅ |
| **ATR-normalized zones** | ✅ | ✅ |
| **Multi-timeframe alerts** (proximity / touch / break) | ✅ | ✅ |
| **Order-flow proxies** (delta, CVD, absorption, swing & stacked imbalance) | ✅ | ✅ |
| Reaction back-test + composite **Score (0–100)** | ✅ | ✅ |
| Static PNG charts | ✅ | – |
| Interactive Plotly HTML | ✅ | ✅ (live) |
| Streamlit dashboard | – | ✅ |

> **Not included:** true footprint / DOM charts (requires tick data with aggressor side). See `src/footprint_notes.py` and GUIDE.md.

---

## Setup

```bash
cd stock-sr-analyzer

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Or use uv
```

---

## Quick Start

### CLI

```bash
# Full analysis
python -m src.main --tickers CRWV IREN NBIS APLD --start 2025-01-01 --save --interactive

# Tuned ATR zones & alerts
python -m src.main --tickers IREN --atr-mult 0.5 --alert-atr 1.0 --save
```

Outputs (with `--save`) go to `plots/`:
- `*_sr_levels.png` – static chart (S/R + VWAP + bands)
- `*_sr_interactive.html` – interactive chart
- `*_levels.json` – levels, scores, ATR, zones
- `*_alerts.txt` – multi-TF alerts
- `*_vp_divergence.txt` – VP divergence (if any)
- `*_order_flow.txt` – order-flow proxies (if any)

### Streamlit dashboard

```bash
streamlit run src/dashboard.py
```

Open the URL shown (usually `http://localhost:8501`).

- **Sidebar:** tickers (comma-separated), date, methods, ATR mult, alert proximity  
- **Each ticker tab:** KPIs, VWAP-band zone, OF imbalance summary, alerts, VP divergence, order-flow signals, chart, levels table, back-test  

---

## CLI flags (summary)

| Flag | Default | Meaning |
|------|---------|---------|
| `--tickers` | CRWV IREN NBIS APLD | Symbols |
| `--start` / `--end` | 2025-01-01 / today | Date range |
| `--methods` | swing,fib,kmeans,pivot | Detectors |
| `--atr-mult` | 0.5 | ATR zone half-width multiplier |
| `--alert-atr` | 1.0 | Proximity alert threshold (ATR units) |
| `--save` | off | Write plots, JSON, alert files |
| `--interactive` | off | Also write Plotly HTML |
| `--no-backtest` | – | Skip reaction stats |
| `--no-weekly` | – | Skip weekly + confluence |
| `--no-vp` | – | Skip volume profile |
| `--no-alerts` | – | Skip alerts |
| `--no-show` | – | Do not open charts |

```bash
python -m src.main --help
```

---

## Project layout

```
stock_sr_analyzer/
├── README.md                 # this file
├── GUIDE.md                  # full interpretation & workflow guide
├── requirements.txt
├── src/
│   ├── main.py               # CLI entry
│   ├── dashboard.py          # Streamlit UI
│   ├── data_fetcher.py       # yfinance + cache
│   ├── detectors.py          # S/R algorithms, weekly, confluence
│   ├── volume_profile.py     # VP, VWAP, VWAP bands, VP divergence
│   ├── order_flow.py         # delta/CVD, absorption, imbalances
│   ├── atr_utils.py          # ATR + zones
│   ├── alerts.py             # multi-TF alerts
│   ├── backtester.py         # reaction stats + Score
│   ├── visualizer.py         # matplotlib + Plotly
│   └── footprint_notes.py    # why footprints need tick data
├── data/                     # cached OHLCV CSVs
└── plots/                    # generated charts & text exports
```

---

## Where to look at signals

| What | Best place |
|------|------------|
| Everything at once | **Streamlit** dashboard |
| Batch / scripting | **CLI** terminal output |
| Archive / journal | `plots/*` JSON, TXT, HTML, PNG |
| Deep interpretation | **GUIDE.md** |

---

## Documentation map

| File | Contents |
|------|----------|
| **README.md** | Setup, features, CLI, layout |
| **GUIDE.md** | Metrics, Score, alerts, VP divergence, order flow, VWAP bands, trigger examples, daily workflow |
| **src/footprint_notes.py** | Data contract for real footprint charts |

---

## Notes

- Support/resistance are **zones** (prefer ATR width over fixed %).  
- Highest-conviction areas: **confluence + Score ≥ 60–70 + price in/near ATR zone**, filtered by VP/order-flow divergence.  
- Order-flow modules are **OHLCV proxies**, not true bid/ask footprint.  
- Not financial advice.

MIT License.
