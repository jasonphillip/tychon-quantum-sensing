"""Configuration for tychon-odmr-ml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    """Top-level configuration."""

    dataset_dir: Path = field(
        default_factory=lambda: Path.home() / "projects/tychon-shared-data/golden"
    )
    n_freq_points: int = 100
    output_dim: int = 3  # [Bx, By, Bz]
    device: str = "cpu"

    def __post_init__(self) -> None:
        self.dataset_dir = Path(self.dataset_dir)


def load_config(path: Path | None = None) -> Config:
    """Load config from YAML file. Falls back to defaults if path is None or missing."""
    if path is None or not Path(path).exists():
        return Config()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return Config(**{k: v for k, v in raw.items() if k in Config.__dataclass_fields__})
