"""
Schwab Trailing Momentum Bot - Launcher
=======================================
Main entry point for the trading bot with CLI and Dashboard support.
"""

import argparse
import sys
import threading
import time
from pathlib import Path
from rich.console import Console
from schwab_trader.config.bot.bot4_config import TradingConfig
from schwab_trader.pipelines.bot4_pipeline import TradingBot
from schwab_trader.dashboard.bot4_dashboard import run_dashboard

console = Console()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schwab Trailing Momentum Trading Bot")
    parser.add_argument("--mode", choices=["full", "cli", "headless"], default="full")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()

    config_path = Path(__file__).parent / "../conf/bot4_config.yaml"

    if not config_path.exists():
        console.print(f"[red]Config not found: {config_path}[/red]")
        sys.exit(1)

    cfg = TradingConfig.load_from_file(config_path)
    bot = TradingBot(cfg, mode=args.mode, config_path=config_path)

    console.print(
        f"[bold green]Starting Trailing Momentum Bot in {args.mode} mode[/bold green]"
    )

    bot.start()

    # CLI
    if args.mode in ("full", "cli") and sys.stdin.isatty():

        def cli_loop():
            console.print("[cyan]Commands: stop | reload | status | positions[/cyan]")
            while bot.running:
                try:
                    cmd = input("> ").strip().lower()
                    if cmd == "stop":
                        bot.stop()
                        break
                    elif cmd == "reload":
                        bot.reload_config()
                    elif cmd == "status":
                        snap = bot.get_account_snapshot()
                        print(
                            f"Equity: ${snap['equity']:,.2f} | Positions: {len(bot.holdings)}"
                        )
                    elif cmd == "positions":
                        bot.update_holdings_from_api()
                        for sym, h in bot.holdings.items():
                            print(f"{sym}: {h['shares']} shares")
                except:
                    break

        threading.Thread(target=cli_loop, daemon=True).start()

    # Dashboard
    if args.mode == "full":
        try:
            run_dashboard(bot, port=args.port)
        except Exception as e:
            console.print(f"[yellow]Dashboard error: {e}[/yellow]")

    # Keep alive
    try:
        while bot.running:
            time.sleep(10)
    except KeyboardInterrupt:
        bot.stop()
