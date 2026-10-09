"""Lightweight YAML config loading (dataclasses + ``yaml.safe_load``; no hydra/pydantic).

Mirrors ``odmr_edge_ml.config``: a dataclass per concern + a generic :func:`load_config` that
filters unknown YAML keys. Two concerns here — the dataset/scenario parameters
(:class:`ScenarioConfig`) and the model architecture (the
:class:`~odmr_vector_tracking.tracking.learned.LearnedTrackerConfig`, re-exported).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import TypeVar

import yaml

from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig

T = TypeVar("T")


@dataclass
class ScenarioConfig:
    """Dataset / field-trajectory scenario parameters (mirror the v1 contract knobs)."""

    dataset_dir: Path = Path("./data/fixture")
    n_timesteps: int = 200
    n_freq: int = 400
    n_lines: int = 8
    linewidth_Hz: float = 4.0e6
    collision_threshold_linewidths: float = 1.5
    bias_B0_T: float = 8.0e-3
    bias_direction_uvw: tuple[float, float, float] = (0.2, 0.3, 0.93)
    dt_s: float = 1.0e-3

    def __post_init__(self) -> None:
        self.dataset_dir = Path(self.dataset_dir)
        b = list(self.bias_direction_uvw)  # YAML gives a list; normalize to a 3-tuple
        self.bias_direction_uvw = (float(b[0]), float(b[1]), float(b[2]))


def load_config(path: Path | str | None, cls: type[T]) -> T:
    """Load ``path`` (YAML) into dataclass ``cls``; **unknown keys are an error**.

    Strict validation catches silent config drift (a renamed/removed field left behind in a
    YAML would otherwise be dropped without a trace). Returns ``cls()`` defaults when ``path``
    is ``None`` or missing, so a config file stays optional. ``int``/``float`` fields are
    coerced from strings, which also neutralizes PyYAML's YAML-1.1 gotcha (bare ``4.0e6``
    parses as a str).
    """
    field_types = {f.name: f.type for f in fields(cls)}  # type: ignore[arg-type]
    if path is None or not Path(path).exists():
        return cls()
    with open(path) as fh:
        raw = yaml.safe_load(fh) or {}

    unknown = sorted(set(raw) - set(field_types))
    if unknown:
        raise ValueError(
            f"{path}: unknown key(s) {unknown} for {cls.__name__} "
            f"(valid: {sorted(field_types)})"
        )

    coerced: dict[str, object] = {}
    for key, value in raw.items():
        # Annotations are strings here (`from __future__ import annotations`).
        ann = field_types[key]
        if ann == "float" and isinstance(value, str):
            value = float(value)
        elif ann == "int" and isinstance(value, str):
            value = int(value)
        coerced[key] = value
    return cls(**coerced)


def load_scenario(path: Path | str | None = None) -> ScenarioConfig:
    """Load a :class:`ScenarioConfig` from YAML (or defaults)."""
    return load_config(path, ScenarioConfig)


def load_model(path: Path | str | None = None) -> LearnedTrackerConfig:
    """Load a :class:`LearnedTrackerConfig` from YAML (or defaults)."""
    return load_config(path, LearnedTrackerConfig)
