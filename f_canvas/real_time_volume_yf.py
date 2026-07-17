
"""
This Python program is a real-time stock trading volume monitor. It continuously watches selected stock symbols (default: AAPL, MSFT, GOOGL) using Yahoo Finance data, detects unusual volume spikes, and sends alerts through email and Pushover notifications. It also writes logs to the console and a rotating log file.

The normal output is nothing except a startup log. It becomes active only when a stock's trading volume suddenly increases.
"""

import click
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time


from email.mime.text import MIMEText
import requests
import smtplib

# from twilio.rest import Client
import yfinance as yf

# include all credentials in `.evn` file, in the current dir or the parent
load_dotenv()


def setup_logger(
    logger_name: str = "MyAppLogger", log_file: str = "app.log", log_level=logging.DEBUG
):
    """
    Create a centralized logger configuration.
    List of logging levels: DEBUG (10) > INFO (20) > WARNING (30) > ERROR (40) > CRITICAL (50)
    """
    # Create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    # Prevent adding handlers if logger is already configured
    if not logger.handlers:
        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%m/%d/%Y %I:%M:%S %p",
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler with rotation (max 5MB, keep 5 backups)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=50 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# def send_sms_alert(message):
#     """Send SMS alert using Twilio."""
#     try:
#         client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
#         client.messages.create(
#             body=message,
#             from_=TWILIO_PHONE_NUMBER,
#             to=YOUR_PHONE_NUMBER
#         )
#         logging.info("SMS alert sent successfully.")
#     except Exception as e:
#         logging.error(f"Failed to send SMS: {e}")


def send_email_alert(message):
    """
    Send email alert using SMTP.
    You need to setup App passwords and used it instead of your google account ligin password.
    https://myaccount.google.com/apppasswords
    """
    try:
        msg = MIMEText(message)
        msg["Subject"] = "Stock Volume Alert"
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = RECIPIENT_EMAIL

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
        logging.info("Email alert sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")


def send_pushover_alert(message):
    """Send push notification using Pushover."""
    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_API_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "message": message,
            },
        )
        if response.status_code == 200:
            logging.info("Pushover alert sent successfully.")
        else:
            logging.error(f"Failed to send Pushover alert: {response.text}")
    except Exception as e:
        logging.error(f"Failed to send Pushover alert: {e}")


def monitor_stock_volumes(symbols, interval=60, volume_threshold=1.5):
    """
    Monitor trading volume for a list of stock symbols and send alerts on significant increases.

    Args:
        symbols (list): List of stock ticker symbols (e.g., ['AAPL', 'MSFT'])
        interval (int): Time interval between checks in seconds
        volume_threshold (float): Multiplier to detect significant volume increase
    """
    try:
        # Initialize stock objects and previous volume dictionary
        stocks = {symbol: yf.Ticker(symbol) for symbol in symbols}
        prev_volumes = {symbol: None for symbol in symbols}

        while True:
            for symbol in symbols:
                try:
                    # Fetch 1-minute interval data for the latest trading day
                    data = stocks[symbol].history(period="1d", interval="1m")

                    if data.empty:
                        logging.warning(
                            f"No data available for {symbol}. Market may be closed or symbol invalid."
                        )
                        continue

                    # Get the latest volume
                    current_volume = data["Volume"].iloc[-2]
                    # data['Volume'].iloc[-1] is always 0

                    if prev_volumes[symbol] is not None:
                        # Check for significant volume increase
                        if current_volume > prev_volumes[symbol] * volume_threshold:
                            alert_message = (
                                f"Volume spike detected for {symbol}! "
                                f"Previous: {prev_volumes[symbol]}, Current: {current_volume}"
                            )
                            logging.info(alert_message)
                            # send_sms_alert(alert_message) # via Twilio
                            send_email_alert(alert_message)  # via SMTP
                            send_pushover_alert(alert_message)  # via Pushover

                    # Update previous volume
                    prev_volumes[symbol] = current_volume

                except Exception as e:
                    logging.error(f"Error fetching data for {symbol}: {e}")

            # Wait for the next tick
            time.sleep(interval)

    except Exception as e:
        logging.error(f"Failed to initialize stock monitoring: {e}")


@click.command()
@click.option(
    "--stock_symbols",
    type=list,
    default=["AAPL", "MSFT", "GOOGL"],
    help="List of stock symbols",
)
@click.option(
    "--check_interval", type=int, default=60, help="Tracing time interval in second"
)
@click.option(
    "--volume_spike_threshold",
    type=float,
    default=1.5,
    help="Volume spike threshold in times, e.g. 1.5 indicating 50 percent increase in volume considered as a spike",
)
def main(stock_symbols, check_interval, volume_spike_threshold):
    """ """
    logging = setup_logger(
        logger_name=__name__, log_file=Path(__file__).parent.parent / "app.log"
    )

    logging.info(f"Running at: {Path.cwd()}")

    monitor_stock_volumes(stock_symbols, check_interval, volume_spike_threshold)


if __name__ == "__main__":

    main()
