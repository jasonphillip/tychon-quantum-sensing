"""Lock-bin sources for vector FCNN anchor ablations."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from odmr_edge_ml.vector.windowing import (
    NV_AXES_UNIT,
    NV_GYROMAGNETIC_RATIO_HZ_T,
    NV_ZERO_FIELD_SPLITTING_HZ,
)


def oracle_lock_bins(
    labels_T: np.ndarray, freq_grid: np.ndarray, axis_idx: int, sign: int,
) -> np.ndarray:
    """Linear-Zeeman expected dip bin for the oracle anchor."""
    proj = (labels_T @ NV_AXES_UNIT.T)[:, axis_idx]
    f_dip = NV_ZERO_FIELD_SPLITTING_HZ + float(sign) * NV_GYROMAGNETIC_RATIO_HZ_T * proj
    bin_spacing = float(freq_grid[1] - freq_grid[0])
    raw = (f_dip - freq_grid[0]) / bin_spacing
    return np.clip(np.rint(raw), 0, len(freq_grid) - 1).astype(np.int64)


def prior_lock_bins(
    B0_T: np.ndarray, freq_grid: np.ndarray, axis_idx: int, sign: int, n: int,
) -> np.ndarray:
    """Repeat the fixed bias-field anchor for each spectrum."""
    bias = np.asarray(B0_T, dtype=np.float64)
    if bias.shape != (3,) or not np.isfinite(bias).all():
        raise ValueError("B0_T must be a three-component vector in Tesla")
    return oracle_lock_bins(np.broadcast_to(bias, (n, 3)), freq_grid, axis_idx, sign)


def spectrum_lock_bins(
    spectra: np.ndarray,
    freq_grid: np.ndarray,
    prior_bins: np.ndarray,
    window_bins: int = 25,
    prominence: float = 0.02,
) -> np.ndarray:
    """Find the deepest local dip near each prior, or retain the prior."""
    spectra = np.asarray(spectra)
    prior_bins = np.asarray(prior_bins, dtype=np.int64)
    if spectra.ndim != 2 or spectra.shape[1] != len(freq_grid):
        raise ValueError("spectra must have shape (N, len(freq_grid))")
    if prior_bins.shape != (len(spectra),):
        raise ValueError("prior_bins must have shape (N,)")
    if window_bins < 0 or prominence < 0:
        raise ValueError("window_bins and prominence must be non-negative")
    out = prior_bins.copy()
    for i, prior in enumerate(prior_bins):
        lo = max(0, int(prior) - window_bins)
        hi = min(spectra.shape[1], int(prior) + window_bins + 1)
        window = spectra[i, lo:hi]
        if not len(window):
            continue
        candidate = int(np.argmin(window))
        if np.max(window) - window[candidate] >= prominence:
            out[i] = lo + candidate
    return out


def jitter_bins(
    bins: np.ndarray, sigma_bins: float, rng: np.random.Generator, n_bins: int,
) -> np.ndarray:
    """Add Gaussian bin noise, round, and clip to the frequency grid."""
    if sigma_bins < 0 or n_bins < 1:
        raise ValueError("sigma_bins must be non-negative and n_bins positive")
    noisy = np.asarray(bins, dtype=np.float64) + rng.normal(0.0, sigma_bins, size=np.shape(bins))
    return np.clip(np.rint(noisy), 0, n_bins - 1).astype(np.int64)


def bias_from_manifest(dataset: Path) -> np.ndarray:
    """Read a static lab-frame bias vector from the dataset's manifest."""
    manifest_path = dataset.parent / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read dataset bias from {manifest_path}") from exc
    if "bias" in manifest:
        bias = np.asarray(manifest["bias"], dtype=np.float64)
    elif "bias_B0_T" in manifest:
        direction = np.asarray(manifest.get("bias_direction_uvw", [0, 0, 1]), dtype=np.float64)
        if direction.shape != (3,) or not np.isfinite(direction).all() or np.linalg.norm(direction) == 0:
            raise ValueError(f"Invalid bias_direction_uvw in {manifest_path}")
        bias = float(manifest["bias_B0_T"]) * direction / np.linalg.norm(direction)
    else:
        raise ValueError(f"No bias field in {manifest_path}")
    if bias.shape != (3,) or not np.isfinite(bias).all():
        raise ValueError(f"Invalid bias vector in {manifest_path}")
    return bias
