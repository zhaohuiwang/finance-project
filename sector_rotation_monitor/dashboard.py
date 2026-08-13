"""
Interactive Streamlit dashboard for Sector + Industry Rotation Monitor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config, get_all_tickers, get_equity_meta
from src.data_fetcher import DataFetcher
from src.analyzer import SectorAnalyzer
from src.support_resistance import SupportResistanceAnalyzer

st.set_page_config(
    page_title="Sector Rotation Monitor",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

QUADRANT_COLORS = {
    "Leading": "#2ecc71",
    "Weakening": "#f1c40f",
    "Lagging": "#e74c3c",
    "Improving": "#3498db",
}


@st.cache_data(ttl=3600, show_spinner="Fetching equity data…")
def load_equity(force: bool = False):
    cfg = load_config()
    tickers = get_all_tickers(cfg)
    resolved = cfg["_resolved"]
    fetcher = DataFetcher(
        tickers=tickers,
        cache_dir=resolved["data_dir"],
        history_period=cfg.get("data", {}).get("history_period", "2y"),
        cache_ttl_hours=cfg.get("data", {}).get("cache_ttl_hours", 6),
    )
    prices = fetcher.fetch(force_refresh=force)
    # Serialize OHLC for cache: dict of records
    ohlc_ser = {}
    for t, df in fetcher.get_ohlc_dict().items():
        ohlc_ser[t] = df.reset_index().to_dict(orient="list")
    return cfg, prices, ohlc_ser


@st.cache_data(ttl=86400, show_spinner="Fetching FRED macro…")
def load_macro(force: bool = False):
    cfg = load_config()
    fred_cfg = cfg.get("fred", {})
    if not fred_cfg.get("enabled", True):
        return None
    try:
        from src.macro import MacroOverlay
        macro = MacroOverlay(
            series_config=fred_cfg.get("series", {}),
            cache_dir=cfg["_resolved"]["data_dir"],
            lookback_months=fred_cfg.get("lookback_months", 36),
        )
        macro.fetch(force_refresh=force)
        result = macro.classify_regime()
        result["preferred"] = macro.preferred_sectors(
            result["phase"], cfg.get("cycle_sector_preferences", {})
        )
        return result
    except Exception as e:
        st.sidebar.warning(f"Macro unavailable: {e}")
        return None


def main():
    st.title("🔄 Sector + Industry Rotation Monitor")
    st.caption("Multi-horizon relative strength, RRG, industry drill-down, FRED macro overlay")

    with st.sidebar:
        st.header("Controls")
        force = st.button("🔄 Force data refresh")
        view = st.radio("Universe", ["Sectors", "Industries", "All"], index=0)
        primary_period = st.selectbox(
            "Primary ranking period",
            options=["1W", "1M", "3M", "6M", "YTD", "1Y"],
            index=2,
        )
        st.markdown("---")
        st.markdown(
            "Equity: Yahoo Finance  \n"
            "Macro: FRED (set `FRED_API_KEY` env var)"
        )

    group_map = {"Sectors": "sector", "Industries": "industry", "All": None}
    group = group_map[view]

    try:
        cfg, prices, ohlc_ser = load_equity(force=force)
        # Rebuild OHLC frames from cached serializable dict
        ohlc = {}
        for t, rec in ohlc_ser.items():
            df = pd.DataFrame(rec)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date")
            elif "index" in df.columns:
                df["index"] = pd.to_datetime(df["index"])
                df = df.set_index("index")
            ohlc[t] = df
    except Exception as e:
        st.error(f"Failed to load equity data: {e}")
        st.stop()

    meta = get_equity_meta(cfg)
    analyzer = SectorAnalyzer(
        prices=prices,
        benchmark=cfg.get("benchmark", "SPY"),
        sector_meta=meta,
        rrg_params=cfg.get("rrg", {}),
    )
    periods = cfg.get("periods", {})
    summary = analyzer.summary_stats(group="sector")
    ranks = analyzer.rank_sectors(periods, by="relative", primary_period=primary_period, group=group)
    rrg = analyzer.rrg_snapshot(group=group)
    abs_perf = analyzer.performance_table(periods)
    rel_perf = analyzer.relative_performance(periods)

    macro = load_macro(force=force)

    # KPIs
    regime = summary.get("regime", {})
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("As of", summary.get("as_of", "—"))
    c2.metric("Price regime", regime.get("regime", "—"))
    c3.metric(
        "Risk-On spread",
        f"{regime.get('risk_on_spread', 0):+.2f}%" if regime.get("risk_on_spread") is not None else "—",
    )
    c4.metric("Macro phase", macro["phase"] if macro else "—")
    c5.metric("Leading (sectors)", len(summary.get("leading", [])))

    if macro:
        with st.expander("FRED macro signals & preferred sectors", expanded=False):
            st.write(f"**Score:** {macro.get('score')}")
            for s in macro.get("signals", []):
                st.write(f"• {s}")
            prefs = macro.get("preferred", {})
            st.write(f"**Favored:** {', '.join(prefs.get('favored', [])) or '—'}")
            st.write(f"**Avoided:** {', '.join(prefs.get('avoided', [])) or '—'}")
            if "snapshot" in macro and macro["snapshot"] is not None:
                st.dataframe(macro["snapshot"], width='stretch')

    # Support / Resistance
    try:
        sr_tickers = [c for c in prices.columns if c != cfg.get("benchmark", "SPY")]
        ohlc_sr = {t: ohlc[t] for t in sr_tickers if t in ohlc}
        sr = SupportResistanceAnalyzer(
            prices=prices[sr_tickers],
            ohlc=ohlc_sr,
            meta=meta,
        )
        sr_df = sr.summary(group=group)
    except Exception as e:
        sr_df = None
        st.sidebar.warning(f"S/R unavailable: {e}")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Rankings & Heatmaps",
        "🎯 RRG",
        "📈 Relative Paths",
        "🛡️ Support / Resistance",
        "📋 Tables",
    ])

    with tab1:
        st.subheader(f"Composite Rankings — {view}")
        show_cols = [c for c in ["Name", "Style", "Group", "Parent", "1M", "3M", "6M", "YTD", "1Y", "Composite_Rank", "Overall_Rank"] if c in ranks.columns]
        st.dataframe(
            ranks[show_cols].style.format(
                {c: "{:+.2f}" for c in ["1M", "3M", "6M", "YTD", "1Y"] if c in ranks.columns},
                na_rep="—",
            ),
            width='stretch',
        )

        tickers_view = analyzer.tickers_by_group(group) if group else analyzer.sector_tickers
        rel_view = rel_perf.loc[rel_perf.index.intersection(tickers_view)]
        abs_view = abs_perf.loc[abs_perf.index.intersection(tickers_view + [cfg.get("benchmark", "SPY")])]

        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.imshow(
                abs_view.drop(index=cfg.get("benchmark", "SPY"), errors="ignore"),
                text_auto=".1f", aspect="auto",
                color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                title="Absolute Returns (%)",
            )
            st.plotly_chart(fig, width='stretch')
        with col_b:
            fig2 = px.imshow(
                rel_view, text_auto=".1f", aspect="auto",
                color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                title="Excess vs SPY (%)",
            )
            st.plotly_chart(fig2, width='stretch')

    with tab2:
        st.subheader(f"RRG — {view}")
        fig_rrg = go.Figure()
        for q, color in QUADRANT_COLORS.items():
            sub = rrg[rrg["Quadrant"] == q]
            if sub.empty:
                continue
            labels = sub["Name"] if "Name" in sub.columns else sub.index
            fig_rrg.add_trace(go.Scatter(
                x=sub["RS_Ratio"], y=sub["RS_Momentum"],
                mode="markers+text", text=labels, textposition="top center",
                marker=dict(size=16, color=color, line=dict(width=1, color="black")),
                name=q,
            ))
        fig_rrg.add_vline(x=100, line_dash="dash", line_color="gray")
        fig_rrg.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_rrg.update_layout(
            title="Relative Rotation Graph",
            xaxis_title="RS-Ratio", yaxis_title="RS-Momentum",
            height=650, legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_rrg, width='stretch')
        st.dataframe(rrg, width='stretch')

    with tab3:
        st.subheader("Cumulative Relative Strength (sectors)")
        lookback = st.slider("Lookback (trading days)", 21, 252, 126, 21)
        bench = cfg.get("benchmark", "SPY")
        sector_cols = analyzer.tickers_by_group("sector")
        subset = prices.iloc[-lookback:]
        ratio = subset[sector_cols].div(subset[bench], axis=0)
        rebased = ratio / ratio.iloc[0] * 100.0
        fig_cum = go.Figure()
        for col in rebased.columns:
            fig_cum.add_trace(go.Scatter(x=rebased.index, y=rebased[col], mode="lines", name=col))
        fig_cum.add_hline(y=100, line_dash="dash", line_color="black")
        fig_cum.update_layout(
            title=f"Relative Strength vs {bench}",
            yaxis_title="RS (start = 100)", height=550,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_cum, width='stretch')

    
    with tab4:
        st.subheader(f"Support / Resistance — {view}")
        if sr_df is None or sr_df.empty:
            st.info("No S/R data available.")
        else:
            # Position counts
            if "Position" in sr_df.columns:
                counts = sr_df["Position"].value_counts()
                ccols = st.columns(min(len(counts), 6))
                for i, (pos, cnt) in enumerate(counts.items()):
                    ccols[i % len(ccols)].metric(str(pos), int(cnt))

            show = [c for c in [
                "Name", "Price", "Position",
                "Nearest_Support", "Dist_Support_%",
                "Nearest_Resistance", "Dist_Resistance_%",
                "SMA_20", "SMA_50", "SMA_200",
                "Above_All_MA", "Golden_Stack", "Death_Stack",
                "Pivot", "S1", "R1",
            ] if c in sr_df.columns]
            st.dataframe(
                sr_df[show].style.format({
                    **{c: "{:.2f}" for c in ["Price", "SMA_20", "SMA_50", "SMA_200", "Pivot", "S1", "R1"] if c in show},
                    **{c: "{:.2f}" for c in ["Dist_Support_%", "Dist_Resistance_%"] if c in show},
                }, na_rep="—"),
                width='stretch',
            )
            st.caption(
                "Position flags: At/Near Support or Resistance (within 0.5–1%), "
                "Breakout (above R1), Breakdown (below S1), Trend_Support (golden stack + above MAs)."
            )

    with tab5:
        st.subheader("Absolute Returns")

        st.dataframe(abs_perf.style.format("{:.2f}"), width='stretch')
        st.subheader("Relative Returns")
        st.dataframe(rel_perf.style.format("{:.2f}"), width='stretch')


    st.markdown("---")
    st.caption("v1.1 • Yahoo Finance + FRED • Research only — not investment advice.")


if __name__ == "__main__":
    main()
