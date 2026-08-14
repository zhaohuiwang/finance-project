"""Configuration loader for Sector Rotation Monitor."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml


def get_project_root() -> Path:
    """Return the project root directory (parent of src/)."""
    return Path(__file__).resolve().parent.parent


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """
    Load YAML configuration.

    Parameters
    ----------
    config_path : optional path to YAML file.
        Defaults to config/sectors.yaml relative to project root.
    """
    root = get_project_root()
    if config_path is None:
        config_path = root / "config" / "sectors.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Resolve relative paths
    data_dir = root / cfg.get("data", {}).get("cache_dir", "data")
    out_dir = root / cfg.get("output", {}).get("dir", "outputs")
    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg["_resolved"] = {
        "project_root": str(root),
        "data_dir": str(data_dir),
        "output_dir": str(out_dir),
        "config_path": str(config_path),
    }
    return cfg


def get_sector_tickers(cfg: Dict[str, Any]) -> List[str]:
    """Return list of broad sector ETF tickers."""
    return list(cfg.get("sectors", {}).keys())


def get_industry_tickers(cfg: Dict[str, Any]) -> List[str]:
    """Return list of industry / thematic ETF tickers."""
    if not cfg.get("data", {}).get("include_industries", True):
        return []
    return list(cfg.get("industries", {}).keys())


def get_equity_meta(cfg: Dict[str, Any]) -> Dict[str, Dict]:
    """Merged metadata for sectors + industries."""
    meta = dict(cfg.get("sectors", {}))
    if cfg.get("data", {}).get("include_industries", True):
        meta.update(cfg.get("industries", {}))
    return meta


def get_all_tickers(cfg: Dict[str, Any]) -> List[str]:
    """Return sector + industry tickers + benchmark (deduped, ordered)."""
    tickers: List[str] = []
    for t in get_sector_tickers(cfg) + get_industry_tickers(cfg):
        if t not in tickers:
            tickers.append(t)
    bench = cfg.get("benchmark", "SPY")
    if bench not in tickers:
        tickers.append(bench)
    return tickers
