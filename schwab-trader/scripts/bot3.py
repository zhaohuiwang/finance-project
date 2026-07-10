# schwab-trader/scripts/bot2.py
"""
Main entry point for the Schwab Trading Bot.
Supports headless, CLI, and full dashboard modes.

cd schwab-trader/scripts
# Default mode (Bot + Dashboard)
python3 bot3.py
# Open your browser → http://127.0.0.1:8050

# Change dashboard port
python3 bot3.py --port 8080

# Run Bot Only (Headless Mode) — No Dashboard This is ideal for: Production / VPS / Server; Running in background; Using with screen, tmux, or systemd
python3 bot3.py --mode headless

# Run Bot with CLI Only (No Dashboard)
python3 bot3.py --mode cli

# Show help
python3 bot3.py --help


# Create/Edit the Service File
sudo nano /etc/systemd/system/schwab-bot.service
# Fill the servie file

# Run the service file
# Reload systemd to apply changes
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable --now schwab-bot.service


Command                                     Action
sudo systemctl stop schwab-bot.service      # Stop the bot
sudo systemctl start schwab-bot.service     # Start the bot
sudo systemctl restart schwab-bot.service   # Restart the bot

journalctl -u schwab-bot.service -f         # View live logs

sudo systemctl status schwab-bot.service    # Check current status
sudo systemctl disable schwab-bot.service   # Disable auto-start on boot
sudo systemctl enable schwab-bot.service    # Enable auto-start on boot
sudo systemctl is-enabled schwab-bot.service    # Check if auto-start is enabled

# To remove the service
sudo systemctl stop schwab-bot.service          # Stop the service (if it's running)
sudo systemctl disable schwab-bot.service       # Disable auto-start
sudo rm /etc/systemd/system/schwab-bot.service  # Remove the service file
sudo systemctl daemon-reload                    # Reload systemd to apply changes
sudo systemctl reset-failed                     # Reset any failed state (optional but recommended)
"""

import argparse
import threading
import sys
from pathlib import Path
from rich.console import Console

from schwab_trader.config.bot.config import TradingConfig
from schwab_trader.pipelines.bot2_pipeline import TradingBot
from dashboard import run_dashboard

console = Console()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schwab Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["full", "cli", "headless"],
        default="full",
        help="full = bot + dashboard, cli = bot + CLI, headless = bot only",
    )
    parser.add_argument("--port", type=int, default=8050, help="Dashboard port")
    args = parser.parse_args()

    config_path = Path(__file__).parent / "../conf/simple_bot_config.yaml"
    cfg = TradingConfig.load_from_file(config_path)
    bot = TradingBot(cfg, mode=args.mode, config_path=config_path)

    console.print(f"[bold green]Starting TradingBot in {args.mode} mode[/bold green]")
    bot.start()

    # CLI
    if args.mode in ("full", "cli") and sys.stdin.isatty():

        def cli_loop():
            console.print("[cyan]CLI ready — commands: stop | reload | status[/cyan]")
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
                    else:
                        print("Commands: stop | reload | status")
                except:
                    break

        threading.Thread(target=cli_loop, daemon=True).start()

    # Dashboard
    if args.mode == "full":
        run_dashboard(bot, port=args.port)
    else:
        console.print("[yellow]Running in headless mode (no dashboard)[/yellow]")
        try:
            while bot.running:
                import time

                time.sleep(10)
        except KeyboardInterrupt:
            bot.stop()
