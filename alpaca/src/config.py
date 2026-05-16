from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator, model_validator
from alpaca.data.timeframe import TimeFrame


_TIMEFRAME_MAP: dict[str, TimeFrame] = {
    "minute": TimeFrame.Minute,
    "hour": TimeFrame.Hour,
    "day": TimeFrame.Day,
}

_DEFAULT_CONFIG = Path(__file__).parent.parent / "conf" / "config.yaml"


class TradingConfig(BaseModel):
    paper_trading: bool
    trade_only_market_hours: bool
    symbol: str
    timeframe: str
    check_interval: int
    log_file: str

    @field_validator("symbol")
    @classmethod
    def symbol_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("symbol must not be empty")
        return v.upper()

    @field_validator("timeframe")
    @classmethod
    def timeframe_valid(cls, v: str) -> str:
        key = v.lower()
        if key not in _TIMEFRAME_MAP:
            raise ValueError(f"timeframe must be one of {list(_TIMEFRAME_MAP)}, got '{v}'")
        return key

    @field_validator("check_interval")
    @classmethod
    def check_interval_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("check_interval must be a positive integer")
        return v

    @property
    def alpaca_timeframe(self) -> TimeFrame:
        return _TIMEFRAME_MAP[self.timeframe]


class StrategyConfig(BaseModel):
    fast_ma: int
    slow_ma: int
    rsi_period: int
    rsi_max_for_buy: float

    @model_validator(mode="after")
    def fast_less_than_slow(self) -> "StrategyConfig":
        if self.fast_ma >= self.slow_ma:
            raise ValueError(f"fast_ma ({self.fast_ma}) must be less than slow_ma ({self.slow_ma})")
        return self

    @field_validator("rsi_max_for_buy")
    @classmethod
    def rsi_in_range(cls, v: float) -> float:
        if not (0 < v < 100):
            raise ValueError("rsi_max_for_buy must be between 0 and 100")
        return v


class RiskConfig(BaseModel):
    risk_per_trade: float
    stop_loss_pct: float
    trailing_stop_pct: float
    take_profit_pct: Optional[float]

    @field_validator("risk_per_trade", "stop_loss_pct", "trailing_stop_pct")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("value must be positive")
        return v

    @field_validator("take_profit_pct")
    @classmethod
    def take_profit_positive_if_set(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("take_profit_pct must be positive if set")
        return v


class Config(BaseModel):
    trading: TradingConfig
    strategy: StrategyConfig
    risk: RiskConfig


def load_config(path: str | Path = _DEFAULT_CONFIG) -> Config:
    """Load and validate trading configuration from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(**data)
