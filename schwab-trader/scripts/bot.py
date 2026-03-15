# schwab-trader/scripts/bot.py

import argparse
import threading

import dash_bootstrap_components as dbc
import pandas as pd

from dotenv import load_dotenv
from pathlib import Path
from rich.console import Console
from schwab_trader.config.bot.config import TradingConfig
from dash import Dash, dcc, html, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate

from schwab_trader.pipelines.bot import TradingBot


load_dotenv()
console = Console()

cfg = TradingConfig.load_from_file(
    Path(__file__).parent / "../conf/bot/conf.yaml"
)


bot = TradingBot(cfg, mode="cli")  # your class instance


# ── Dash app ────────────────────────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],  # SLATE, CYBORG or FLATLY, etc
    assets_folder="assets",
)

app.layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(html.H2("Schwab Trading Bot Dashboard"), width=12),
            ],
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(
                dbc.Button(
                    "Refresh Now",
                    id="refresh-button",
                    color="primary",
                    className="mb-3",
                ),
                width={"size": 3, "offset": 0},
            ),
            className="mb-3",
        ),
        # Positions - full width (unchanged)
        html.H4("Positions", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="positions-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Price", "id": "Price"},
                {"name": "Shares", "id": "Shares"},
                {"name": "Avg Buy", "id": "Avg Buy"},
                {"name": "P/L %", "id": "P/L %"},
                {"name": "Status", "id": "Status"},
            ],
            style_table={
                "overflowX": "auto",
                "maxWidth": "100%",
                "width": "100%",
            },
            style_cell={
                "textAlign": "left",
                "minWidth": "80px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_data={"color": "white", "backgroundColor": "#212529"},
            style_header={"backgroundColor": "#2c3e50", "color": "white"},
        ),
        # Open Orders - full width (unchanged)
        html.H4("Open Orders", className="mt-5 mb-2"),
        dash_table.DataTable(
            id="orders-table",
            columns=[
                {"name": "ID", "id": "ID"},
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Qty", "id": "Qty"},
                {"name": "Price", "id": "Price"},
                {"name": "Side", "id": "Side"},
                {"name": "Type", "id": "Type"},
                {"name": "Duration", "id": "Duration"},
            ],
            style_table={
                "overflowX": "auto",
                "maxWidth": "100%",
                "width": "100%",
            },
            style_cell={
                "textAlign": "left",
                "minWidth": "80px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_data={"color": "white", "backgroundColor": "#212529"},
            style_header={"backgroundColor": "#2c3e50", "color": "white"},
        ),
        # ── Account Summary - now half width ────────────────────────────────
        dbc.Row(
            dbc.Col(
                [
                    html.H4("Account Summary", className="mt-5 mb-2"),
                    dash_table.DataTable(
                        id="account-summary-table",
                        columns=[
                            {"name": "Metric", "id": "Metric"},
                            {"name": "Value", "id": "Value"},
                        ],
                        style_table={
                            "overflowX": "auto",
                            "maxWidth": "100%",
                            "width": "100%",  # ← fills the column
                        },
                        style_cell={"textAlign": "left"},
                        style_header={
                            "backgroundColor": "#2c3e50",
                            "color": "white",
                            "fontWeight": "bold",
                        },
                        style_data={
                            "color": "white",
                            "backgroundColor": "#212529",
                        },
                    ),
                ],
                width=6,  # ← this is the key change: half width
                lg=6,
                md=12,  # full width on smaller screens
                xs=12,
            ),
            className="mb-4",  # adds some bottom margin
        ),
        # Footer
        html.Div(id="status-footer", className="mt-5 text-center"),
        dcc.Interval(id="interval-component", interval=8 * 1000, n_intervals=0),
    ],
    fluid=True,
    className="p-4",
)


# ── FIXED CALLBACK ────────────────────────────────────────────────────────────
@app.callback(
    [
        Output("positions-table", "data"),
        Output("orders-table", "data"),
        Output("account-summary-table", "data"),
        Output("status-footer", "children"),
    ],
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-button", "n_clicks"),
    ],
    prevent_initial_call=True,  # optional: skip first empty call
)
def update_dashboard(n_interval, n_clicks):
    try:
        # Positions
        positions_data = []
        with bot.lock:
            for sym in bot.symbols_config:
                price = bot.current_prices.get(sym)
                h = bot.holdings.get(sym, {})
                shares = h.get("shares", 0)
                buy_p = h.get("buy_price")
                pl = (
                    round((price - buy_p) / buy_p * 100, 1)
                    if price and buy_p and buy_p > 0
                    else 0.0
                )
                positions_data.append(
                    {
                        "Symbol": sym,
                        "Price": f"${price:,.2f}" if price else "—",
                        "Shares": shares,
                        "Avg Buy": f"${buy_p:,.2f}" if buy_p else "—",
                        "P/L %": f"{pl:+.1f}%",
                        "Status": "HOLDING" if shares > 0 else "WATCHING",
                    }
                )

        # Open Orders
        orders_list = bot.get_open_orders()
        orders_data = []
        for o in orders_list:
            orders_data.append(
                {
                    "ID": str(o.get("orderId", "N/A")),
                    "Symbol": o.get("symbol", "—"),
                    "Qty": o.get("quantity", 0),
                    "Price": (
                        f"${float(o.get('price') or 0):,.2f}" if o.get("price") else "—"
                    ),
                    "Side": o.get("instruction", "—"),
                    "Type": o.get("type", "—"),
                    "Duration": o.get("duration", "—"),
                }
            )

        # Account Summary
        snapshot = bot.get_account_snapshot()

        account_data = [
            {"Metric": "Equity(Net Liq)", "Value": f"${snapshot['equity']:,.2f}"},
            {
                "Metric": "Cash & Sweep Vehicle",
                "Value": f"${snapshot['cashBalance']:,.2f}",
            },
            {"Metric": "Buying Power", "Value": f"${snapshot['buyingPower']:,.2f}"},
            {
                "Metric": "Day Trading Buying Power",
                "Value": f"${snapshot['dayTradingBP']:,.2f}",
            },
            {
                "Metric": "Non-Marginable Buying Power",
                "Value": f"${snapshot['nonMarginableBP']:,.2f}",
            },
        ]

        daily_pnl = (
            (snapshot["equity"] - bot.daily_start_equity) / bot.daily_start_equity * 100
            if bot.daily_start_equity > 0
            else 0
        )
        risk_used = len(bot.holdings) / bot.risk_config.max_positions * 100
        status_text = (
            f"Equity(Net Liq): ${snapshot['equity']:,.0f} | Daily P/L: {daily_pnl:+.1f}% | "
            f"Risk Used: {risk_used:.0f}% | {'PAUSED' if bot.trading_paused else 'ACTIVE'}"
        )

        return positions_data, orders_data, account_data, status_text

    except Exception as e:
        console.print(f"[red]Dashboard callback error: {e}[/red]")
        return [], [], [], "Dashboard error — check console"


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schwab Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["full", "cli"],
        default="cli",
        help="full = rich terminal dashboard + web dashboard | cli = web dashboard only + terminal commands",
    )
    args = parser.parse_args()

    bot = TradingBot(cfg, mode=args.mode)
    bot.start_stream()

    # Start logic thread
    logic_thread = threading.Thread(target=bot.monitor_logic, daemon=True)
    logic_thread.start()

    # Add the watchdog thread
    watchdog_thread = threading.Thread(target=bot.stream_watchdog, daemon=True)
    watchdog_thread.start()


    if args.mode == "full":
        display_thread = threading.Thread(target=bot.monitor_display, daemon=True)
        display_thread.start()
        console.print("[bold green]FULL MODE - Terminal + Web dashboard active[/bold green]")
    else:
        cli_thread = threading.Thread(target=bot.cli_loop, daemon=True)
        cli_thread.start()
        console.print("[bold green]CLI MODE - Web dashboard only + terminal commands active[/bold green]")

    app.run(debug=True, use_reloader=False)

    # print("Dashboard starting → open http://127.0.0.1:8050/")
    # Fix: remove duplicate app = dash.Dash line (was in your original)

