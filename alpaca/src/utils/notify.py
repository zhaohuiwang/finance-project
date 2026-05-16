import requests


def send_telegram_message(message: str, token: str | None, chat_id: str | None) -> None:
    """Send a Markdown-formatted message to a Telegram chat. Silently no-ops if credentials are missing."""
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=15)
    except Exception:
        pass
