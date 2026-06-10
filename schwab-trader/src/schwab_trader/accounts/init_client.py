

"""
Access token expires in: 30 minutes
Refresh token expires in: 7 days

# Normal run
python3 src/schwab_trader/accounts/init_client.py

# Reset tokens (with confirmation)
python3 src/schwab_trader/accounts/init_client.py --clean-tokens
or 
python3 src/schwab_trader/accounts/init_client.py --reset

--tokens-path allows you to specify a custom location for the tokens.db file. By default, it uses ~/.schwabdev/tokens.db.
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
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ========================= SCHWAB AUTH SETUP =========================

def initialize_client(
    tokens_path="~/.schwabdev/tokens.db"
    ):
    """Normal initialization using existing tokens.db"""
    try:        
        tokens_path = str(Path(tokens_path).expanduser())
        APP_KEY = os.getenv("APP_KEY")
        APP_SECRET = os.getenv("APP_SECRET")
        CALLBACK_URL = os.getenv("CALLBACK_URL")
        logger.info(f"Initializing Schwab Client with tokens at: {tokens_path}")
    except Exception as e:
        logger.error(f"Error occurred while initializing tokens path: {e}")
        raise

    return schwabdev.Client(
        APP_KEY,
        APP_SECRET,
        callback_url=CALLBACK_URL,
        tokens_db=tokens_path
    )
    
# ========================= CLEAN TOKENS =========================
def clean_file(file_path: str | Path):
    """Safely delete a file with user confirmation. Accepts str or Path."""
    
    # Convert to Path if string is passed
    if isinstance(file_path, str):
        file_path = Path(file_path).expanduser()
    elif isinstance(file_path, Path):
        file_path = file_path.expanduser()
    else:
        raise TypeError("file_path must be str or Path")

    if not file_path.exists():
        logger.info(f"No file found at: {file_path}")
        return

    logger.warning(f"About to permanently delete: {file_path}")
    logger.warning("This action cannot be undone.")

    # User confirmation
    confirm = input("Are you sure you want to delete this file? (yes/y): ").strip().lower()
    
    if confirm in ["yes", "y", "ye"]:
        try:
            file_path.unlink(missing_ok=True)
            logger.info(f"✅ Successfully deleted: {file_path}")
            
            # Optional: Clean up parent directory if empty
            parent = file_path.parent
            if not any(parent.iterdir()):
                try:
                    parent.rmdir()
                    logger.info(f"🗑️  Removed empty directory: {parent}")
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"❌ Failed to delete file: {e}")
    else:
        logger.info("🛑 File deletion cancelled by user.")
        sys.exit(0)


# ========================= MAIN EXECUTION =========================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Schwab Trader API Authentication Setup")
    parser.add_argument(
        "--clean-tokens",
        "--reset",
        action="store_true",
        help="Delete existing tokens.db and force re-authentication"
    )
    parser.add_argument(
        "--tokens-path",
        type=str,
        default=None,
        help="Custom path to tokens.db (default: ~/.schwabdev/tokens.db)"
    )
    
    args =parser.parse_args()
    tokens_path = args.tokens_path or str(Path("~/.schwabdev/tokens.db").expanduser())
    
    # Handle token cleaning
    if args.clean_tokens:
        clean_file(tokens_path)
    
    client = initialize_client()

