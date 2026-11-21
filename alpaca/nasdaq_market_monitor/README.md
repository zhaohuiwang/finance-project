# NASDAQ Live Market Monitor

Streamlit market monitor.

## Streaming behaviour
The Alpaca IEX WebSocket connection is started once and **stays open continuously** for the lifetime of the process (it is a long-lived daemon thread).

However, **new one-minute bars only arrive while the US equity market is open** (regular trading hours, roughly 09:30–16:00 US/Eastern, Monday–Friday). Outside those hours the connection is idle – no bars are published by Alpaca – so the dashboard simply continues to display the last known data. There is no
automatic disconnect / reconnect based on the clock; the stream is always ready for the next trading session.

### Adaptive idle mode
When no new bar has arrived for `idle_after_seconds` (default 120 s) a clear **Idle mode** banner appears at the top of the dashboard.  The last known data (summary table, signals, charts) remains fully visible.  As soon as the next bar arrives the banner disappears and live updates continue.

Configure it in `config.toml`:

## Quick start

```bash
# 1. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create a .env file with your Alpaca credentials
echo "ALPACA_API_KEY=your_key_here" > .env
echo "ALPACA_API_SECRET_KEY=your_secret_here" >> .env

# 4. Run the dashboard, inside alpaca/
streamlit run nasdaq_market_monitor/tracker.py
```

Then open http://localhost:8501

If metrics are enabled (default), Prometheus scrapes are available at  
http://localhost:9100/metrics

## Project layout

```
.
├── tracker.py                 # Streamlit entry point
├── config.toml                # All tunables (symbols, periods, retention…)
├── requirements.txt
├── README.md
├── market_monitor/
│   ├── __init__.py
│   ├── config.py              # loads config.toml + env credentials
│   ├── status.py              # StatusManager (thread-safe metrics)
│   ├── database.py            # BarDatabase (SQLite repository)
│   ├── indicators.py          # IndicatorCalculator (SMA / EMA / VWAP)
│   ├── signals.py             # EquitySignal / VixSignal dataclasses + calculators
│   ├── stream.py              # MarketDataStream (Alpaca WebSocket + shutdown)
│   └── ui.py                  # Streamlit presentation layer
└── tests/
    ├── test_indicators.py
    ├── test_signals.py
    └── test_database.py
```

## Design notes

- The WebSocket + background threads are started once via `@st.cache_resource`.
- The live dashboard is a `@st.fragment` that refreshes every two seconds.
- ...

## Suggested improvements

1. Replace free-form signal dicts with `@dataclass`es.
2. Add unit tests for the pure calculators and `BarDatabase`.
3. Externalise symbols / periods / retention into a YAML/TOML config.
4. Add a clean shutdown path for the Alpaca stream.
5. Optional Prometheus metrics endpoint.
