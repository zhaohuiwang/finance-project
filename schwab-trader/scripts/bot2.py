# bot.py
import argparse
import threading
import logging
import multiprocessing
import time
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('dash').setLevel(logging.ERROR)

from schwab_trader.config.bot.config import TradingConfig
from schwab_trader.pipelines.bot2_pipeline import TradingBot as CoreTradingBot


class TradingBot(CoreTradingBot):
    def __init__(self, config_path: Path):
        cfg = TradingConfig.load_from_file(config_path)
        super().__init__(cfg, mode="cli", config_path=config_path)
        self.dashboard_port = 8050
        self._dashboard_process = None

    def start_with_dashboard(self):
        self.start()

        self._dashboard_process = multiprocessing.Process(
            target=self._run_dashboard,
            daemon=False,          # Changed to False for stability
            name="DashboardProcess"
        )
        self._dashboard_process.start()

        console.print(f"[bold green]✅ Dashboard should be available at http://127.0.0.1:{self.dashboard_port}[/bold green]")

    def _run_dashboard(self):
        try:
            from dashboard2 import create_dashboard
            app = create_dashboard(self)
            console.print("[cyan]Starting Dash server...[/cyan]")
            app.run(debug=False, use_reloader=False, port=self.dashboard_port)
        except Exception as e:
            console.print(f"[red]Dashboard process crashed: {e}[/red]")
            import traceback
            traceback.print_exc()

    def stop(self):
        console.print("[yellow]Shutting down...[/yellow]")
        if self._dashboard_process and self._dashboard_process.is_alive():
            self._dashboard_process.terminate()
            self._dashboard_process.join(timeout=5)
        super().stop()


# ====================== CLI ======================
def cli_loop(bot):
    console.print("[cyan]CLI ready — type 'stop', 'reload', or 'status'[/cyan]")
    while bot.running:
        try:
            cmd = input("> ").strip().lower()
            if cmd == "stop":
                bot.stop()
                break
            elif cmd == "reload":
                console.print("[yellow]Reloading config...[/yellow]")
                bot.reload_config()
            elif cmd == "status":
                snap = bot.get_account_snapshot()
                print(f"Equity: ${snap['equity']:,.2f}")
                print(f"Positions: {len(bot.holdings)}")
                print(f"Dashboard PID: {bot._dashboard_process.pid if bot._dashboard_process else 'None'}")
            else:
                print("Commands: stop | reload | status")
        except EOFError:
            break
        except Exception as e:
            console.print(f"[red]CLI error: {e}[/red]")


# ====================== MAIN ======================
if __name__ == "__main__":
    console.print(f"RUNNING FILE: {__file__}")
    
    config_path = Path(__file__).parent / "../conf/simple_bot_config.yaml"
    bot = TradingBot(config_path)

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full", "cli"], default="cli")
    args = parser.parse_args()

    try:
        bot.start_with_dashboard()

        if args.mode == "cli":
            # Run CLI in a separate thread
            cli_thread = threading.Thread(target=cli_loop, args=(bot,), daemon=True)
            cli_thread.start()

        # Keep main process alive
        while bot.running:
            time.sleep(1)

    except KeyboardInterrupt:
        bot.stop()
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        bot.stop()