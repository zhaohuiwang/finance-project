import argparse
import threading
import logging
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, dcc, html, dash_table, Input, Output
from dotenv import load_dotenv
from rich.console import Console

from schwab_trader.config.bot.config import TradingConfig
from schwab_trader.pipelines.bot2 import TradingBot

load_dotenv()
console = Console()

# Suppress noisy logs
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('dash').setLevel(logging.ERROR)

# Load config & bot
config_path = Path(__file__).parent / "../conf/simple_bot_config.yaml"
cfg = TradingConfig.load_from_file(config_path)
bot = TradingBot(cfg, mode="cli")

# ====================== DASH APP ======================
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    assets_folder="assets",
    title="Schwab Trading Bot",
    suppress_callback_exceptions=True,
)

app.layout = dbc.Container(
    [
        dbc.Row(dbc.Col(html.H2("Schwab Trading Bot Dashboard"), width=12), className="mb-4"),
        
        dbc.Row(dbc.Col(
            dbc.Button("Refresh Now", id="refresh-button", color="primary", className="mb-3"),
            width=3
        )),

        # All Holdings
        html.H4("All Account Holdings", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="all-holdings-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Shares", "id": "Shares"},
                {"name": "Price", "id": "Price"},
                {"name": "Avg Buy", "id": "Avg Buy"},
                {"name": "P/L %", "id": "P/L %"},
                {"name": "Market Value", "id": "Market Value"},
            ],
            style_table={"overflowX": "auto", "width": "100%"},
            style_cell={"textAlign": "left", "minWidth": "90px"},
            style_header={"backgroundColor": "#2c3e50", "color": "white", "fontWeight": "bold"},
            style_data={"backgroundColor": "#212529", "color": "white"},
        ),

        # Managed Symbols - FIXED
        html.H4("Managed Symbols (Config)", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="managed-positions-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Buy Target", "id": "buy_target_price"},
                {"name": "Limit Sell", "id": "limit_sell_price"},
                {"name": "Stop Loss %", "id": "stop_loss_pct"},
                {"name": "Fixed Shares", "id": "fixed_shares"},
            ],
            style_table={"overflowX": "auto", "width": "100%"},
            style_cell={"textAlign": "right"},
            style_header={"backgroundColor": "#2c3e50", "color": "white", "fontWeight": "bold"},
        ),

        # Open Orders - IMPROVED FOR OCO
        html.H4("Open Orders (Including OCO Brackets)", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="orders-table",
            columns=[
                {"name": "Symbol", "id": "Symbol"},
                {"name": "Order Type", "id": "Type"},
                {"name": "Side", "id": "Side"},
                {"name": "Qty", "id": "Qty"},
                {"name": "Price / Stop", "id": "Price"},
                {"name": "Status", "id": "Status"},
            ],
            style_table={"overflowX": "auto", "width": "100%"},
            style_cell={"textAlign": "left"},
            style_header={"backgroundColor": "#2c3e50", "color": "white", "fontWeight": "bold"},
            style_data_conditional=[
                {"if": {"filter_query": '{Side} = "BUY"'}, "color": "lime"},
                {"if": {"filter_query": '{Side} contains "SELL"'}, "color": "tomato"},
            ],
        ),

        # Account Summary
        html.H4("Account Summary", className="mt-4 mb-2"),
        dash_table.DataTable(
            id="account-summary-table",
            columns=[{"name": "Metric", "id": "Metric"}, {"name": "Value", "id": "Value"}],
            style_header={"backgroundColor": "#2c3e50", "color": "white", "fontWeight": "bold"},
            style_data={"backgroundColor": "#212529", "color": "white"},
        ),

        html.Div(id="status-footer", className="mt-4 text-center"),

        dcc.Interval(id="interval-component", interval=10 * 1000, n_intervals=0),
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
    [Input("interval-component", "n_intervals"), Input("refresh-button", "n_clicks")],
)
def update_dashboard(n_interval, n_clicks):
    try:
        # 1. Managed Symbols (Config)
        managed_data = []
        for sym, cfg in sorted(bot.symbols_config.items()):
            managed_data.append({
                "Symbol": sym,
                "buy_target_price": f"${cfg.buy_target_price:.2f}",
                "limit_sell_price": f"${cfg.limit_sell_price:.2f}",
                "stop_loss_pct": f"{getattr(cfg, 'stop_loss_pct', 0):.1f}%",
                "fixed_shares": cfg.fixed_shares,
            })

        # 2. Open Orders - Better OCO handling
        raw_orders = bot.get_open_orders()
        orders_data = []
        seen = set()

        for o in raw_orders:
            key = (o.get("orderId"), o.get("symbol"), o.get("instruction"))
            if key in seen:
                continue
            seen.add(key)

            symbol = o.get("symbol", "—")
            side = o.get("instruction", "—")
            qty = o.get("quantity", "—")
            price = o.get("price")
            price_str = f"${float(price):.2f}" if price else "—"

            order_type = "OCO BRACKET" if any(k in str(o) for k in ["childOrderStrategies", "OCO"]) else "SINGLE"

            orders_data.append({
                "Symbol": symbol,
                "Type": order_type,
                "Side": side,
                "Qty": qty,
                "Price": price_str,
                "Status": "WORKING",
            })

        # 3. Account Summary
        snap = bot.get_account_snapshot()
        account_data = [
            {"Metric": "Equity (Net Liq)", "Value": f"${snap.get('equity', 0):,.2f}"},
            {"Metric": "Cash & Sweep", "Value": f"${snap.get('cashBalance', 0):,.2f}"},
            {"Metric": "Buying Power", "Value": f"${snap.get('buyingPower', 0):,.2f}"},
        ]

        # 4. All Holdings
        holdings_data = []
        with bot.lock:
            for sym, h in bot.all_holdings.items():
                price = bot.current_market_prices.get(sym) or h.get("current_price")
                shares = int(h.get("shares", 0))
                buy_p = h.get("buy_price")
                pl = round(((price or 0) - (buy_p or 0)) / (buy_p or 1) * 100, 1) if buy_p and buy_p > 0 else 0

                holdings_data.append({
                    "Symbol": sym,
                    "Shares": shares,
                    "Price": f"${price:,.2f}" if price else "—",
                    "Avg Buy": f"${buy_p:,.2f}" if buy_p else "—",
                    "P/L %": f"{pl:+.1f}%",
                    "Market Value": f"${(shares * (price or 0)):,.2f}",
                })

        # Status Footer
        status_text = (
            f"Equity: ${snap.get('equity', 0):,.0f} | "
            f"Positions: {len(bot.holdings)} | "
            f"Open Orders: {len(orders_data)} | "
            f"Status: {'🛑 PAUSED' if bot.trading_paused else '✅ ACTIVE'}"
        )

        return holdings_data, managed_data, orders_data, account_data, status_text

    except Exception as e:
        console.print(f"[red]Dashboard update error: {e}[/red]")
        return [], [], [], [], f"Error: {str(e)}"


# ====================== MAIN ======================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schwab Trading Bot")
    parser.add_argument("--mode", choices=["full", "cli"], default="cli")
    args = parser.parse_args()

    bot.start()

    if args.mode == "cli":
        def cli_loop():
            console.print("[cyan]CLI ready — type 'stop' to shutdown[/cyan]")
            while bot.running:
                try:
                    cmd = input("> ").strip().lower()
                    if cmd == "stop":
                        bot.stop()
                        break
                except:
                    break
        threading.Thread(target=cli_loop, daemon=True).start()

    console.print("[bold green]✅ Quiet Dashboard running at http://127.0.0.1:8050[/bold green]")
    app.run(debug=False, use_reloader=False, port=8050)