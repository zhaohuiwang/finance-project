"""
Simple Streamlit dashboard for the Stock Support & Resistance Analyzer.

Run with:
    streamlit run src/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# ensure package import works when launched via streamlit
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.data_fetcher import fetch_ohlcv
from src.detectors import (
    analyze_levels,
    detect_weekly_levels,
    find_confluence,
    enrich_with_volume_profile,
    filter_nearby,
)
from src.volume_profile import compute_vwap, compute_volume_profile, detect_vp_divergence, compute_vwap_bands, vwap_band_position
from src.order_flow import analyze_order_flow, compute_order_flow, imbalance_summary
from src.backtester import backtest_levels
from src.atr_utils import compute_atr, make_atr_zones
from src.alerts import generate_alerts


st.set_page_config(
    page_title="S/R Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 Stock Support & Resistance Analyzer")
st.caption("Oscillating / range-bound stocks – multi-timeframe levels, ATR zones, alerts")


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")
    tickers_input = st.text_input("Tickers (comma-separated)", value="IREN,CRWV,NBIS,APLD")
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

    start = st.date_input("Start date", value=pd.Timestamp("2025-01-01"))
    methods = st.multiselect(
        "Detection methods",
        ["swing", "kmeans", "fib", "pivot"],
        default=["swing", "kmeans", "fib", "pivot"],
    )
    do_weekly = st.checkbox("Weekly + Confluence", value=True)
    do_vp = st.checkbox("Volume Profile", value=True)
    do_backtest = st.checkbox("Reaction Back-test", value=True)
    atr_mult = st.slider("ATR zone multiplier", 0.2, 1.5, 0.5, 0.1)
    proximity_atr = st.slider("Alert proximity (ATR)", 0.3, 2.5, 1.0, 0.1)
    max_dist = st.slider("Max distance % from price", 10, 50, 35)

    run_btn = st.button("Run Analysis", type="primary")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
if run_btn and tickers:
    tabs = st.tabs(tickers)

    for tab, ticker in zip(tabs, tickers):
        with tab:
            with st.spinner(f"Fetching & analyzing {ticker}…"):
                try:
                    df = fetch_ohlcv(ticker, start=str(start), use_cache=True)
                except Exception as e:
                    st.error(f"Failed to fetch {ticker}: {e}")
                    continue

                if df.empty or len(df) < 30:
                    st.warning("Insufficient data")
                    continue

                # Daily levels
                daily = analyze_levels(df, methods=methods or ["swing", "kmeans"])
                weekly = detect_weekly_levels(df, methods=["swing", "kmeans", "fib"]) if do_weekly else []
                conf = find_confluence(daily, weekly) if (daily and weekly) else []
                levels = daily + weekly + conf

                if do_vp:
                    levels = enrich_with_volume_profile(df, levels)

                current = float(df["Close"].iloc[-1])
                levels = filter_nearby(levels, current, max_distance_pct=max_dist)

                # ATR + zones
                atr = compute_atr(df)
                last_atr = float(atr.iloc[-1])
                zones = make_atr_zones(levels, atr, multiplier=atr_mult)

                vwap = compute_vwap(df)

                # Back-test scores
                if do_backtest and levels:
                    stats = backtest_levels(df, levels[:18], tolerance_pct=1.0, horizon=12)
                    score_map = {round(s.level.price, 2): s.score for s in stats}
                    for L in levels:
                        L.score = score_map.get(round(L.price, 2), L.score)

                # Alerts
                alerts = generate_alerts(
                    ticker, df, levels,
                    proximity_atr=proximity_atr,
                    strong_score_threshold=60.0,
                )

            # ---- KPI row ----
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Last Close", f"{current:.2f}")
            c2.metric("ATR(14)", f"{last_atr:.2f}")
            c3.metric("VWAP", f"{float(vwap.iloc[-1]):.2f}")
            c4.metric("Levels kept", len(levels))
            c5.metric("Alerts", len(alerts))

            bands = compute_vwap_bands(df)
            pos = vwap_band_position(df, bands)
            try:
                ims = imbalance_summary(df, lookback=20)
            except Exception:
                ims = {}
            if pos:
                st.caption(
                    f"VWAP bands: zone=**{pos.get('zone')}** | "
                    f"VWAP={pos.get('vwap'):.2f} | dist={pos.get('dist_pct_vwap'):.2f}% | "
                    f"±1σ [{pos.get('lower_1')}, {pos.get('upper_1')}]"
                )
            if ims:
                st.caption(
                    f"Order-flow (20d): pressure=**{ims.get('pressure')}** | "
                    f"up={ims.get('up_vol_share', 0):.0%} dn={ims.get('dn_vol_share', 0):.0%} | "
                    f"net_delta={ims.get('net_delta', 0):.0f} | cvd_chg={ims.get('cvd_change', 0):.0f}"
                )


            # ---- Alerts ----
            if alerts:
                st.subheader("🚨 Multi-Timeframe Alerts")
                for a in alerts[:12]:
                    color = {"action": "🔴", "watch": "🟡", "info": "🔵"}.get(a.severity, "⚪")
                    st.markdown(f"{color} **{a.severity.upper()}** – {a.message}  \n"
                                f"`{a.level_price:.2f}`  |  {a.distance_atr:+.2f} ATR  |  score={a.score:.0f}  |  {a.timeframe}")
            else:
                st.info("No proximity alerts right now.")

            # VP Divergence
            try:
                vp_divs = detect_vp_divergence(df, lookback=min(30, len(df)//3))
                if vp_divs:
                    st.subheader("📉 Volume Profile Divergence")
                    for d in vp_divs:
                        icon = "🔴" if d.severity == "action" else "🟡"
                        st.markdown(f"{icon} **{d.kind}** – {d.message}")
            except Exception:
                pass

            # Order Flow
            try:
                of_signals = analyze_order_flow(df, lookback=min(30, len(df)//3))
                if of_signals:
                    st.subheader("📊 Order Flow Proxies")
                    for s in of_signals:
                        icon = "🔴" if s.severity == "action" else "🟡"
                        st.markdown(f"{icon} **{s.kind}** – {s.message}")
            except Exception:
                pass

            # ---- Interactive chart ----
            st.subheader("Chart")
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                vertical_spacing=0.03, row_heights=[0.72, 0.28],
            )
            fig.add_trace(
                go.Candlestick(
                    x=df.index, open=df["Open"], high=df["High"],
                    low=df["Low"], close=df["Close"], name="OHLC",
                    increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(x=df.index, y=vwap, name="VWAP", line=dict(color="orange", width=1.4)),
                row=1, col=1,
            )
            if not bands.empty and "upper_1" in bands.columns:
                fig.add_trace(go.Scatter(x=df.index, y=bands["upper_1"], name="VWAP+1σ",
                    line=dict(color="orange", width=1, dash="dash"), opacity=0.6), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=bands["lower_1"], name="VWAP-1σ",
                    line=dict(color="orange", width=1, dash="dash"), opacity=0.6), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=bands["upper_2"], name="VWAP+2σ",
                    line=dict(color="orange", width=1, dash="dot"), opacity=0.4), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=bands["lower_2"], name="VWAP-2σ",
                    line=dict(color="orange", width=1, dash="dot"), opacity=0.4), row=1, col=1)

            # ATR bands around close (visual reference)
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df["Close"] + atr,
                    line=dict(width=0), showlegend=False, hoverinfo="skip",
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df["Close"] - atr,
                    fill="tonexty", fillcolor="rgba(100,100,200,0.08)",
                    line=dict(width=0), name="±1 ATR",
                ),
                row=1, col=1,
            )

            colors = {"support": "#2ca02c", "resistance": "#d62728", "both": "#1f77b4"}
            for z in sorted(zones, key=lambda x: -x["strength"])[:12]:
                color = colors.get(z["kind"], "gray")
                fig.add_hrect(
                    y0=z["zone_low"], y1=z["zone_high"],
                    fillcolor=color, opacity=0.12, line_width=0, row=1, col=1,
                )
                fig.add_hline(
                    y=z["price"], line_color=color,
                    line_dash="solid" if z["timeframe"] in ("weekly", "confluence") else "dash",
                    line_width=1.5,
                    annotation_text=f"{z['price']:.1f}",
                    annotation_position="right",
                    row=1, col=1,
                )

            vol_colors = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(df["Open"], df["Close"])]
            fig.add_trace(
                go.Bar(x=df.index, y=df["Volume"], marker_color=vol_colors, opacity=0.55, name="Volume"),
                row=2, col=1,
            )
            fig.update_layout(
                xaxis_rangeslider_visible=False, height=700,
                template="plotly_white", margin=dict(l=40, r=40, t=40, b=30),
                legend=dict(orientation="h", y=1.02),
            )
            try:
                st.plotly_chart(fig, width="stretch")
            except TypeError:
                st.plotly_chart(fig, use_container_width=True)

            # ---- Levels table ----
            st.subheader("Levels & ATR Zones")
            rows = []
            for z in sorted(zones, key=lambda x: (-x["score"] if x["score"] else -x["strength"], -x["strength"])):
                rows.append(
                    {
                        "Price": round(z["price"], 2),
                        "Zone Low": round(z["zone_low"], 2),
                        "Zone High": round(z["zone_high"], 2),
                        "Width %": round(z["width_pct"], 2),
                        "Kind": z["kind"],
                        "TF": z["timeframe"],
                        "Strength": z["strength"],
                        "Score": float(z["score"]) if z["score"] else None,
                        "Method": z["method"][:40],
                    }
                )
            try:
                st.dataframe(pd.DataFrame(rows), width="stretch", height=360)
            except TypeError:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, height=360)

            # ---- Back-test summary ----
            if do_backtest and levels:
                st.subheader("Reaction Back-test (top levels)")
                stats = backtest_levels(df, levels[:15], tolerance_pct=1.0, horizon=12)
                bt_rows = [
                    {
                        "Price": round(s.level.price, 2),
                        "Kind": s.level.kind,
                        "Touches": s.n_touches,
                        "Bounces": s.n_bounces,
                        "Win %": round(s.win_rate * 100, 1),
                        "Avg Bounce %": round(s.avg_bounce_pct, 2),
                        "Score": s.score,
                    }
                    for s in stats
                ]
                try:
                    st.dataframe(pd.DataFrame(bt_rows), width="stretch")
                except TypeError:
                    st.dataframe(pd.DataFrame(bt_rows), use_container_width=True)

else:
    st.info("Select tickers and click **Run Analysis** in the sidebar.")
    st.markdown(
        """
        ### Features available in this dashboard
        - Multi-method S/R detection (swing, K-Means, Fibonacci, pivots)
        - Weekly levels + daily/weekly **confluence**
        - **Volume Profile** (POC / Value Area)
        - **ATR-normalized zones** (zone width = multiplier × ATR)
        - **Multi-timeframe alerts** (proximity + recent touch/break)
        - Reaction back-test with composite Score
        - Interactive Plotly chart with VWAP and ATR bands
        """
    )
