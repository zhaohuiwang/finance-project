# src/schwab_bot/config_model.py

from pydantic import BaseModel, Field, HttpUrl
from typing import Dict


class TickerRule(BaseModel):
    buy_below: float
    sell_above: float


class APISettings(BaseModel):
    app_key: str
    app_secret: str
    callback_url: HttpUrl
    account_id: str


class BotConfig(BaseModel):
    api: APISettings
    tickers: Dict[str, TickerRule]
    polling_interval: int = Field(default=5, gt=0)
    log_file: str
