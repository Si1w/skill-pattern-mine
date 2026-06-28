"""Shared paths and config helpers for the mining stage (configs/mine.yaml)."""

from pathlib import Path

import yaml

# Shared paths. All mining outputs live under data/mine/.
CONFIG_PATH = Path("configs/mine.yaml")
DATA_DIR = Path("data/mine")


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Load the mining config from YAML."""
    with open(config_path) as f:
        return yaml.safe_load(f) or {}
