# schwab-trader/src/schwab_trader/config/bot/config.py

from typing import Dict
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
import yaml


# ----------------------------
# 1. Individual symbol config
# ----------------------------
class SymbolConfig(BaseModel):
    buy_target_price: float = Field(default=float("inf"), ge=0)
    limit_sell_price: float = Field(gt=0)
    buy_drop_pct: float = Field(ge=0)
    limit_sell_pct: float = Field(ge=0)
    stop_loss_pct: float = Field(ge=0)
    fixed_shares: int = Field(default=0, ge=0)
    stop_loss_dollar: float = Field(default=0.0, ge=0)   # fixed $ amount below entry
    # If > 0, use this as primary stop distance; otherwise fall back to %

    @model_validator(mode="after")
    def check_prices(self):
        if self.limit_sell_price <= self.buy_target_price:
            raise ValueError("limit_sell_price must be greater than buy_target_price")
        return self


# ----------------------------
# 2. Overall risk config
# ----------------------------
class RiskConfig(BaseModel):
    risk_per_trade_pct: float
    max_positions: int
    min_account_equity: float
    max_daily_loss_pct: float
    default_shares: int = Field(default=1)


# ----------------------------
# 3. Full configuration
# ----------------------------
class TradingConfig(BaseModel):
    symbols: Dict[str, SymbolConfig]
    risk: RiskConfig

    @classmethod
    def load_from_file(cls, path: str | Path) -> "TradingConfig":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)
