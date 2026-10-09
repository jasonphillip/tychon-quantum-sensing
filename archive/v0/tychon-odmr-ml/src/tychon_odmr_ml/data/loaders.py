"""Dataset loader for Repo 1 HDF5 datasets.

Reads dataset.h5 directly (no Repo 1 import needed). Validates the
companion manifest.json via contracts, applies input normalization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import TensorDataset

from tychon_odmr_ml.data.contracts import validate_manifest_file

VALID_SPLITS = {"train", "val", "test"}


@dataclass
class OdmrDataset:
    """Container for one split of ODMR data."""

    spectra: np.ndarray  # (N, n_freq) — normalized if requested
    frequencies: np.ndarray  # (n_freq,) — Hz
    labels: np.ndarray  # (N, 3) — [Bx, By, Bz] in Tesla
    corruption_params: np.ndarray  # (N, 4) — [p1_ppm, T_K, b1_gradient, b_perp]
    seeds: np.ndarray  # (N,) — per-spectrum RNG seeds


class DatasetLoader:
    """Loads ODMR datasets produced by tychon-nv-sim.

    Parameters
    ----------
    dataset_dir : Path or str
        Directory containing dataset.h5 and manifest.json.
    normalize : bool
        If True, apply per-spectrum min-max normalization to [0, 1].
    """

    def __init__(self, dataset_dir: Path | str, normalize: bool = True) -> None:
        self._dir = Path(dataset_dir)
        self._normalize = normalize
        self._h5_path = self._dir / "dataset.h5"
        self._manifest_path = self._dir / "manifest.json"

        if not self._h5_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self._h5_path}")

        self._manifest_dict = validate_manifest_file(self._manifest_path)

    def load_split(self, split: str) -> OdmrDataset:
        """Load a train/val/test split from HDF5.

        Parameters
        ----------
        split : str
            One of "train", "val", "test".

        Returns
        -------
        OdmrDataset
            Loaded data container.
        """
        if split not in VALID_SPLITS:
            raise ValueError(f"Invalid split '{split}'. Must be one of {VALID_SPLITS}")

        with h5py.File(self._h5_path, "r") as f:
            g = f[split]
            spectra = g["spectra"][:]
            frequencies = g["frequencies"][:]
            labels = g["labels"][:]
            corruption_params = g["corruption_params"][:]
            seeds = g["seeds"][:]

        if self._normalize:
            spectra = self.normalize_spectra(spectra)

        return OdmrDataset(
            spectra=spectra,
            frequencies=frequencies,
            labels=labels,
            corruption_params=corruption_params,
            seeds=seeds,
        )

    def to_torch(self, split: str) -> TensorDataset:
        """Return a PyTorch TensorDataset for the given split.

        Returns
        -------
        TensorDataset
            (spectra_tensor, labels_tensor) as float32 tensors.
        """
        ds = self.load_split(split)
        spectra_t = torch.from_numpy(ds.spectra).float()
        labels_t = torch.from_numpy(ds.labels).float()
        return TensorDataset(spectra_t, labels_t)

    @staticmethod
    def normalize_spectra(spectra: np.ndarray) -> np.ndarray:
        """Per-spectrum min-max normalization to [0, 1].

        Raw PL signal is ~0.97-1.0 with ODMR dips pointing downward.
        This rescales each spectrum so features span the full [0, 1] range.

        Parameters
        ----------
        spectra : np.ndarray
            Shape (N, n_freq), raw PL signal.

        Returns
        -------
        np.ndarray
            Shape (N, n_freq), normalized to [0, 1] per spectrum.
        """
        mins = spectra.min(axis=1, keepdims=True)
        maxs = spectra.max(axis=1, keepdims=True)
        denom = maxs - mins
        # Avoid division by zero for flat spectra
        denom = np.where(denom == 0, 1.0, denom)
        return (spectra - mins) / denom

    @property
    def manifest(self) -> dict:
        """The validated manifest dictionary."""
        return self._manifest_dict

    @property
    def n_freq_points(self) -> int:
        """Number of frequency points per spectrum."""
        return int(self._manifest_dict["n_freq_points"])
