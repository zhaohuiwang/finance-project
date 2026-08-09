# schwab-trader/src/schwab_trader/config/bot/bot3_config.py
from typing import Dict
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
import yaml


# ----------------------------
# 1. Individual symbol config
# ----------------------------
class SymbolConfig(BaseModel):
    fixed_shares: int = Field(default=0, ge=0)
    buy_target_price: float = Field(default=float("inf"), ge=0)
    limit_sell_price: float = Field(gt=0)
    buy_drop_pct: float = Field(ge=0)
    stop_loss_pct: float = Field(ge=0)
    stop_loss_dollar: float = Field(default=0.0, ge=0)

    # Trailing parameters
    trail_activation_price: float = Field(gt=0)
    trail_offset_pct: float = Field(default=3.0, ge=0, le=50.0)

    @model_validator(mode="after")
    def validate_price_relationships(self):
        """
        Enforce sensible relationships between:
        - buy_target_price
        - trail_activation_price
        - trail_offset_pct
        - limit_sell_price
        """
        # 1. Take-profit must be above buy price
        if self.limit_sell_price <= self.buy_target_price:
            raise ValueError(
                f"limit_sell_price ({self.limit_sell_price}) must be greater than "
                f"buy_target_price ({self.buy_target_price})"
            )

        # 2. Trail activation must be above buy price
        if self.trail_activation_price <= self.buy_target_price:
            raise ValueError(
                f"trail_activation_price ({self.trail_activation_price}) must be greater than "
                f"buy_target_price ({self.buy_target_price})"
            )

        # 3. Take-profit must be above trail activation (threshold1)
        if self.limit_sell_price <= self.trail_activation_price:
            raise ValueError(
                f"limit_sell_price ({self.limit_sell_price}) must be greater than "
                f"trail_activation_price ({self.trail_activation_price})"
            )

        # 4. Even after a full trail from the activation price,
        #    the stop should still land above the buy price
        worst_trail_price = self.trail_activation_price * (
            1 - self.trail_offset_pct / 100
        )
        if worst_trail_price <= self.buy_target_price:
            raise ValueError(
                f"Trailing stop is too wide. "
                f"trail_activation_price * (1 - trail_offset_pct/100) = {worst_trail_price:.4f} "
                f"must be greater than buy_target_price ({self.buy_target_price}). "
                f"Either raise trail_activation_price or reduce trail_offset_pct."
            )

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

    auto_shutdown_after_close: bool = Field(
        default=True,
        description="Enable automatic graceful shutdown after regular market close",
    )
    shutdown_buffer_minutes: int = Field(
        default=5,
        ge=0,
        le=60,
        description="Minutes after 4:00 PM ET to wait before shutdown",
    )
    shutdown_on_weekends: bool = Field(
        default=True,
        description="If False, skip auto-shutdown on Saturday and Sunday",
    )

    @classmethod
    def load_from_file(cls, path: str | Path) -> "TradingConfig":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)
