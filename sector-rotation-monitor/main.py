#!/usr/bin/env python3
"""
Sector Rotation Monitor
=======================

Professional toolkit for monitoring equity sector + industry rotation
with optional FRED macro overlay.

Usage
-----
  python main.py
  python main.py --refresh
  python main.py --no-macro
  python main.py --dashboard
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config_loader import (
    load_config,
    get_all_tickers,
    get_equity_meta,
)
from src.data_fetcher import DataFetcher
from src.analyzer import SectorAnalyzer
from src.visualizer import SectorVisualizer
from src.reporter import ReportGenerator
from src.support_resistance import SupportResistanceAnalyzer


def setup_logging(verbose: bool = True) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def run_analysis(
    force_refresh: bool = False,
    quiet: bool = False,
    enable_macro: bool = True,
) -> None:
    setup_logging(verbose=not quiet)
    logger = logging.getLogger("main")

    cfg = load_config()
    tickers = get_all_tickers(cfg)
    meta = get_equity_meta(cfg)
    periods = cfg.get("periods", {})
    resolved = cfg["_resolved"]

    logger.info("Tickers (%d): %s", len(tickers), ", ".join(tickers))
    logger.info("Output directory: %s", resolved["output_dir"])

    # ----- Equity data -----
    fetcher = DataFetcher(
        tickers=tickers,
        cache_dir=resolved["data_dir"],
        history_period=cfg.get("data", {}).get("history_period", "2y"),
        cache_ttl_hours=cfg.get("data", {}).get("cache_ttl_hours", 6),
    )
    prices = fetcher.fetch(force_refresh=force_refresh)

    analyzer = SectorAnalyzer(
        prices=prices,
        benchmark=cfg.get("benchmark", "SPY"),
        sector_meta=meta,
        rrg_params=cfg.get("rrg", {}),
    )

    abs_perf = analyzer.performance_table(periods)
    rel_perf = analyzer.relative_performance(periods)

    ranks_sector = analyzer.rank_sectors(periods, by="relative", primary_period="3M", group="sector")
    ranks_industry = analyzer.rank_sectors(periods, by="relative", primary_period="3M", group="industry")

    rrg_sector = analyzer.rrg_snapshot(group="sector")
    rrg_industry = analyzer.rrg_snapshot(group="industry")
    summary = analyzer.summary_stats(group="sector")

    # ----- FRED macro overlay -----
    macro_result = None
    fred_cfg = cfg.get("fred", {})
    if enable_macro and fred_cfg.get("enabled", True):
        try:
            from src.macro import MacroOverlay

            macro = MacroOverlay(
                series_config=fred_cfg.get("series", {}),
                cache_dir=resolved["data_dir"],
                lookback_months=fred_cfg.get("lookback_months", 36),
            )
            macro.fetch(force_refresh=force_refresh)
            macro_result = macro.classify_regime()
            prefs = macro.preferred_sectors(
                macro_result["phase"],
                cfg.get("cycle_sector_preferences", {}),
            )
            macro_result["preferred"] = prefs
            summary["macro_phase"] = macro_result["phase"]
            summary["macro_score"] = macro_result["score"]
            summary["macro_signals"] = macro_result["signals"]
            summary["macro_preferred"] = prefs
            logger.info("Macro phase: %s (score=%s)", macro_result["phase"], macro_result["score"])
        except Exception as exc:
            logger.warning("Macro overlay skipped: %s", exc)
            summary["macro_phase"] = None
    else:
        summary["macro_phase"] = None

    # ----- Support / Resistance -----
    sr_summary = None
    sr_sector = None
    sr_industry = None
    try:
        # Exclude benchmark from S/R; pass true OHLC for pivot accuracy
        sr_tickers = [c for c in prices.columns if c != cfg.get("benchmark", "SPY")]
        ohlc_all = fetcher.get_ohlc_dict()
        ohlc_sr = {t: ohlc_all[t] for t in sr_tickers if t in ohlc_all}
        sr = SupportResistanceAnalyzer(
            prices=prices[sr_tickers],
            ohlc=ohlc_sr,
            meta=meta,
            ma_windows=[20, 50, 200],
            at_tolerance=0.005,
        )
        sr_summary = sr.summary(group=None)
        sr_sector = sr.summary(group="sector")
        sr_industry = sr.summary(group="industry")
        counts = sr.position_counts(group="sector")
        summary["sr_position_counts"] = counts
        logger.info("S/R positions (sectors): %s", counts)
    except Exception as exc:
        logger.warning("Support/Resistance module skipped: %s", exc)

    # ----- Visuals -----

    viz = SectorVisualizer(resolved["output_dir"])
    images = {}

    sector_tickers = analyzer.tickers_by_group("sector")
    abs_sec = abs_perf.loc[[t for t in abs_perf.index if t in sector_tickers or t == cfg.get("benchmark")]]
    rel_sec = rel_perf.loc[rel_perf.index.intersection(sector_tickers)]

    images["Sector Absolute Returns"] = viz.performance_heatmap(
        abs_sec.drop(index=cfg.get("benchmark", "SPY"), errors="ignore"),
        title="Absolute Sector Returns (%)",
        filename="performance_heatmap.png",
    )
    images["Sector Relative Strength"] = viz.relative_heatmap(
        rel_sec,
        title="Sector Excess Return vs SPY (%)",
        filename="relative_heatmap.png",
    )
    rrg_plot = rrg_sector.rename(columns={"Name": "Sector"}) if "Name" in rrg_sector.columns else rrg_sector
    images["Sector RRG"] = viz.rrg_scatter(
        rrg_plot,
        title="Sector Relative Rotation Graph",
        filename="rrg_scatter.png",
    )

    if not ranks_industry.empty:
        ind_tickers = analyzer.tickers_by_group("industry")
        rel_ind = rel_perf.loc[rel_perf.index.intersection(ind_tickers)]
        images["Industry Relative Strength"] = viz.relative_heatmap(
            rel_ind,
            title="Industry Excess Return vs SPY (%)",
            filename="industry_relative_heatmap.png",
        )
        rrg_ind_plot = rrg_industry.rename(columns={"Name": "Sector"}) if "Name" in rrg_industry.columns else rrg_industry
        images["Industry RRG"] = viz.rrg_scatter(
            rrg_ind_plot,
            title="Industry Relative Rotation Graph",
            filename="industry_rrg_scatter.png",
        )

    images["Cumulative Relative Strength"] = viz.cumulative_relative_chart(
        prices[[c for c in prices.columns if c in sector_tickers or c == cfg.get("benchmark")]],
        benchmark=cfg.get("benchmark", "SPY"),
        lookback_days=126,
        filename="cumulative_relative.png",
    )

    if "3M" in ranks_sector.columns:
        plot_df = ranks_sector.copy()
        if "Name" in plot_df.columns and "Sector" not in plot_df.columns:
            plot_df = plot_df.rename(columns={"Name": "Sector"})
        images["3M Sector Ranking"] = viz.ranking_bar(
            plot_df,
            value_col="3M",
            title="3-Month Sector Excess Return vs SPY",
            filename="ranking_3m.png",
        )

    # ----- Reports -----
    reporter = ReportGenerator(resolved["output_dir"])
    if not quiet:
        reporter.print_summary(summary, ranks_sector, rrg_sector)
        if macro_result:
            reporter.print_macro(macro_result)
        if not ranks_industry.empty:
            reporter.print_industry_ranks(ranks_industry)
        if sr_sector is not None and not sr_sector.empty:
            reporter.print_sr_summary(sr_sector, title="Sector Support / Resistance")
        if sr_industry is not None and not sr_industry.empty:
            reporter.print_sr_summary(sr_industry, title="Industry Support / Resistance")

    if cfg.get("output", {}).get("generate_csv", True):
        reporter.export_csv(ranks_sector, rrg_sector, abs_perf, rel_perf, prefix=None)
        out = Path(resolved["output_dir"])
        if not ranks_industry.empty:
            ranks_industry.to_csv(out / "industry_ranks.csv")
            rrg_industry.to_csv(out / "industry_rrg.csv")
        if macro_result and "snapshot" in macro_result:
            macro_result["snapshot"].to_csv(out / "macro_snapshot.csv")
        if sr_summary is not None and not sr_summary.empty:
            sr_summary.to_csv(out / "support_resistance.csv")
        if sr_sector is not None and not sr_sector.empty:
            sr_sector.to_csv(out / "sr_sectors.csv")
        if sr_industry is not None and not sr_industry.empty:
            sr_industry.to_csv(out / "sr_industries.csv")

    if cfg.get("output", {}).get("generate_html", True):
        reporter.export_html_report(
            summary,
            ranks_sector,
            rrg_sector,
            abs_sec,
            rel_sec,
            images,
            ranks_industry=ranks_industry if not ranks_industry.empty else None,
            macro_result=macro_result,
            sr_sector=sr_sector,
            sr_industry=sr_industry,
        )

    logger.info("Analysis complete. Artifacts → %s", resolved["output_dir"])


def launch_dashboard() -> None:
    import subprocess
    dashboard_path = ROOT / "dashboard.py"
    if not dashboard_path.exists():
        print("dashboard.py not found.")
        sys.exit(1)
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(dashboard_path), "--server.headless", "true"],
        check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sector + Industry Rotation Monitor with FRED macro overlay",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--refresh", action="store_true", help="Force fresh market + FRED data")
    parser.add_argument("--quiet", action="store_true", help="Suppress console tables")
    parser.add_argument("--no-macro", action="store_true", help="Skip FRED macro overlay")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit dashboard")
    args = parser.parse_args()

    if args.dashboard:
        launch_dashboard()
    else:
        run_analysis(
            force_refresh=args.refresh,
            quiet=args.quiet,
            enable_macro=not args.no_macro,
        )


if __name__ == "__main__":
    main()
