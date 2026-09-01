# schwab-trader/src/schwab_trader/dashboard/bot3_dashboard.py
"""
Dash-based web dashboard for the Schwab Trading Bot.
Completely separated from core bot logic.
"""

import logging
import dash
import dash_bootstrap_components as dbc
from dash import Dash, dcc, html, dash_table, Input, Output
from rich.console import Console

from schwab_trader.pipelines.bot3_pipeline import TradingBot
from rich.console import Console
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
            [dbc.Col(html.H2("Schwab Trading Bot Dashboard"), width=12)],
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
        html.H4("All Account Holdings", className="mt-4 mb-2"),
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
        html.H4("Managed Positions (config)", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="managed-positions-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Current Price", "id": "current_price"},
                {"name": "Buy Target", "id": "buy_target_price"},
                {"name": "Trail Activate (T1)", "id": "trail_activation_price"},
                {"name": "Limit Sell (T2)", "id": "limit_sell_price"},
                {"name": "Trail Offset %", "id": "trail_offset_pct"},
                {"name": "Stop Loss", "id": "stop_loss"},  # $ or %
                {"name": "Fixed Shares", "id": "fixed_shares"},
                {"name": "HWM", "id": "hwm"},
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
                {
                    "if": {"column_id": "current_price"},
                    "fontWeight": "bold",
                    "color": "#00FFAA",
                }
            ],
        ),
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
        # Managed Positions
        managed_data = []
        with bot.lock:
            for sym, cfg in sorted(bot.symbols_config.items()):
                price = bot.day_prices.get(sym, {}).get("market")
                hwm = bot.day_prices.get(sym, {}).get("hwm")

                # Show $ stop when configured, otherwise %
                if getattr(cfg, "stop_loss_dollar", 0) and cfg.stop_loss_dollar > 0:
                    stop_display = f"${cfg.stop_loss_dollar:.2f}"
                else:
                    stop_display = f"{cfg.stop_loss_pct:.1f}%"

                managed_data.append(
                    {
                        "Symbol": sym,
                        "current_price": f"${price:,.2f}" if price else "—",
                        "buy_target_price": f"{cfg.buy_target_price:.2f}",
                        "trail_activation_price": f"{getattr(cfg, 'trail_activation_price', 0):.2f}",
                        "limit_sell_price": f"{cfg.limit_sell_price:.2f}",
                        "trail_offset_pct": f"{getattr(cfg, 'trail_offset_pct', 0):.1f}%",
                        "stop_loss": stop_display,
                        "fixed_shares": cfg.fixed_shares,
                        "hwm": f"{hwm:.2f}",
                    }
                )

        # Open Orders
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

        # Account Summary
        snapshot = bot.get_account_snapshot()
        account_data = [
            {"Metric": "Equity(Net Liq)", "Value": f"${snapshot['equity']:,.2f}"},
            {"Metric": "Cash & Sweep", "Value": f"${snapshot['cashBalance']:,.2f}"},
            {"Metric": "Buying Power", "Value": f"${snapshot['buyingPower']:,.2f}"},
            {"Metric": "Day Trading BP", "Value": f"${snapshot['dayTradingBP']:,.2f}"},
            {
                "Metric": "Non-Marginable BP",
                "Value": f"${snapshot['nonMarginableBP']:,.2f}",
            },
        ]

        # All Holdings
        all_holdings_data = []
        with bot.lock:
            for sym, h in bot.all_holdings.items():
                price = bot.day_prices.get(sym, {}).get("market") or h.get("current_price")
                shares = h.get("shares", 0)
                buy_p = h.get("buy_price")
                pl = (
                    round((price - buy_p) / buy_p * 100, 1)
                    if buy_p and buy_p > 0
                    else 0.0
                )
                market_val = round(shares * (price or 0), 2)
                day_chg = h.get("day_pct", 0.0)

                all_holdings_data.append(
                    {
                        "Symbol": sym,
                        "Shares": shares,
                        "Avg Buy": f"${buy_p:,.2f}" if buy_p else "—",
                        "Price": f"${price:,.2f}" if price else "—",
                        "Today's % Chg": (
                            f"{day_chg:+.2f}%" if abs(day_chg) > 0.001 else "—"
                        ),
                        "P/L %": f"{pl:+.1f}%",
                        "Market Value": f"${market_val:,.2f}",
                    }
                )
        all_holdings_data.sort(key=lambda x: x["Symbol"])

        daily_pnl = (
            (snapshot["equity"] - bot.daily_start_equity) / bot.daily_start_equity * 100
            if bot.daily_start_equity > 0
            else 0
        )
        risk_used = (
            len(bot.holdings) / getattr(bot.risk_config, "max_positions", 4) * 100
        )

        status_text = (
            f"Equity(Net Liq): ${snapshot['equity']:,.0f} | "
            f"Daily P/L: {daily_pnl:+.1f}% | "
            f"Risk Used: {risk_used:.0f}% | "
            f"{'PAUSED' if bot.trading_paused else 'ACTIVE'}"
        )

        return all_holdings_data, managed_data, orders_data, account_data, status_text

    except Exception as e:
        console.print(f"[red]Dashboard callback error: {e}[/red]")
        return [], [], [], [], "Dashboard error — check console"


def run_dashboard(trading_bot: TradingBot, port: int = 8050):
    """Start the dashboard."""
    global bot
    bot = trading_bot
    console.print(f"[bold green]✅ Dashboard running at http://127.0.0.1:{port}[/bold green]")
    app.run(debug=False, use_reloader=False, port=port)