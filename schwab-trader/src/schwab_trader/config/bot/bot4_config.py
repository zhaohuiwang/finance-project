


"""
# schwab-trader/src/schwab_trader/config/bot/bot4_config.py

Schwab Trading Bot Configuration Module
=======================================

Pydantic-based configuration system with full support for the trailing momentum strategy.
"""

from pydantic import BaseModel, Field
from pathlib import Path
import yaml
from typing import Dict


class SymbolConfig(BaseModel):
    """
    Configuration for individual trading symbols in the trailing momentum strategy.
    """
    # Core trading parameters
    fixed_shares: int = Field(
        default=100, 
        ge=1, 
        description="Number of shares to trade per order"
    )
    
    # Momentum Sell Parameters
    momentum_up_pct: float = Field(
        default=5.0, 
        ge=0.0, 
        description="x% gain from previous day's close to trigger trailing sell"
    )
    trailing_sell_pct: float = Field(
        default=2.0, 
        ge=0.1, 
        description="a% trailing stop percentage for sell orders"
    )
    
    # Pullback Buy Parameters
    pullback_buy_pct: float = Field(
        default=3.0, 
        ge=0.0, 
        description="y% drop from last sell price to trigger trailing buy"
    )
    trailing_buy_pct: float = Field(
        default=1.5, 
        ge=0.1, 
        description="b% trailing stop percentage for buy orders"
    )
    
    # Additional risk controls
    max_position_value: float = Field(
        default=10000.0, 
        ge=0.0, 
        description="Maximum dollar value per position"
    )


class RiskConfig(BaseModel):
    """
    Global risk management settings for the trading bot.
    """
    min_account_equity: float = Field(
        default=5000.0, 
        ge=1000.0, 
        description="Minimum account equity before pausing trading"
    )
    max_positions: int = Field(
        default=4, 
        ge=1, 
        description="Maximum number of concurrent positions"
    )


class TradingConfig(BaseModel):
    """
    Main configuration container for the entire trading bot.
    """
    risk: RiskConfig = Field(default_factory=RiskConfig)
    symbols: Dict[str, SymbolConfig] = Field(default_factory=dict)
    
    # Bot behavior settings
    auto_shutdown_after_close: bool = Field(
        default=True, 
        description="Automatically shutdown after market close"
    )
    shutdown_buffer_minutes: int = Field(
        default=2, 
        ge=0, 
        description="Minutes to wait after market close before shutdown"
    )
    shutdown_on_weekends: bool = Field(
        default=True, 
        description="Shutdown on weekends"
    )

    @classmethod
    def load_from_file(cls, config_path: Path) -> "TradingConfig":
        """
        Load configuration from a YAML file.
        
        Args:
            config_path: Path to the YAML configuration file
            
        Returns:
            TradingConfig instance
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # Convert symbol dictionaries to SymbolConfig objects
        if "symbols" in data and isinstance(data["symbols"], dict):
            symbols_dict = {}
            for symbol, config_data in data["symbols"].items():
                symbols_dict[symbol] = SymbolConfig(**config_data)
            data["symbols"] = symbols_dict
        
        # Convert risk config
        if "risk" in data and isinstance(data["risk"], dict):
            data["risk"] = RiskConfig(**data["risk"])
        
        return cls(**data)

    def save_to_file(self, config_path: Path):
        """
        Save current configuration to a YAML file.
        
        Args:
            config_path: Path where to save the config
        """
        data = self.model_dump(mode='python')
        
        # Convert Pydantic objects to dicts for YAML serialization
        if isinstance(data.get("symbols"), dict):
            for sym, cfg in data["symbols"].items():
                if hasattr(cfg, "model_dump"):
                    data["symbols"][sym] = cfg.model_dump()
        
        if hasattr(data.get("risk"), "model_dump"):
            data["risk"] = data["risk"].model_dump()
        
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data, 
                f, 
                default_flow_style=False, 
                sort_keys=False,
                indent=2
            )

    def get_symbol_config(self, symbol: str) -> SymbolConfig | None:
        """Get configuration for a specific symbol."""
        return self.symbols.get(symbol)


# Example default configuration (for reference)
DEFAULT_CONFIG = {
    "risk": {
        "min_account_equity": 5000,
        "max_positions": 4
    },
    "symbols": {
        "AAPL": {
            "fixed_shares": 50,
            "momentum_up_pct": 5.0,
            "trailing_sell_pct": 2.0,
            "pullback_buy_pct": 3.0,
            "trailing_buy_pct": 1.5
        },
        "NVDA": {
            "fixed_shares": 30,
            "momentum_up_pct": 6.0,
            "trailing_sell_pct": 2.5,
            "pullback_buy_pct": 3.5,
            "trailing_buy_pct": 2.0
        }
    },
    "auto_shutdown_after_close": True,
    "shutdown_buffer_minutes": 2
}



# onfig_path = Path("conf/_bot4_config.yaml")
# cfg = TradingConfig.load_from_file(config_path)


