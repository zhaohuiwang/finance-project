"""
Access token expires in: 30 minutes
Refresh token expires in: 7 days

Command                                      clean_tokens
python3 src/schwab_trader/accounts/init_client.py                       False
python3 src/schwab_trader/accounts/init_client.py --reset               True
python3 src/schwab_trader/accounts/init_client.py --clean-tokens        True

python3 src/schwab_trader/accounts/init_client.py \
    --reset \
    --tokens-path /tmp/my-tokens.db

python3 src/schwab_trader/accounts/init_client.py --help

--tokens-path allows you to specify a custom location for the tokens.db file. By default, it uses ~/.schwabdev/tokens.db. This is the default token database location by schwabdev. It is generally not recommended to put tokens.db inside the Git repository or project directory as by doing so poses risk of accidental explosure if private credentials to the public or unintentional sharing among the collaborators.

"""

import argparse
import logging
import os
from dotenv import load_dotenv
from pathlib import Path
import sys

import schwabdev

load_dotenv()

# ========================= LOGGING SETUP =========================
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ========================= SCHWAB AUTH SETUP =========================
DEFAULT_TOKENS_PATH = Path("~/.schwabdev/tokens.db").expanduser() # The .expanduser() method replaces a leading tilde (~) or ~user in a file path with the user's home directory.

def initialize_client(tokens_path: str | Path):
    """Initialize the Schwab client using the specified tokens database."""
    try:
        tokens_path = Path(tokens_path).expanduser()

        app_key = os.getenv("APP_KEY")
        app_secret = os.getenv("APP_SECRET")
        callback_url = os.getenv("CALLBACK_URL")

        if not app_key:
            raise RuntimeError("APP_KEY is not set")

        if not app_secret:
            raise RuntimeError("APP_SECRET is not set")

        if not callback_url:
            raise RuntimeError("CALLBACK_URL is not set")

        logger.info("Initializing Schwab Client")
        logger.info("Tokens database: %s", tokens_path)
        logger.info("Tokens database exists: %s", tokens_path.exists())

        tokens_path = str(Path(tokens_path).expanduser())
        APP_KEY = os.getenv("APP_KEY")
        APP_SECRET = os.getenv("APP_SECRET")
        CALLBACK_URL = os.getenv("CALLBACK_URL")
        logger.info(f"Initializing Schwab Client with tokens at: {tokens_path}")
    except Exception as e:
        logger.error(f"Error occurred while initializing Schwab Client with tokens at '{tokens_path}': {e}")
        raise

    return schwabdev.Client(
        APP_KEY, APP_SECRET,
        callback_url=CALLBACK_URL,
        tokens_db=str(tokens_path),
    )


# ========================= CLEAN TOKENS =========================
def clean_file(file_path: str | Path):
    """Safely delete a tokens file after user confirmation."""
    file_path = Path(file_path).expanduser()

    if not file_path.exists():
        logger.info("No file found at: %s", file_path)
        return

    logger.warning("About to permanently delete: %s", file_path)
    logger.warning("This action cannot be undone.")

    confirm = input(
        "Are you sure you want to delete this file? (yes/y): "
    ).strip().lower()

    if confirm not in {"yes", "y", "ye"}:
        logger.info("🛑 File deletion cancelled by user.")
        sys.exit(0)

    try:
        file_path.unlink()
        logger.info("Successfully deleted: %s", file_path)

        # Remove parent directory if empty.
        parent = file_path.parent

        try:
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                logger.info("Removed empty directory: %s", parent)
        except OSError:
            pass

    except Exception as e:
        logger.error("❌ Failed to delete file: %s", e)
        raise


# ========================= MAIN EXECUTION =========================
def main():
    parser = argparse.ArgumentParser(
        description="Schwab Trader API Authentication Setup"
    )

    parser.add_argument(
        "--clean-tokens",
        "--reset",  # alias to --clean-token
        action="store_true", 
        # Flag style command-line argument (option as it starts with --): with action="store_true", if --reset is provided arg.reset is True; if --reset (or --clear-tokens) is not provided arg.reset is False.
        dest="clean_tokens",
        # destination or assignment. The value of the CLI option(s) either --reset or --clean-token is assigned to args.clean_tokens
        help="Delete existing tokens.db and force re-authentication",
    )

    parser.add_argument(
        
        "--tokens-path",
        type=Path,
        # type=Path is a converter here to convert a string into a Path object.
        default=DEFAULT_TOKENS_PATH,
        help=f"Custom path to tokens.db "
             f"(default: {DEFAULT_TOKENS_PATH})",
    )

    args = parser.parse_args()

    tokens_path = args.tokens_path.expanduser()

    logger.info("========================================")
    logger.info("Schwab authentication configuration")
    logger.info("tokens_path = %s", tokens_path)
    logger.info("clean_tokens = %s", args.clean_tokens)
    logger.info("========================================")

    # Reset/delete tokens if requested.
    if args.clean_tokens:
        clean_file(tokens_path)

    # Always initialize using the EXACT path supplied by argparse.
    client = initialize_client(tokens_path)

    return client


if __name__ == "__main__":
    main()
