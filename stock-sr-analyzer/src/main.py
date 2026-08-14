#!/usr/bin/env python3
"""
CLI entry point for the enhanced Stock Support & Resistance Analyzer.

Features
--------
- Swing / K-Means / Fibonacci / Pivot detection
- Weekly higher-timeframe levels + confluence
- Volume Profile (POC, Value Area) + strength boost
- VWAP (cumulative + rolling)
- Historical reaction back-test with composite score
- Static + interactive (Plotly) charts

Example
-------
python -m src.main --tickers IREN NBIS APLD --start 2025-01-01 --save --interactive
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .data_fetcher import fetch_multiple
from .detectors import (
    analyze_levels,
    detect_weekly_levels,
    find_confluence,
    enrich_with_volume_profile,
    filter_nearby,
)
from .volume_profile import (
    compute_vwap, compute_volume_profile, detect_vp_divergence, print_vp_divergences,
    vwap_summary, compute_vwap_bands, vwap_band_position,
)
from .order_flow import analyze_order_flow, print_order_flow_signals, imbalance_summary
from .order_flow import analyze_order_flow, print_order_flow_signals, imbalance_summary
from .backtester import backtest_levels, print_backtest_report
from .visualizer import plot_levels, plot_interactive, print_levels_table, PLOTS_DIR
from .atr_utils import compute_atr, make_atr_zones
from .alerts import generate_alerts, print_alerts, save_alerts


def parse_args():
    p = argparse.ArgumentParser(
        description="Detect support & resistance levels for oscillating stocks (enhanced)"
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        default=["CRWV", "IREN", "NBIS", "APLD"],
        help="Ticker symbols",
    )
    p.add_argument("--start", default="2025-01-01", help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    p.add_argument(
        "--methods",
        default="swing,fib,kmeans,pivot",
        help="Comma-separated: swing,fib,kmeans,pivot",
    )
    p.add_argument("--tolerance", type=float, default=1.8, help="Cluster tolerance %%")
    p.add_argument("--min-strength", type=int, default=2, help="Min touches for a level")
    p.add_argument("--max-dist", type=float, default=35.0, help="Max distance %% from price to keep")
    p.add_argument("--save", action="store_true", help="Save plots, HTML and JSON")
    p.add_argument("--no-show", action="store_true", help="Do not display interactive/static plots")
    p.add_argument("--interactive", action="store_true", help="Also generate Plotly interactive HTML")
    p.add_argument("--backtest", action="store_true", default=True, help="Run level reaction back-test")
    p.add_argument("--no-backtest", action="store_true", help="Skip back-test")
    p.add_argument("--weekly", action="store_true", default=True, help="Include weekly levels")
    p.add_argument("--no-weekly", action="store_true", help="Skip weekly detection")
    p.add_argument("--vp", action="store_true", default=True, help="Include volume profile")
    p.add_argument("--no-vp", action="store_true", help="Skip volume profile")
    p.add_argument("--atr-mult", type=float, default=0.5, help="ATR zone half-width multiplier")
    p.add_argument("--alert-atr", type=float, default=1.0, help="Alert when price within N ATRs of level")
    p.add_argument("--alerts", action="store_true", default=True, help="Generate multi-TF alerts")
    p.add_argument("--no-alerts", action="store_true", help="Skip alerts")
    return p.parse_args()


def main():
    args = parse_args()
    methods = [m.strip().lower() for m in args.methods.split(",") if m.strip()]
    do_backtest = args.backtest and not args.no_backtest
    do_weekly = args.weekly and not args.no_weekly
    do_vp = args.vp and not args.no_vp

    print(f"Fetching data for {args.tickers} from {args.start} …")
    data = fetch_multiple(args.tickers, start=args.start, end=args.end)

    summary = {}

    for ticker, df in data.items():
        if df.empty or len(df) < 30:
            print(f"Skipping {ticker}: insufficient data")
            continue

        print(f"\n{'='*70}")
        print(f">>> Analyzing {ticker} ({len(df)} daily bars) …")
        print(f"{'='*70}")

        # --- Daily levels ---
        daily_levels = analyze_levels(
            df,
            methods=methods,
            tolerance_pct=args.tolerance,
            min_strength=args.min_strength,
            lookback=min(150, len(df) - 5),
        )

        # --- Weekly levels ---
        weekly_levels = []
        if do_weekly:
            weekly_levels = detect_weekly_levels(
                df,
                methods=["swing", "kmeans", "fib"],
                tolerance_pct=args.tolerance + 0.5,
                min_strength=2,
            )
            print(f"  Weekly levels found: {len(weekly_levels)}")

        # --- Confluence ---
        conf_levels = []
        if daily_levels and weekly_levels:
            conf_levels = find_confluence(daily_levels, weekly_levels, tolerance_pct=1.8)
            print(f"  Confluence levels: {len(conf_levels)}")

        # Combine
        all_levels = daily_levels + weekly_levels + conf_levels

        # --- Volume Profile enrichment ---
        if do_vp:
            all_levels = enrich_with_volume_profile(df, all_levels, bins=45)
            try:
                vp = compute_volume_profile(df, bins=45)
                print(f"  Volume Profile → POC={vp.poc:.2f}  VAL={vp.val:.2f}  VAH={vp.vah:.2f}")
            except Exception:
                pass

        # --- VWAP ---
        vwap = compute_vwap(df)  # cumulative from start of data

        current = float(df["Close"].iloc[-1])
        all_levels = filter_nearby(all_levels, current, max_distance_pct=args.max_dist)

        # de-dup again after enrichment
        all_levels.sort(key=lambda L: L.price)
        final = []
        for lvl in all_levels:
            if not final:
                final.append(lvl)
                continue
            last = final[-1]
            if abs(lvl.price - last.price) / last.price * 100 < 0.7:
                if lvl.strength > last.strength:
                    final[-1] = lvl
                else:
                    last.strength = max(last.strength, lvl.strength)
            else:
                final.append(lvl)
        final.sort(key=lambda L: (-L.strength, L.price))

        print_levels_table(final, current)

        # --- Back-test reactions ---
        if do_backtest and final:
            print("Running historical reaction back-test …")
            stats = backtest_levels(df, final[:20], tolerance_pct=1.0, horizon=12)
            # attach scores back to levels
            score_map = {round(s.level.price, 2): s.score for s in stats}
            for L in final:
                key = round(L.price, 2)
                if key in score_map:
                    L.score = score_map[key]
            print_backtest_report(stats, top_n=12)

        # --- ATR zones ---
        atr = compute_atr(df)
        last_atr = float(atr.iloc[-1]) if not atr.empty else 1.0
        zones = make_atr_zones(final, atr, multiplier=args.atr_mult)
        print(f"  ATR(14) = {last_atr:.2f}  |  zone half-width ≈ {args.atr_mult * last_atr:.2f}")
        vs = vwap_summary(df)
        if vs:
            print(f"  VWAP cum={vs.get('vwap_cumulative'):.2f}  roll20={vs.get('vwap_roll_20')}  "
                  f"AVWAP(low)={vs.get('avwap_from_swing_low')}  AVWAP(high)={vs.get('avwap_from_swing_high')}")

        bands = compute_vwap_bands(df, window=None, std_mults=(1.0, 2.0))
        pos = vwap_band_position(df, bands)
        if pos:
            print(f"  VWAP bands zone={pos.get('zone')}  "
                  f"upper1={pos.get('upper_1')}  lower1={pos.get('lower_1')}  "
                  f"dist_vwap={pos.get('dist_pct_vwap'):.2f}%")
        try:
            ims = imbalance_summary(df, lookback=20)
            print(f"  OF imbalance (20d): pressure={ims['pressure']}  "
                  f"up_share={ims['up_vol_share']:.1%}  dn_share={ims['dn_vol_share']:.1%}  "
                  f"net_delta={ims['net_delta']:.0f}  cvd_chg={ims['cvd_change']:.0f}")
        except Exception as e:
            print(f"  [imbalance summary skipped] {e}")


        # --- Multi-timeframe alerts ---
        do_alerts = args.alerts and not args.no_alerts
        if do_alerts:
            alerts = generate_alerts(
                ticker, df, final,
                proximity_atr=args.alert_atr,
                strong_score_threshold=60.0,
            )
            print_alerts(alerts)
            if args.save and alerts:
                save_alerts(alerts, PLOTS_DIR / f"{ticker}_alerts.txt")

        # --- Volume Profile Divergence ---
        try:
            vp_divs = detect_vp_divergence(df, lookback=min(30, len(df)//3))
            print_vp_divergences(vp_divs)
            if args.save and vp_divs:
                div_path = PLOTS_DIR / f"{ticker}_vp_divergence.txt"
                div_path.write_text("\n".join(f"[{d.severity}] {d.kind}: {d.message}" for d in vp_divs) + "\n")
                print(f"VP divergence saved → {div_path}")
        except Exception as e:
            print(f"  [vp divergence skipped] {e}")

        # --- Order Flow proxies ---
        try:
            of_signals = analyze_order_flow(df, lookback=min(30, len(df)//3))
            print_order_flow_signals(of_signals)
            if args.save and of_signals:
                of_path = PLOTS_DIR / f"{ticker}_order_flow.txt"
                of_path.write_text("\n".join(f"[{s.severity}] {s.kind}: {s.message}" for s in of_signals) + "\n")
                print(f"Order flow saved → {of_path}")
        except Exception as e:
            print(f"  [order flow skipped] {e}")

        # --- Save levels JSON ---
        if args.save:
            out = {
                "ticker": ticker,
                "last_close": current,
                "as_of": str(df.index[-1].date()),
                "vwap": float(vwap.iloc[-1]) if not vwap.empty else None,
                "atr": last_atr,
                "atr_mult": args.atr_mult,
                "levels": [
                    {
                        "price": round(L.price, 4),
                        "kind": L.kind,
                        "strength": L.strength,
                        "score": L.score,
                        "method": L.method,
                        "timeframe": L.timeframe,
                    }
                    for L in final
                ],
                "zones": zones[:20],
            }
            json_path = PLOTS_DIR / f"{ticker}_levels.json"
            with open(json_path, "w") as f:
                json.dump(out, f, indent=2)
            print(f"Levels JSON → {json_path}")

        # --- Charts ---
        plot_levels(
            df,
            final,
            ticker=ticker,
            title=f"{ticker} S/R + VWAP (since {args.start})",
            save=args.save,
            show=not args.no_show,
            vwap=vwap,
            vwap_bands=bands,
        )

        if args.interactive or args.save:
            plot_interactive(
                df,
                final,
                ticker=ticker,
                title=f"{ticker} Interactive S/R",
                save=args.save or args.interactive,
                vwap=vwap,
            )

        # nearest meaningful levels
        supports = [L for L in final if L.kind in ("support", "both")]
        resistances = [L for L in final if L.kind in ("resistance", "both")]
        nearest_s = min(supports, key=lambda L: abs(L.price - current), default=None)
        nearest_r = min(resistances, key=lambda L: abs(L.price - current), default=None)

        summary[ticker] = {
            "last": current,
            "vwap": float(vwap.iloc[-1]) if not vwap.empty else None,
            "n_levels": len(final),
            "nearest_support": nearest_s.price if nearest_s else None,
            "nearest_resistance": nearest_r.price if nearest_r else None,
            "top_score": max((L.score for L in final), default=0),
        }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for t, s in summary.items():
        print(
            f"{t}: last={s['last']:.2f}  VWAP={(s['vwap'] or 0):.2f}  "
            f"nearest S={s['nearest_support']}  R={s['nearest_resistance']}  "
            f"levels={s['n_levels']}  top_score={s['top_score']:.1f}"
        )
    print("\nDone. Check the plots/ folder for charts and JSON.")


if __name__ == "__main__":
    main()
