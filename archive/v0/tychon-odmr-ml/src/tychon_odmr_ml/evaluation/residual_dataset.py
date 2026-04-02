"""Residual dataset: 2-channel input (spectrum + PID anchor) with scalar ΔB target.

Generates PID estimates for the production dataset and creates training labels
for the scalar residual correction task: ΔB = |B_true| - B_PID.
"""

from __future__ import annotations

import logging
from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset

from tychon_odmr_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID

log = logging.getLogger(__name__)


def generate_pid_labels(
    data_dir: Path,
    output_path: Path | None = None,
) -> Path:
    """Run PID on all splits and save results as a sidecar npz file.

    Parameters
    ----------
    data_dir : Path
        Directory containing dataset.h5 with raw spectra.
    output_path : Path or None
        Where to save. Default: data_dir / "pid_residuals.npz".

    Returns
    -------
    Path
        Path to the saved npz file.
    """
    if output_path is None:
        output_path = data_dir / "pid_residuals.npz"

    h5_path = data_dir / "dataset.h5"
    arrays: dict[str, np.ndarray] = {}

    with h5py.File(h5_path, "r") as f:
        frequencies = f["train/frequencies"][:]
        pid = DerivativeZeroCrossingPID(frequencies)

        for split in ("train", "val", "test"):
            spectra = f[split]["spectra"][:]
            labels_T = f[split]["labels"][:]
            b_mag_uT = np.linalg.norm(labels_T * 1e6, axis=1)

            results = pid.estimate_batch(spectra)
            b_pid = np.array([r.b_mag_uT for r in results])
            lock_bins = np.array([r.lock_bin for r in results])
            delta_b = b_mag_uT - b_pid

            arrays[f"{split}_b_pid_uT"] = b_pid
            arrays[f"{split}_lock_bins"] = lock_bins
            arrays[f"{split}_delta_b_uT"] = delta_b
            arrays[f"{split}_b_mag_uT"] = b_mag_uT

            log.info(
                "%s: PID MAE=%.2f uT, residual range=[%.1f, %.1f] uT",
                split,
                np.abs(delta_b).mean(),
                delta_b.min(),
                delta_b.max(),
            )

    np.savez(output_path, **arrays)
    log.info("Saved PID labels to %s", output_path)
    return output_path


def _normalize_symmetric(spectra: np.ndarray) -> np.ndarray:
    """Per-spectrum normalization to [-1, 1]."""
    mins = spectra.min(axis=1, keepdims=True)
    maxs = spectra.max(axis=1, keepdims=True)
    denom = maxs - mins
    denom = np.where(denom == 0, 1.0, denom)
    return 2.0 * (spectra - mins) / denom - 1.0


def _make_anchor(lock_bins: np.ndarray, n_freq: int, sigma: float = 1.5) -> np.ndarray:
    """Create PID anchor channel: Gaussian pulse at each lock-point bin.

    Parameters
    ----------
    lock_bins : np.ndarray
        Shape (N,) — bin index of PID lock point per spectrum.
    n_freq : int
        Number of frequency bins.
    sigma : float
        Gaussian width in bins.

    Returns
    -------
    np.ndarray
        Shape (N, n_freq) — anchor channel.
    """
    bins = np.arange(n_freq)[None, :]  # (1, n_freq)
    centers = lock_bins[:, None]  # (N, 1)
    return np.exp(-0.5 * ((bins - centers) / sigma) ** 2)


class ResidualDataset(Dataset):
    """2-channel dataset for scalar PID residual correction.

    Returns 200-dim input: spectrum (100) || PID anchor (100).
    Label is scalar ΔB = |B_true| - B_PID in µT.

    Parameters
    ----------
    data_dir : Path
        Directory with dataset.h5 and pid_residuals.npz.
    split : str
        "train", "val", or "test".
    sigma : float
        Gaussian anchor width in bins.
    """

    def __init__(
        self,
        data_dir: Path,
        split: str = "train",
        sigma: float = 1.5,
    ) -> None:
        npz_path = data_dir / "pid_residuals.npz"
        if not npz_path.exists():
            log.info("PID labels not found, generating...")
            generate_pid_labels(data_dir)

        npz = np.load(npz_path)
        lock_bins = npz[f"{split}_lock_bins"]
        delta_b = npz[f"{split}_delta_b_uT"]

        with h5py.File(data_dir / "dataset.h5", "r") as f:
            spectra_raw = f[split]["spectra"][:]
            corruption_params = f[split]["corruption_params"][:]

        # Channel 0: spectrum normalized to [-1, 1]
        spectra_norm = _normalize_symmetric(spectra_raw)
        # Channel 1: PID anchor Gaussian
        anchor = _make_anchor(lock_bins, spectra_raw.shape[1], sigma=sigma)

        # Concatenate: (N, 200)
        combined = np.concatenate([spectra_norm, anchor], axis=1)

        self.spectra = torch.from_numpy(combined).float()
        self.labels = torch.from_numpy(delta_b[:, None]).float()  # (N, 1)
        self.corruption_params = torch.from_numpy(corruption_params).float()

    def __len__(self) -> int:
        return len(self.spectra)

    def __getitem__(self, idx: int) -> dict:
        return {
            "spectra": self.spectra[idx],
            "b_field_uT": self.labels[idx],
            "meta": {"corruption_params": self.corruption_params[idx]},
        }
