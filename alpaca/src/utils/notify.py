# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/src/utils/notify.py
# ================================================================================

import requests
from utils.logger import get_logger

logger = get_logger(__name__)


def notify(message: str, token: str | None = None, chat_id: str | None = None) -> None:
    """
    Log message and send to Telegram.
    Can be called with explicit token/chat_id or use global ones.
    """
    logger.info(message)

    # If token and chat_id not passed, try to use globals from the calling script
    if not token or not chat_id:
        # This is a bit tricky without globals, so we'll keep token/chat_id passing for now
        pass

    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}")


# For backward compatibility with existing scripts
def send_telegram_message(message: str, token: str | None, chat_id: str | None) -> None:
    notify(message, token, chat_id)