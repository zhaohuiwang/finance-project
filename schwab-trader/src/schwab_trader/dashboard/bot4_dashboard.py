


# schwab-trader/scripts/bot4_dashboard.py


import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from datetime import datetime
import threading
import time

def run_dashboard(bot, port=8050):
    """Launch interactive Dash dashboard for the trading bot."""
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
    
    app.layout = dbc.Container([
        dbc.Row([
            dbc.Col(html.H1("Schwab Trailing Momentum Bot", className="text-center mb-4"), width=12)
        ]),
        dbc.Row([
            dbc.Col([
                html.Div(id="status", className="mb-3"),
                dbc.Button("Refresh", id="refresh-btn", color="primary", className="mb-3"),
                dbc.Button("Reload Config", id="reload-btn", color="info", className="mb-3 mx-2"),
                dbc.Button("Stop Bot", id="stop-btn", color="danger")
            ], width=12)
        ]),
        dbc.Row([
            dbc.Col([
                dcc.Graph(id="price-chart"),
                dcc.Interval(id="interval", interval=5000, n_intervals=0)  # 5s refresh
            ], width=8),
            dbc.Col([
                html.H4("Holdings"),
                html.Div(id="holdings-table"),
                html.H4("Prices & Momentum", className="mt-4"),
                html.Div(id="prices-table")
            ], width=4)
        ])
    ], fluid=True)

    @app.callback(
        [Output("status", "children"),
         Output("price-chart", "figure"),
         Output("holdings-table", "children"),
         Output("prices-table", "children")],
        [Input("interval", "n_intervals"),
         Input("refresh-btn", "n_clicks")]
    )
    def update_dashboard(n, refresh_clicks):
        snap = bot.get_account_snapshot()
        status = dbc.Alert(
            f"Equity: ${snap['equity']:,.2f} | Cash: ${snap['cashBalance']:,.2f} | "
            f"Positions: {len(bot.holdings)} | Paused: {bot.trading_paused}",
            color="success" if snap["equity"] > bot.daily_start_equity else "warning"
        )

        # Price & Momentum Table
        price_rows = []
        for sym in bot.symbols:
            price = bot.current_market_prices.get(sym)
            prev = bot.previous_closes.get(sym)
            if price and prev:
                pct = ((price - prev) / prev) * 100
                color = "green" if pct > 0 else "red"
                price_rows.append(html.Tr([
                    html.Td(sym),
                    html.Td(f"${price:.2f}"),
                    html.Td(html.Span(f"{pct:+.1f}%", style={"color": color}))
                ]))

        prices_table = dbc.Table([
            html.Thead(html.Tr([html.Th("Symbol"), html.Th("Price"), html.Th("Momentum")]))
        ] + [html.Tbody(price_rows)], bordered=True)

        # Holdings
        holdings_rows = []
        for sym, h in bot.holdings.items():
            holdings_rows.append(html.Tr([
                html.Td(sym),
                html.Td(h["shares"]),
                html.Td(f"${h.get('buy_price', 0):.2f}")
            ]))
        holdings_table = dbc.Table([
            html.Thead(html.Tr([html.Th("Symbol"), html.Th("Shares"), html.Th("Avg Price")]))
        ] + [html.Tbody(holdings_rows)], bordered=True) if holdings_rows else html.P("No positions")

        # Simple price line chart (last few updates - basic)
        fig = go.Figure()
        for sym in list(bot.symbols)[:3]:  # Limit to 3 for clarity
            price = bot.current_market_prices.get(sym)
            if price:
                fig.add_trace(go.Scatter(
                    x=[datetime.now().strftime("%H:%M:%S")],
                    y=[price],
                    mode="lines+markers",
                    name=sym
                ))
        fig.update_layout(title="Live Prices", template="plotly_dark", height=400)

        return status, fig, holdings_table, prices_table

    @app.callback(
        Output("status", "children"),
        Input("reload-btn", "n_clicks")
    )
    def reload_config_callback(n):
        if n:
            bot.reload_config()
            return dbc.Alert("Config reloaded successfully!", color="info")
        return dash.no_update

    @app.callback(
        Output("status", "children"),
        Input("stop-btn", "n_clicks")
    )
    def stop_bot_callback(n):
        if n:
            bot.stop()
            return dbc.Alert("Bot stopped. Restart the script to run again.", color="danger")
        return dash.no_update

    print(f"🚀 Dashboard running at http://127.0.0.1:{port}")
    app.run(debug=False, port=port, use_reloader=False)