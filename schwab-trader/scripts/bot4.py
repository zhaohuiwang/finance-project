# schwab-trader/scripts/bot4.py
"""
Schwab Trailing Momentum Bot - Launcher
=======================================
Main entry point for the trading bot with CLI and Dashboard support.

Based on bot3 structure.

Usage examples:

cd schwab-trader/scripts

# Default mode (Bot + Dashboard)
python3 bot4.py
# Open your browser → http://127.0.0.1:8050

# Change dashboard port
python3 bot4.py --port 8054

# Run Bot Only (Headless Mode) — No Dashboard
# Ideal for: Production / VPS / Server; Running in background; Using with screen, tmux, or systemd
python3 bot4.py --mode headless

# Run Bot with CLI Only (No Dashboard)
python3 bot4.py --mode cli

# Show help
python3 bot4.py --help
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
    parser.add_argument(
        "--mode",
        choices=["full", "cli", "headless"],
        default="full",
        help="full = bot + dashboard, cli = bot + CLI, headless = bot only",
    )
    parser.add_argument("--port", type=int, default=8050, help="Dashboard port")
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
            console.print(
                "[cyan]CLI ready — commands: stop | reload | status | positions[/cyan]"
            )
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
                        if not bot.holdings:
                            print("No open positions")
                        else:
                            for sym, h in bot.holdings.items():
                                print(f"{sym}: {h['shares']} shares @ ${h.get('buy_price', 0):.2f}")
                    else:
                        print("Commands: stop | reload | status | positions")
                except Exception:
                    break

        threading.Thread(target=cli_loop, daemon=True).start()

    # Dashboard
    if args.mode == "full":
        try:
            run_dashboard(bot, port=args.port)
        except Exception as e:
            console.print(f"[yellow]Dashboard error: {e}[/yellow]")
    else:
        console.print("[yellow]Running in headless / CLI mode (no dashboard)[/yellow]")
        try:
            while bot.running:
                time.sleep(10)
        except KeyboardInterrupt:
            bot.stop()