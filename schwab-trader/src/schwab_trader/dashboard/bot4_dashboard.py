

# schwab-trader/src/schwab_trader/dashboard/bot4_dashboard.py
"""
Dash-based web dashboard for the Schwab Trailing Momentum Bot (Bot4).
Aligned with bot4_pipeline.py and bot4_config.yaml.
Style and layout closely follow bot3_dashboard.py.
"""

import logging
import dash
import dash_bootstrap_components as dbc
from dash import Dash, dcc, html, dash_table, Input, Output
from rich.console import Console

from schwab_trader.pipelines.bot4_pipeline import TradingBot

# Suppress logs
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("dash").setLevel(logging.ERROR)

console = Console()

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    assets_folder="assets",
)

# Global reference
bot: TradingBot = None


# ====================== LAYOUT ======================
app.layout = dbc.Container(
    [
        dbc.Row(
            [dbc.Col(html.H2("Schwab Trailing Momentum Bot"), width=12)],
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(
                [
                    dbc.Button(
                        "Refresh Now",
                        id="refresh-button",
                        color="primary",
                        className="mb-3",
                    ),
                    dbc.Button(
                        "Reload Config",
                        id="reload-config-button",
                        color="warning",
                        className="mb-3 ms-2",
                    ),
                ],
                width={"size": 6},
            ),
            className="mb-3",
        ),

        # ---------- Current Account Holdings ----------
        html.H4("Current Account Holdings", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="all-holdings-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Price", "id": "Price"},
                {"name": "Today's % Chg", "id": "Today's % Chg"},
                {"name": "Shares", "id": "Shares"},
                {"name": "Avg Buy", "id": "Avg Buy"},
                {"name": "P/L %", "id": "P/L %"},
                {"name": "Market Value", "id": "Market Value"},
            ],
            style_table={"overflowX": "auto", "width": "100%"},
            style_cell={"textAlign": "left", "minWidth": "80px"},
            style_data={"color": "white", "backgroundColor": "#212529"},
            style_header={"backgroundColor": "#2c3e50", "color": "white"},
            style_data_conditional=[
                {
                    "if": {"filter_query": '{Today\'s % Chg} contains "+"'},
                    "color": "lime",
                },
                {
                    "if": {"filter_query": '{Today\'s % Chg} contains "-"'},
                    "color": "tomato",
                },
            ],
        ),

        # ---------- Managed Symbols (Bot4 strategy) ----------
        html.H4("Managed Symbols (Trailing Momentum Config)", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="managed-positions-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Current Price", "id": "current_price"},
                {"name": "Prev Close", "id": "prev_close"},
                {"name": "Momentum %", "id": "momentum_pct"},
                {"name": "Momentum Trigger", "id": "momentum_up_pct"},
                {"name": "Trail Sell %", "id": "trailing_sell_pct"},
                {"name": "Pullback Buy %", "id": "pullback_buy_pct"},
                {"name": "Trail Buy %", "id": "trailing_buy_pct"},
                {"name": "Fixed Shares", "id": "fixed_shares"},
                {"name": "Last Sell", "id": "last_sell"},
            ],
            style_table={"overflowX": "auto", "width": "100%"},
            style_cell={"textAlign": "right", "minWidth": "90px"},
            style_header={
                "backgroundColor": "#2c3e50",
                "color": "white",
                "fontWeight": "bold",
            },
            style_data={"color": "white", "backgroundColor": "#212529"},
            style_data_conditional=[
                # Momentum coloring for the momentum_pct column only
                {
                    "if": {
                        "filter_query": '{momentum_pct} contains "+"',
                        "column_id": "momentum_pct",
                    },
                    "color": "lime",
                    "fontWeight": "bold",
                },
                {
                    "if": {
                        "filter_query": '{momentum_pct} contains "-"',
                        "column_id": "momentum_pct",
                    },
                    "color": "tomato",
                    "fontWeight": "bold",
                },

                # Current price always highlighted
                {
                    "if": {"column_id": "current_price"},
                    "fontWeight": "bold",
                    "color": "#00FFAA",
                },
            ],
        ),

        # ---------- Open Orders ----------
        html.H4("Open Orders", className="mt-5 mb-2"),
        dash_table.DataTable(
            id="orders-table",
            columns=[
                {"name": "ID", "id": "ID"},
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Side", "id": "Side"},
                {"name": "Type", "id": "Type"},
                {"name": "Price / Offset", "id": "Price"},
                {"name": "Qty", "id": "Qty"},
                {"name": "Duration", "id": "Duration"},
                {"name": "Strategy", "id": "Strategy"},
            ],
            style_table={"overflowX": "auto", "width": "100%"},
            style_cell={"textAlign": "left", "minWidth": "80px"},
            style_data={"color": "white", "backgroundColor": "#212529"},
            style_header={"backgroundColor": "#2c3e50", "color": "white"},
            style_data_conditional=[
                {
                    "if": {"filter_query": '{Type} = "TRAILING_STOP"'},
                    "color": "#00E5FF",
                    "fontWeight": "bold",
                },
                {
                    "if": {"filter_query": '{Type} = "LIMIT"'},
                    "color": "lime",
                },
                {
                    "if": {"filter_query": '{Type} contains "STOP"'},
                    "color": "orange",
                },
            ],
        ),

        # ---------- Account Summary ----------
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
                        style_table={"width": "100%"},
                        style_header={
                            "backgroundColor": "#2c3e50",
                            "color": "white",
                            "fontWeight": "bold",
                        },
                        style_data={"color": "white", "backgroundColor": "#212529"},
                    ),
                ],
                width=6,
            ),
            className="mb-4",
        ),

        html.Div(id="status-footer", className="mt-5 text-center"),
        dcc.Interval(id="interval-component", interval=8000, n_intervals=0),
    ],
    fluid=True,
    className="p-4",
)


@app.callback(
    [
        Output("all-holdings-table", "data"),
        Output("managed-positions-table", "data"),
        Output("orders-table", "data"),
        Output("account-summary-table", "data"),
        Output("status-footer", "children"),
    ],
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-button", "n_clicks"),
        Input("reload-config-button", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def update_dashboard(n_interval, n_clicks, reload_clicks):
    """Update all dashboard components."""
    ctx = dash.callback_context
    triggered_id = None
    if ctx and ctx.triggered:
        prop_id = ctx.triggered[0].get("prop_id", "")
        triggered_id = prop_id.split(".")[0] if prop_id else None

    if triggered_id == "reload-config-button" and reload_clicks and bot:
        bot.reload_config()

    try:
        # ---------- Current Holdings ----------
        holdings_data = []
        with bot.lock:
            for sym, h in sorted(bot.holdings.items()):
                price = bot.day_prices.get(sym, {}).get("market") or h.get("buy_price")
                shares = h.get("shares", 0)
                buy_p = h.get("buy_price")
                hwm = bot.day_prices.get(sym, {}).get("hwm")

                pl = (
                    round((price - buy_p) / buy_p * 100, 1)
                    if buy_p and buy_p > 0 and price
                    else 0.0
                )
                market_val = round(shares * (price or 0), 2)
                day_chg = h.get("day_pct", 0.0)

                holdings_data.append(
                    {
                        "Symbol": sym,
                        "Shares": shares,
                        "Avg Buy": f"${buy_p:,.2f}" if buy_p else "—",
                        "Price": f"${price:,.2f}" if price else "—",
                        "Today's % Chg": (f"{day_chg:+.2f}%" if abs(day_chg) > 0.001 else "—"),
                        "P/L %": f"{pl:+.1f}%",
                        "Market Value": f"${market_val:,.2f}",
                    }
                )

        # ---------- Managed Symbols ----------
        managed_data = []
        with bot.lock:
            for sym, cfg in sorted(bot.symbols_config.items()):
                price = bot.day_prices.get(sym, {}).get("market")
                prev_close = bot.day_prices.get(sym, {}).get("close")
                hwm = bot.day_prices.get(sym, {}).get("hwm")
                last_sell = bot.last_sell_prices.get(sym)

                momentum_pct = None
                if price and prev_close and prev_close > 0:
                    momentum_pct = ((price - prev_close) / prev_close) * 100

                managed_data.append(
                    {
                        "Symbol": sym,
                        "current_price": f"${price:,.2f}" if price else "—",
                        "prev_close": f"${prev_close:,.2f}" if prev_close else "—",
                        "momentum_pct": (
                            f"{momentum_pct:+.2f}%" if momentum_pct is not None else "—"
                        ),
                        "momentum_up_pct": f"{cfg.momentum_up_pct:.1f}%",
                        "trailing_sell_pct": f"{cfg.trailing_sell_pct:.1f}%",
                        "pullback_buy_pct": f"{cfg.pullback_buy_pct:.1f}%",
                        "trailing_buy_pct": f"{cfg.trailing_buy_pct:.1f}%",
                        "fixed_shares": cfg.fixed_shares,
                        "last_sell": f"${last_sell:,.2f}" if last_sell else "—",
                        "hwm": f"${hwm:,.2f}" if hwm else "—",
                    }
                )

        # ---------- Open Orders ----------
        orders_data = []
        for o in bot.get_open_orders():
            price_val = o.get("price")
            price_str = (
                f"${float(price_val):,.2f}" if price_val not in (None, "", 0) else "—"
            )
            orders_data.append(
                {
                    "ID": str(o.get("orderId", "N/A")),
                    "Symbol": o.get("symbol", "—"),
                    "Side": o.get("instruction", "—"),
                    "Type": o.get("type", "—"),
                    "Price": price_str,
                    "Qty": o.get("quantity", 0),
                    "Duration": o.get("duration", "—"),
                    "Strategy": o.get("orderStrategyType", "—"),
                }
            )

        # ---------- Account Summary ----------
        snapshot = bot.get_account_snapshot()
        account_data = [
            {"Metric": "Equity (Net Liq)", "Value": f"${snapshot.get('equity', 0):,.2f}"},
            {"Metric": "Cash", "Value": f"${snapshot.get('cashBalance', 0):,.2f}"},
            {"Metric": "Buying Power", "Value": f"${snapshot.get('buyingPower', 0):,.2f}"},
        ]

        # ---------- Status footer ----------
        daily_pnl = (
            (snapshot["equity"] - bot.daily_start_equity) / bot.daily_start_equity * 100
            if getattr(bot, "daily_start_equity", 0) > 0
            else 0.0
        )

        status = "PAUSED" if getattr(bot, "trading_paused", False) else "ACTIVE"

        status_text = (
            f"Equity: ${snapshot.get('equity', 0):,.0f} | "
            f"Daily P/L: {daily_pnl:+.1f}% | "
            f"Positions: {len(bot.holdings)} | "
            f"{status}"
        )

        return holdings_data, managed_data, orders_data, account_data, status_text

    except Exception as e:
        console.print(f"[red]Dashboard callback error: {e}[/red]")
        return [], [], [], [], f"Dashboard error: {e}"


def run_dashboard(trading_bot: TradingBot, port: int = 8050):
    """Start the dashboard."""
    global bot
    bot = trading_bot
    console.print(
        f"[bold green]✅ Bot4 Dashboard running at http://127.0.0.1:{port}[/bold green]"
    )
    app.run(debug=False, use_reloader=False, port=port)