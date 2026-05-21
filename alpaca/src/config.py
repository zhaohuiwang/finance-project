# ================================================================================
# FILE: /home/zhaohuiwang/dev/finance-project/alpaca/src/config.py
# ================================================================================
from datetime import datetime
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
    symbols: list[str]
    timeframe: str
    check_interval: int
    log_file: str
    sector_etfs: dict[str, str] = {}
    earnings_blackout_days: int = 0

    @field_validator("earnings_blackout_days")
    @classmethod
    def earnings_days_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("earnings_blackout_days must be >= 0")
        return v

    @field_validator("symbols")
    @classmethod
    def symbols_valid(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("symbols must contain at least one ticker")
        cleaned = [s.strip().upper() for s in v]
        if any(not s for s in cleaned):
            raise ValueError("each symbol must be a non-empty string")
        return cleaned

    @field_validator("timeframe")
    @classmethod
    def timeframe_valid(cls, v: str) -> str:
        key = v.lower()
        if key not in _TIMEFRAME_MAP:
            raise ValueError(
                f"timeframe must be one of {list(_TIMEFRAME_MAP)}, got '{v}'"
            )
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
    volume_min_ratio: float = 0.0
    use_5m_confirmation: bool = False
    min_signal_confidence: float = 0.65

    # === NEW MARKET HOURS CONFIG ===
    use_regular_hours_only: bool = True
    market_open_time: str = "09:30"
    market_close_time: str = "16:00"

    @field_validator("market_open_time", "market_close_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            raise ValueError(f"Invalid time format '{v}'. Use HH:MM (e.g. 09:30)")

    @model_validator(mode="after")
    def validate_market_times(self) -> "StrategyConfig":
        if self.market_open_time >= self.market_close_time:
            raise ValueError("market_open_time must be before market_close_time")
        return self
    
    @field_validator("volume_min_ratio")
    @classmethod
    def volume_ratio_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("volume_min_ratio must be >= 0")
        return v

    @field_validator("min_signal_confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("min_signal_confidence must be between 0.0 and 1.0")
        return v

    @model_validator(mode="after")
    def fast_less_than_slow(self) -> "StrategyConfig":
        if self.fast_ma >= self.slow_ma:
            raise ValueError(
                f"fast_ma ({self.fast_ma}) must be less than slow_ma ({self.slow_ma})"
            )
        return self

    @field_validator("rsi_max_for_buy")
    @classmethod
    def rsi_in_range(cls, v: float) -> float:
        if not (0 < v < 100):
            raise ValueError("rsi_max_for_buy must be between 0 and 100")
        return v


class RiskConfig(BaseModel):
    risk_per_trade: float
    max_position_pct: float
    stop_loss_pct: float
    trailing_stop_pct: float
    take_profit_pct: Optional[float]
    daily_max_loss_pct: float
    stop_loss_cooldown_minutes: int

    # ==================== ATR Settings ====================
    atr_period: int = 14
    atr_multiplier: float = 2.5
    trailing_stop_enabled: bool = True
    trail_update_interval_minutes: int = 5
    use_wilder_atr: bool = True

    @field_validator(
        "risk_per_trade",
        "max_position_pct",
        "stop_loss_pct",
        "trailing_stop_pct",
        "atr_multiplier",
    )
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("value must be positive")
        return v

    @model_validator(mode="after")
    def risk_less_than_position(self) -> "RiskConfig":
        if self.risk_per_trade >= self.max_position_pct:
            raise ValueError(
                f"risk_per_trade ({self.risk_per_trade:.1%}) must be less than "
                f"max_position_pct ({self.max_position_pct:.1%})"
            )
        return self

    @field_validator("take_profit_pct")
    @classmethod
    def take_profit_positive_if_set(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("take_profit_pct must be positive if set")
        return v

    @field_validator("stop_loss_cooldown_minutes", "atr_period")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("value must be >= 0")
        return v

    @field_validator("daily_max_loss_pct")
    @classmethod
    def daily_loss_in_range(cls, v: float) -> float:
        if not (0 < v < 1):
            raise ValueError("daily_max_loss_pct must be between 0 and 1 (exclusive)")
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
