
# dashboard2.py -- to be coupled with bot2.py


import dash
import dash_bootstrap_components as dbc
from dash import Dash, dcc, html, dash_table, Input, Output
from datetime import datetime
from rich.console import Console

console = Console()


def create_dashboard(bot):
    """Create dashboard - keeps your original logic as much as possible"""
    
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1.0'}],  # Mobile support
        assets_folder="assets",
    )

    app.layout = dbc.Container(
        [
            dbc.Row([
                dbc.Col(html.H2("Schwab Trading Bot Dashboard"), width=12),
            ], className="mb-4"),

            dbc.Row(
                dbc.Col([
                    dbc.Button("Refresh Now", id="refresh-button", color="primary", className="mb-3"),
                    dbc.Button("Reload Config", id="reload-config-button", color="warning", className="mb-3 ms-2"),
                ], width={"size": 6}),
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
                style_table={"overflowX": "auto", "maxWidth": "100%", "width": "100%"},
                style_cell={"textAlign": "left", "minWidth": "80px", "overflow": "hidden", "textOverflow": "ellipsis"},
                style_data={"color": "white", "backgroundColor": "#212529"},
                style_header={"backgroundColor": "#2c3e50", "color": "white"},
                style_data_conditional=[
                    {"if": {"filter_query": '{Today\'s % Chg} contains "+"'}, "color": "lime"},
                    {"if": {"filter_query": '{Today\'s % Chg} contains "-"'}, "color": "tomato"},
                    # Safe P/L coloring
                    {"if": {"filter_query": '{P/L %} contains "+"'}, "color": "lime"},
                    {"if": {"filter_query": '{P/L %} contains "-"'}, "color": "tomato"},
                ],
            ),

            html.H4("Managed Positions (config only)", className="mt-4 mb-2"),
            dash_table.DataTable(id="managed-positions-table", **get_managed_style()),

            html.H4("Open Orders", className="mt-5 mb-2"),
            dash_table.DataTable(id="orders-table", **get_default_style()),

            dbc.Row(
                dbc.Col([
                    html.H4("Account Summary", className="mt-5 mb-2"),
                    dash_table.DataTable(id="account-summary-table", **get_default_style()),
                ], width=6, lg=6, md=12, xs=12),
                className="mb-4",
            ),

            html.Div(id="status-footer", className="mt-5 text-center"),
            html.Div(id="last-updated", className="text-center text-muted small mt-2"),
            dcc.Interval(id="interval-component", interval=8 * 1000, n_intervals=0),
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
            Output("last-updated", "children"),
        ],
        [
            Input("interval-component", "n_intervals"),
            Input("refresh-button", "n_clicks"),
            Input("reload-config-button", "n_clicks"),
        ],
        prevent_initial_call=True,
    )
    def update_dashboard(n_interval, n_clicks, reload_clicks):
        ctx = dash.callback_context
        triggered_id = None
        if ctx and ctx.triggered:
            prop_id = ctx.triggered[0].get("prop_id", "")
            triggered_id = prop_id.split(".")[0] if prop_id else None

        if triggered_id == "reload-config-button" and reload_clicks:
            bot.reload_config()

        try:
            # === YOUR ORIGINAL LOGIC (kept almost 100% intact) ===
            managed_positions_data = []
            with bot.lock:
                for sym, cfg in sorted(bot.symbols_config.items()):
                    current_price = bot.current_market_prices.get(sym)
                    price_str = f"${current_price:,.2f}" if current_price else "—"
                    managed_positions_data.append({
                        "Symbol": sym,
                        "current_price": price_str,
                        "buy_target_price": f"{cfg.buy_target_price:.2f}",
                        "limit_sell_price": f"{cfg.limit_sell_price:.2f}",
                        "buy_drop_pct": f"{cfg.buy_drop_pct:.1f}%",
                        "limit_sell_pct": f"{cfg.limit_sell_pct:.1f}%",
                        "stop_loss_pct": f"{cfg.stop_loss_pct:.1f}%",
                        "fixed_shares": cfg.fixed_shares,
                    })

            orders_list = bot.get_open_orders()
            orders_data = []
            for o in orders_list:
                orders_data.append({
                    "ID": str(o.get("orderId", "N/A")),
                    "Symbol": o.get("symbol", "—"),
                    "Side": o.get("instruction", "—"),
                    "Price": f"${float(o.get('price') or 0):,.2f}" if o.get("price") else "—",
                    "Qty": o.get("quantity", 0),
                    "Type": o.get("type", "—"),
                    "Duration": o.get("duration", "—"),
                })

            snapshot = bot.get_account_snapshot()
            account_data = [
                {"Metric": "Equity(Net Liq)", "Value": f"${snapshot['equity']:,.2f}"},
                {"Metric": "Cash & Sweep Vehicle", "Value": f"${snapshot['cashBalance']:,.2f}"},
                {"Metric": "Buying Power", "Value": f"${snapshot['buyingPower']:,.2f}"},
                {"Metric": "Day Trading Buying Power", "Value": f"${snapshot['dayTradingBP']:,.2f}"},
                {"Metric": "Non-Marginable Buying Power", "Value": f"${snapshot['nonMarginableBP']:,.2f}"},
            ]

            all_holdings_data = []
            with bot.lock:
                for sym, h in bot.all_holdings.items():
                    price = bot.current_market_prices.get(sym) or h.get("current_price", None)
                    shares = h.get("shares", 0)
                    buy_p = h.get("buy_price")
                    price_safe = price if price is not None else 0.0
                    buy_p_safe = buy_p if buy_p is not None else 0.0
                    pl = round((price_safe - buy_p_safe) / buy_p_safe * 100, 1) if buy_p_safe > 0 else 0.0
                    market_val = round(shares * (price or 0), 2)
                    day_chg_pct = h.get("day_pct", 0.0)

                    all_holdings_data.append({
                        "Symbol": sym,
                        "Shares": shares,
                        "Avg Buy": f"${buy_p:,.2f}" if buy_p else "—",
                        "Price": f"${price:,.2f}" if price else "—",
                        "Today's % Chg": f"{day_chg_pct:+.2f}%" if abs(day_chg_pct) > 0.001 else "—",
                        "P/L %": f"{pl:+.1f}%",
                        "Market Value": f"${market_val:,.2f}",
                    })
            all_holdings_data.sort(key=lambda x: x["Symbol"])

            daily_pnl = (
                (snapshot["equity"] - bot.daily_start_equity) / bot.daily_start_equity * 100
                if bot.daily_start_equity > 0 else 0
            )
            risk_used = len(bot.holdings) / bot.risk_config.max_positions * 100 if getattr(bot.risk_config, 'max_positions', 0) > 0 else 0

            status_text = (
                f"Equity(Net Liq): ${snapshot['equity']:,.0f} | Daily P/L: {daily_pnl:+.1f}% | "
                f"Risk Used: {risk_used:.0f}% | {'PAUSED' if bot.trading_paused else 'ACTIVE'}"
            )

            last_updated = f"Last updated: {datetime.now().strftime('%H:%M:%S')}"

            return all_holdings_data, managed_positions_data, orders_data, account_data, status_text, last_updated

        except Exception as e:
            console.print(f"[red]Dashboard callback error: {e}[/red]")
            return [], [], [], [], "Dashboard error — check console", f"Error at {datetime.now().strftime('%H:%M:%S')}"

    return app


def get_managed_style():
    return {
        "style_table": {"overflowX": "auto", "maxWidth": "100%", "width": "100%"},
        "style_cell": {"textAlign": "right", "minWidth": "100px", "overflow": "hidden", "textOverflow": "ellipsis"},
        "style_header": {"backgroundColor": "#2c3e50", "color": "white", "fontWeight": "bold"},
        "style_data": {"color": "white", "backgroundColor": "#212529"},
        "style_data_conditional": [{"if": {"column_id": "current_price"}, "fontWeight": "bold", "color": "#00FFAA"}],
    }


def get_default_style():
    return {
        "style_table": {"overflowX": "auto", "maxWidth": "100%", "width": "100%"},
        "style_cell": {"textAlign": "left", "minWidth": "80px", "overflow": "hidden", "textOverflow": "ellipsis"},
        "style_data": {"color": "white", "backgroundColor": "#212529"},
        "style_header": {"backgroundColor": "#2c3e50", "color": "white"},
    }