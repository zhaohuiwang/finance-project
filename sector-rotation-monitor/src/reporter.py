"""Report generation: console (rich), CSV, and HTML summary."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()


class ReportGenerator:
    """Produce human-readable and machine-readable reports."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def print_summary(self, summary: Dict[str, Any], ranks: pd.DataFrame, rrg: pd.DataFrame) -> None:
        """Rich console dashboard for broad sectors."""
        as_of = summary.get("as_of", "N/A")
        regime = summary.get("regime", {})
        regime_label = regime.get("regime", "Unknown")
        spread = regime.get("risk_on_spread")
        macro_phase = summary.get("macro_phase")

        header = Text.from_markup(
            f"[bold cyan]Sector Rotation Monitor[/]  •  As of [bold]{as_of}[/]  •  "
            f"Price Regime: [bold]{regime_label}[/]"
        )
        if spread is not None:
            header.append(f"  (Cyc−Def: {spread:+.2f}%)", style="dim")
        if macro_phase:
            header.append(f"  •  Macro: [bold yellow]{macro_phase}[/]")

        console.print(Panel(header, expand=False))

        q_table = Table(title="Sector RRG Quadrants", show_header=True, header_style="bold magenta")
        q_table.add_column("Quadrant", style="bold")
        q_table.add_column("Sectors")
        for q in ["Leading", "Improving", "Weakening", "Lagging"]:
            tickers = summary.get(q.lower(), [])
            q_table.add_row(q, ", ".join(tickers) if tickers else "—")
        console.print(q_table)
        console.print()

        rank_table = Table(title="Sector Composite Ranking", show_header=True)
        rank_table.add_column("#", justify="right", style="cyan")
        rank_table.add_column("Ticker", style="bold")
        rank_table.add_column("Name")
        rank_table.add_column("Style")
        rank_table.add_column("1M Excess", justify="right")
        rank_table.add_column("3M Excess", justify="right")
        rank_table.add_column("YTD Excess", justify="right")
        rank_table.add_column("Quadrant")

        rrg_q = rrg["Quadrant"].to_dict() if "Quadrant" in rrg.columns else {}
        name_col = "Name" if "Name" in ranks.columns else ("Sector" if "Sector" in ranks.columns else None)

        for i, (ticker, row) in enumerate(ranks.head(12).iterrows(), 1):
            name = row.get(name_col, ticker) if name_col else ticker
            style = str(row.get("Style", ""))[:22]
            m1 = row.get("1M", float("nan"))
            m3 = row.get("3M", float("nan"))
            ytd = row.get("YTD", float("nan"))
            quad = rrg_q.get(ticker, "")

            def fmt(v):
                if pd.isna(v):
                    return "—"
                color = "green" if v >= 0 else "red"
                return f"[{color}]{v:+.2f}%[/]"

            rank_table.add_row(
                str(i), ticker, str(name)[:20], style,
                fmt(m1), fmt(m3), fmt(ytd), quad,
            )
        console.print(rank_table)
        console.print()

    def print_macro(self, macro_result: Dict[str, Any]) -> None:
        """Print FRED regime summary."""
        phase = macro_result.get("phase", "Unknown")
        score = macro_result.get("score", 0)
        signals = macro_result.get("signals", [])
        prefs = macro_result.get("preferred", {})

        console.print(Panel(
            f"[bold]Macro Cycle Phase:[/] [yellow]{phase}[/]  (score={score})",
            title="FRED Macro Overlay",
            expand=False,
        ))
        if signals:
            for s in signals:
                console.print(f"  • {s}")
        fav = prefs.get("favored", [])
        avd = prefs.get("avoided", [])
        if fav or avd:
            console.print(f"  [green]Historically favored:[/] {', '.join(fav) or '—'}")
            console.print(f"  [red]Historically avoided:[/] {', '.join(avd) or '—'}")
        console.print()

        snap = macro_result.get("snapshot")
        if snap is not None and not snap.empty:
            t = Table(title="Macro Snapshot", show_header=True)
            t.add_column("Series")
            t.add_column("Name")
            t.add_column("Latest", justify="right")
            t.add_column("As Of")
            t.add_column("3M Chg", justify="right")
            t.add_column("12M Chg", justify="right")
            for sid, row in snap.iterrows():
                def fnum(v, places=2):
                    if pd.isna(v):
                        return "—"
                    return f"{v:.{places}f}"
                t.add_row(
                    sid,
                    str(row.get("Name", ""))[:28],
                    fnum(row.get("Latest")),
                    str(row.get("AsOf", "")),
                    fnum(row.get("Chg_3M")),
                    fnum(row.get("Chg_12M")),
                )
            console.print(t)
            console.print()

    def print_industry_ranks(self, ranks: pd.DataFrame) -> None:
        """Compact industry ranking table."""
        t = Table(title="Industry Composite Ranking", show_header=True)
        t.add_column("#", justify="right", style="cyan")
        t.add_column("Ticker", style="bold")
        t.add_column("Name")
        t.add_column("Parent")
        t.add_column("1M", justify="right")
        t.add_column("3M", justify="right")
        t.add_column("YTD", justify="right")

        def fmt(v):
            if pd.isna(v):
                return "—"
            color = "green" if v >= 0 else "red"
            return f"[{color}]{v:+.2f}%[/]"

        for i, (ticker, row) in enumerate(ranks.head(15).iterrows(), 1):
            t.add_row(
                str(i),
                ticker,
                str(row.get("Name", ticker))[:22],
                str(row.get("Parent", "")),
                fmt(row.get("1M")),
                fmt(row.get("3M")),
                fmt(row.get("YTD")),
            )
        console.print(t)
        console.print()


    def print_sr_summary(self, sr: pd.DataFrame, title: str = "Support / Resistance") -> None:
        """Compact S/R status table."""
        t = Table(title=title, show_header=True)
        t.add_column("Ticker", style="bold")
        t.add_column("Name")
        t.add_column("Price", justify="right")
        t.add_column("Position", style="cyan")
        t.add_column("Near Support")
        t.add_column("Dist S %", justify="right")
        t.add_column("Near Resistance")
        t.add_column("Dist R %", justify="right")
        t.add_column("MAs", justify="center")

        for ticker, row in sr.iterrows():
            pos = str(row.get("Position", ""))
            if pos in ("At_Support", "Near_Support", "Trend_Support"):
                pos_fmt = f"[green]{pos}[/]"
            elif pos in ("At_Resistance", "Near_Resistance", "Trend_Resistance", "Breakdown"):
                pos_fmt = f"[red]{pos}[/]"
            elif pos == "Breakout":
                pos_fmt = f"[bold green]{pos}[/]"
            else:
                pos_fmt = pos

            def fnum(v, p=2):
                if pd.isna(v):
                    return "—"
                return f"{v:.{p}f}"

            ma_flags = []
            if row.get("Above_SMA20"):
                ma_flags.append("20")
            if row.get("Above_SMA50"):
                ma_flags.append("50")
            if row.get("Above_SMA200"):
                ma_flags.append("200")
            ma_str = ",".join(ma_flags) if ma_flags else "none"

            t.add_row(
                ticker,
                str(row.get("Name", ticker))[:18],
                fnum(row.get("Price")),
                pos_fmt,
                str(row.get("Nearest_Support", "—"))[:16],
                fnum(row.get("Dist_Support_%")),
                str(row.get("Nearest_Resistance", "—"))[:16],
                fnum(row.get("Dist_Resistance_%")),
                ma_str,
            )
        console.print(t)
        console.print()

    def export_csv(
        self,
        ranks: pd.DataFrame,
        rrg: pd.DataFrame,
        abs_perf: pd.DataFrame,
        rel_perf: pd.DataFrame,
        prefix: Optional[str] = None,
    ) -> List[Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        prefix = prefix or f"sector_rotation_{ts}"
        paths = []
        mapping = {
            f"{prefix}_ranks.csv": ranks,
            f"{prefix}_rrg.csv": rrg,
            f"{prefix}_absolute_returns.csv": abs_perf,
            f"{prefix}_relative_returns.csv": rel_perf,
        }
        for name, df in mapping.items():
            path = self.output_dir / name
            df.to_csv(path)
            paths.append(path)
            logger.info("CSV → %s", path)
        return paths

    def export_html_report(
        self,
        summary: Dict[str, Any],
        ranks: pd.DataFrame,
        rrg: pd.DataFrame,
        abs_perf: pd.DataFrame,
        rel_perf: pd.DataFrame,
        image_paths: Optional[Dict[str, Path]] = None,
        filename: Optional[str] = None,
        ranks_industry: Optional[pd.DataFrame] = None,
        macro_result: Optional[Dict[str, Any]] = None,
        sr_sector: Optional[pd.DataFrame] = None,
        sr_industry: Optional[pd.DataFrame] = None,
    ) -> Path:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        as_of = summary.get("as_of", "N/A")
        regime = summary.get("regime", {})
        filename = filename or f"sector_rotation_report_{datetime.now().strftime('%Y%m%d')}.html"
        path = self.output_dir / filename

        def df_to_html(df: pd.DataFrame) -> str:
            styled = df.copy()
            for c in styled.select_dtypes(include="number").columns:
                styled[c] = styled[c].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
            return styled.to_html(classes="dataframe", border=0, escape=False)

        images_html = ""
        if image_paths:
            for label, img in image_paths.items():
                if img and Path(img).exists():
                    images_html += (
                        f'<div class="chart"><h3>{label}</h3>'
                        f'<img src="{Path(img).name}" alt="{label}" style="max-width:100%;"/></div>\n'
                    )

        macro_html = ""
        if macro_result:
            phase = macro_result.get("phase", "—")
            score = macro_result.get("score", "—")
            signals = macro_result.get("signals", [])
            prefs = macro_result.get("preferred", {})
            sig_li = "".join(f"<li>{s}</li>" for s in signals)
            macro_html = f"""
  <h2>FRED Macro Overlay</h2>
  <p><strong>Cycle phase:</strong> {phase} &nbsp;|&nbsp; <strong>Score:</strong> {score}</p>
  <ul>{sig_li}</ul>
  <p><strong>Historically favored sectors:</strong> {', '.join(prefs.get('favored', [])) or '—'}</p>
  <p><strong>Historically avoided sectors:</strong> {', '.join(prefs.get('avoided', [])) or '—'}</p>
"""
            if "snapshot" in macro_result and macro_result["snapshot"] is not None:
                macro_html += "<h3>Macro Snapshot</h3>" + df_to_html(macro_result["snapshot"])

        industry_html = ""
        if ranks_industry is not None and not ranks_industry.empty:
            industry_html = "<h2>Industry Rankings</h2>" + df_to_html(ranks_industry)

        sr_html = ""
        if sr_sector is not None and not sr_sector.empty:
            cols = [c for c in ["Name", "Group", "Price", "Position", "Nearest_Support", "Dist_Support_%",
                                "Nearest_Resistance", "Dist_Resistance_%", "SMA_20", "SMA_50", "SMA_200",
                                "Above_All_MA", "Golden_Stack", "Pivot", "S1", "R1"] if c in sr_sector.columns]
            sr_html += "<h2>Sector Support / Resistance</h2>" + df_to_html(sr_sector[cols])
        if sr_industry is not None and not sr_industry.empty:
            cols = [c for c in ["Name", "Group", "Price", "Position", "Nearest_Support", "Dist_Support_%",
                                "Nearest_Resistance", "Dist_Resistance_%", "SMA_20", "SMA_50", "SMA_200",
                                "Above_All_MA", "Golden_Stack", "Pivot", "S1", "R1"] if c in sr_industry.columns]
            sr_html += "<h2>Industry Support / Resistance</h2>" + df_to_html(sr_industry[cols])

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Sector Rotation Report — {as_of}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         margin: 2rem; background: #f8f9fa; color: #212529; }}
  h1 {{ color: #0d6efd; }}
  h2 {{ margin-top: 2rem; border-bottom: 2px solid #dee2e6; padding-bottom: 0.3rem; }}
  .meta {{ color: #6c757d; margin-bottom: 1.5rem; }}
  .badge {{ display: inline-block; padding: 0.25em 0.6em; border-radius: 0.25rem;
            font-weight: 600; font-size: 0.9em; }}
  .risk-on {{ background: #d1e7dd; color: #0f5132; }}
  .risk-off {{ background: #f8d7da; color: #842029; }}
  .neutral {{ background: #e2e3e5; color: #41464b; }}
  table.dataframe {{ border-collapse: collapse; width: 100%; margin: 1rem 0; background: white;
                     box-shadow: 0 1px 3px rgba(0,0,0,0.08); font-size: 0.9rem; }}
  table.dataframe th, table.dataframe td {{ padding: 0.45rem 0.65rem; text-align: right;
                                            border-bottom: 1px solid #dee2e6; }}
  table.dataframe th {{ background: #e9ecef; text-align: left; }}
  table.dataframe td:first-child, table.dataframe th:first-child {{ text-align: left; }}
  .chart {{ margin: 1.5rem 0; background: white; padding: 1rem; border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  footer {{ margin-top: 3rem; color: #6c757d; font-size: 0.85em; }}
</style>
</head>
<body>
  <h1>Sector + Industry Rotation Monitor</h1>
  <div class="meta">
    Generated: {ts} &nbsp;|&nbsp; Market data as of: <strong>{as_of}</strong> &nbsp;|&nbsp;
    Price regime:
    <span class="badge {(regime.get('regime') or 'Neutral').lower().replace('-', '')}">
      {regime.get('regime', 'Unknown')}
    </span>
    {f"&nbsp;|&nbsp; Macro phase: <strong>{summary.get('macro_phase') or '—'}</strong>" if summary.get('macro_phase') else ""}
  </div>

  {macro_html}

  <h2>Sector RRG Snapshot</h2>
  {df_to_html(rrg)}

  <h2>Sector Composite Rankings</h2>
  {df_to_html(ranks)}

  {industry_html}

  {sr_html}

  <h2>Absolute Sector Returns (%)</h2>
  {df_to_html(abs_perf)}

  <h2>Excess Returns vs Benchmark (%)</h2>
  {df_to_html(rel_perf)}

  {images_html}

  <footer>
    Sector Rotation Monitor v1.1 — Equity data via Yahoo Finance; macro via FRED.
    For informational / research purposes only. Not investment advice.
  </footer>
</body>
</html>
"""
        path.write_text(html, encoding="utf-8")
        logger.info("HTML report → %s", path)
        return path
