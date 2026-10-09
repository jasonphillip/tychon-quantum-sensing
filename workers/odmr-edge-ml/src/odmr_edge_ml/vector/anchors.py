"""Lock-bin sources for vector FCNN anchor ablations."""

from __future__ import annotations

import json
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks, savgol_filter

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


@lru_cache(maxsize=4)
def _coarse_candidates(
    grid_bytes: bytes, grid_size: int, n_dirs: int, mags: tuple[float, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Cache candidate fields and their eight line bins for one grid."""
    freq_grid = np.frombuffer(grid_bytes, dtype=np.float64, count=grid_size)
    indices = np.arange(n_dirs, dtype=np.float64)
    z = 1.0 - (indices + 0.5) / n_dirs
    theta = indices * np.pi * (3.0 - np.sqrt(5.0))
    radial = np.sqrt(1.0 - z * z)
    directions = np.stack((radial * np.cos(theta), radial * np.sin(theta), z), axis=1)
    fields = (directions[:, None, :] * np.asarray(mags)[None, :, None]).reshape(-1, 3)
    bins = np.stack([
        oracle_lock_bins(fields, freq_grid, axis, sign)
        for axis in range(4) for sign in (+1, -1)
    ], axis=1)
    return fields, bins


def coarse_fit_field(
    spectra: np.ndarray,
    freq_grid: np.ndarray,
    *,
    n_dirs: int = 2000,
    mags_T: np.ndarray | None = None,
    prominence: float = 0.02,
    method: str = "matched",
    fwhm_bins: float = 6.0,
) -> np.ndarray:
    """Fit a field by matched Lorentzian templates or dip-bin Chamfer score."""
    spectra = np.asarray(spectra, dtype=np.float64)
    freq_grid = np.asarray(freq_grid, dtype=np.float64)
    mags = np.asarray(np.linspace(0.5e-3, 5e-3, 19) if mags_T is None else mags_T,
                      dtype=np.float64)
    if spectra.ndim != 2 or freq_grid.ndim != 1 or freq_grid.size < 2 or spectra.shape[1] != freq_grid.size:
        raise ValueError("spectra must have shape (N, len(freq_grid)); grid needs two bins")
    if not isinstance(n_dirs, (int, np.integer)) or n_dirs < 1:
        raise ValueError("n_dirs must be a positive integer")
    if mags.ndim != 1 or mags.size == 0 or not np.isfinite(mags).all() or np.any(mags < 0):
        raise ValueError("mags_T must be a nonempty array of non-negative finite magnitudes")
    if not np.isfinite(spectra).all() or not np.isfinite(freq_grid).all() or not np.all(np.diff(freq_grid) > 0):
        raise ValueError("spectra and increasing freq_grid must be finite")
    if prominence < 0 or not np.isfinite(prominence):
        raise ValueError("prominence must be non-negative and finite")
    if method not in ("matched", "chamfer"):
        raise ValueError("method must be 'matched' or 'chamfer'")
    if not np.isfinite(fwhm_bins) or fwhm_bins <= 0:
        raise ValueError("fwhm_bins must be positive and finite")
    fields, predicted = _coarse_candidates(freq_grid.tobytes(), freq_grid.size,
                                            int(n_dirs), tuple(mags.tolist()))
    if method == "matched":
        # Build one contiguous candidate matrix; spectrum batches use BLAS matrix products.
        n_bins = freq_grid.size
        templates = np.empty((len(fields), n_bins), dtype=np.float32)
        sample_bins = np.arange(n_bins, dtype=np.float32)[None, :]
        half_width = np.float32(fwhm_bins / 2.0)
        for start in range(0, len(fields), 2048):
            stop = min(start + 2048, len(fields))
            block = templates[start:stop]
            block.fill(0)
            for line in range(8):
                offset = (sample_bins - predicted[start:stop, line, None]) / half_width
                block += 1.0 / (1.0 + offset * offset)
            block -= block.mean(axis=1, keepdims=True)
            block /= np.linalg.norm(block, axis=1, keepdims=True)

        fitted = np.empty((len(spectra), 3), dtype=np.float64)
        top_count = max(1, int(np.ceil(n_bins * 0.2)))
        for start in range(0, len(spectra), 64):
            stop = min(start + 64, len(spectra))
            batch = spectra[start:stop].astype(np.float32)
            baseline = np.median(np.partition(batch, -top_count, axis=1)[:, -top_count:], axis=1)
            if np.any(baseline == 0):
                raise ValueError("matched filter requires a nonzero spectrum baseline")
            dips = (baseline[:, None] - batch) / baseline[:, None]
            dips -= dips.mean(axis=1, keepdims=True)
            fitted[start:stop] = fields[np.argmax(dips @ templates.T, axis=1)]
        return fitted

    fitted = np.empty((len(spectra), 3), dtype=np.float64)
    zero_nearest = int(np.argmin(np.linalg.norm(fields, axis=1)))
    top_count = max(1, int(np.ceil(freq_grid.size * 0.2)))
    for row, spectrum in enumerate(spectra):
        baseline = float(np.median(np.partition(spectrum, -top_count)[-top_count:]))
        dips = np.empty(0, dtype=np.int64) if baseline == 0 else find_peaks(
            (baseline - spectrum) / baseline, prominence=prominence,
        )[0]
        if dips.size == 0:
            warnings.warn(f"No dips found in spectrum {row}; using nearest-zero candidate",
                          RuntimeWarning, stacklevel=2)
            fitted[row] = fields[zero_nearest]
            continue
        best_score = np.inf
        best_index = 0
        for start in range(0, len(fields), 2048):
            line_bins = predicted[start:start + 2048]
            distances = np.abs(line_bins[:, :, None] - dips[None, None, :])
            scores = distances.min(axis=2).mean(axis=1) + distances.min(axis=1).mean(axis=1)
            local_index = int(np.argmin(scores))
            if scores[local_index] < best_score:
                best_score = float(scores[local_index])
                best_index = start + local_index
        fitted[row] = fields[best_index]
    return fitted


def coarse_fit_lock_bins(
    B_hat: np.ndarray, freq_grid: np.ndarray, axis_idx: int, sign: int,
) -> np.ndarray:
    """Return the selected field's expected line bin for one channel."""
    return oracle_lock_bins(B_hat, freq_grid, axis_idx, sign)


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
    prominence: float = 0.002,
    smooth: bool = True,
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
        if hi <= lo:
            continue
        baseline = float(np.max(spectra[i]))
        if baseline == 0:
            continue
        dips = (baseline - spectra[i]) / baseline
        if smooth and len(dips) >= 9:
            dips = savgol_filter(dips, 9, 2)
        peaks, _ = find_peaks(dips[lo:hi], prominence=prominence)
        if peaks.size:
            out[i] = lo + int(peaks[np.argmax(dips[lo + peaks])])
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
