# bot2.py
import argparse
import threading
import logging
import multiprocessing
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# Suppress noisy logs
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('dash').setLevel(logging.ERROR)

from schwab_trader.config.bot.config import TradingConfig
from schwab_trader.pipelines.bot2_pipeline import TradingBot as CoreTradingBot


class TradingBot(CoreTradingBot):
    """Wrapper to support dashboard in separate process"""
    def __init__(self, config_path: Path):
        cfg = TradingConfig.load_from_file(config_path)
        super().__init__(cfg, mode="cli", config_path=config_path)
        self.dashboard_port = 8050
        self._dashboard_process = None

    def start_with_dashboard(self):
        self.start()  # Start bot logic, streamer, etc.

        # Start Dashboard in separate process
        self._dashboard_process = multiprocessing.Process(
            target=self._run_dashboard,
            daemon=True,
            name="DashboardProcess"
        )
        self._dashboard_process.start()

        console.print(f"[bold green]✅ Bot running + Dashboard at http://127.0.0.1:{self.dashboard_port}[/bold green]")

    def _run_dashboard(self):
        """Run dashboard in separate process"""
        import sys
        sys.path.append(str(Path(__file__).parent))
        from dashboard2 import create_dashboard
        app = create_dashboard(self)
        app.run(debug=False, use_reloader=False, port=self.dashboard_port)

    def stop(self):
        if self._dashboard_process and self._dashboard_process.is_alive():
            self._dashboard_process.terminate()
            self._dashboard_process.join(timeout=3)
        super().stop()


# ====================== MAIN ======================
if __name__ == "__main__":
    console.print(f"RUNNING FILE: {__file__}")
    
    config_path = Path(__file__).parent / "../conf/simple_bot_config.yaml"
    bot = TradingBot(config_path)

    parser = argparse.ArgumentParser(description="Schwab Trading Bot")
    parser.add_argument("--mode", choices=["full", "cli"], default="cli")
    args = parser.parse_args()

    try:
        bot.start_with_dashboard()

        if args.mode == "cli":
            def cli_loop():
                console.print("[cyan]CLI ready — type 'stop' to shutdown[/cyan]")
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
                            print(f"Equity: {snap['equity']:.2f}")
                            print(f"Positions: {len(bot.holdings)}")
                        else:
                            print("Commands: stop | reload | status")
                    except:
                        break

            threading.Thread(target=cli_loop, daemon=True).start()

    except KeyboardInterrupt:
        bot.stop()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        bot.stop()