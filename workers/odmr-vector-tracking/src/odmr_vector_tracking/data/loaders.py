"""Loader for v1 time-series ODMR tracker datasets.

Reads ``dataset.h5`` directly (no simulator import needed) and validates the companion
``manifest.json`` + dataset against the v1 contract on construction. Mirrors
``odmr_edge_ml.data.loaders.DatasetLoader``, adapted to the temporal sequence schema
(``(N, T, F)`` spectra + per-line association labels + collision masks).

This is the swap point for sim→fixture: the synthetic fixtures and the real ``nv-sensor-sim``
output share the v1 contract, so the *same* loader reads both — only the producer changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset

from odmr_vector_tracking.data.contract import VALID_SPLITS, validate_dataset_dir


@dataclass
class SequenceDataset:
    """One split of time-series ODMR tracker data (numpy arrays, contract dtypes).

    N = sequences, T = frames, F = MW-frequency points, L = resonances.
    """

    spectra: np.ndarray          # (N, T, F) float32 — normalized PL time-series
    frequencies: np.ndarray      # (F,)      float32 — MW axis, Hz
    B_true: np.ndarray           # (N, T, 3) float32 — lab-frame B, Tesla
    resonance_freqs: np.ndarray  # (N, T, L) float32 — line centers, Hz
    line_axis: np.ndarray        # (N, T, L) int8    — NV axis id 0..3 (assoc. ground truth)
    line_transition: np.ndarray  # (N, T, L) int8    — 0=ms0→−1, 1=ms0→+1
    collision_mask: np.ndarray   # (N, T)    bool    — any two lines within k·Γ this frame
    line_collision: np.ndarray   # (N, T, L) bool    — per-line collision flag
    bias: np.ndarray             # (3,)      float32 — static bias vector, Tesla
    seeds: np.ndarray            # (N,)      int64   — per-sequence RNG seed

    @property
    def n_sequences(self) -> int:
        return int(self.spectra.shape[0])


class _SequenceTorchDataset(Dataset):
    """Per-sequence ``torch`` view: ``__getitem__(i)`` returns a dict of tensors for one seq."""

    def __init__(self, ds: SequenceDataset) -> None:
        self._spectra = torch.from_numpy(np.ascontiguousarray(ds.spectra)).float()
        self._b_true = torch.from_numpy(np.ascontiguousarray(ds.B_true)).float()
        self._res = torch.from_numpy(np.ascontiguousarray(ds.resonance_freqs)).float()
        self._axis = torch.from_numpy(np.ascontiguousarray(ds.line_axis)).long()
        self._trans = torch.from_numpy(np.ascontiguousarray(ds.line_transition)).long()
        self._coll = torch.from_numpy(np.ascontiguousarray(ds.collision_mask)).bool()
        self._lcoll = torch.from_numpy(np.ascontiguousarray(ds.line_collision)).bool()
        self._seeds = torch.from_numpy(np.ascontiguousarray(ds.seeds)).long()
        # Per-dataset (not per-item) tensors, exposed as attributes.
        self.frequencies = torch.from_numpy(np.ascontiguousarray(ds.frequencies)).float()
        self.bias = torch.from_numpy(np.ascontiguousarray(ds.bias)).float()

    def __len__(self) -> int:
        return int(self._spectra.shape[0])

    def __getitem__(self, i: int) -> dict[str, torch.Tensor]:
        return {
            "spectra": self._spectra[i],            # (T, F)
            "B_true": self._b_true[i],              # (T, 3)
            "resonance_freqs": self._res[i],        # (T, L)
            "line_axis": self._axis[i],             # (T, L)
            "line_transition": self._trans[i],      # (T, L)
            "collision_mask": self._coll[i],        # (T,)
            "line_collision": self._lcoll[i],       # (T, L)
            "seed": self._seeds[i],                 # scalar
        }


class SequenceDatasetLoader:
    """Loads v1 time-series ODMR datasets produced upstream (or by the synthetic fixtures).

    Parameters
    ----------
    dataset_dir : Path or str
        Directory containing ``dataset.h5`` and ``manifest.json``.
    normalize : bool
        If True, apply per-(sequence, frame) min-max normalization of each spectrum to [0, 1].
        Default False — the contract spectra are already normalized (~1 off-resonance).
    """

    def __init__(self, dataset_dir: Path | str, normalize: bool = False) -> None:
        self._dir = Path(dataset_dir)
        self._normalize = normalize
        self._h5_path = self._dir / "dataset.h5"
        # Validates manifest + HDF5 against the v1 contract (raises on violation).
        self._manifest = validate_dataset_dir(self._dir)

    def load_split(self, split: str) -> SequenceDataset:
        """Load a train/val/test split from HDF5 into a :class:`SequenceDataset`."""
        if split not in VALID_SPLITS:
            raise ValueError(f"Invalid split '{split}'. Must be one of {VALID_SPLITS}")

        with h5py.File(self._h5_path, "r") as f:
            if split not in f:
                raise KeyError(f"Split '{split}' not present in {self._h5_path.name}")
            g = f[split]
            assert isinstance(g, h5py.Group)

            def _arr(name: str) -> np.ndarray:
                obj = g[name]
                assert isinstance(obj, h5py.Dataset)
                return np.asarray(obj[()])

            # bias: authoritative v1 is top-level /bias; fall back to per-split for back-compat.
            bias_obj = f["bias"] if "bias" in f else g["bias"]
            assert isinstance(bias_obj, h5py.Dataset)
            bias = np.asarray(bias_obj[()]).astype(np.float32)

            spectra = _arr("spectra").astype(np.float32)
            ds = SequenceDataset(
                spectra=self.normalize_spectra(spectra) if self._normalize else spectra,
                frequencies=_arr("frequencies").astype(np.float32),
                B_true=_arr("B_true").astype(np.float32),
                resonance_freqs=_arr("resonance_freqs").astype(np.float32),
                line_axis=_arr("line_axis").astype(np.int8),
                line_transition=_arr("line_transition").astype(np.int8),
                collision_mask=_arr("collision_mask").astype(bool),
                line_collision=_arr("line_collision").astype(bool),
                bias=bias,
                seeds=_arr("seeds").astype(np.int64),
            )
        return ds

    def to_torch(self, split: str) -> _SequenceTorchDataset:
        """Return a per-sequence ``torch`` dataset for ``split`` (dict items, batch over N)."""
        return _SequenceTorchDataset(self.load_split(split))

    @staticmethod
    def normalize_spectra(spectra: np.ndarray) -> np.ndarray:
        """Per-(sequence, frame) min-max normalization of each spectrum to [0, 1].

        ``spectra`` has shape ``(N, T, F)``; normalization is over the last (frequency) axis,
        with a zero-denominator guard for flat frames.
        """
        mins = spectra.min(axis=-1, keepdims=True)
        maxs = spectra.max(axis=-1, keepdims=True)
        denom = np.where(maxs - mins == 0, 1.0, maxs - mins)
        return ((spectra - mins) / denom).astype(np.float32)

    @property
    def manifest(self) -> dict:
        """The validated manifest dictionary."""
        return self._manifest

    @property
    def n_timesteps(self) -> int:
        return int(self._manifest["n_timesteps"])

    @property
    def n_lines(self) -> int:
        return int(self._manifest["n_lines"])

    @property
    def n_freq_points(self) -> int:
        return int(self._manifest["n_freq_points"])

    @property
    def bias(self) -> np.ndarray:
        """Static bias vector (3,), Tesla, ``= bias_B0_T · normalize(bias_direction_uvw)``.

        The upstream stores the raw (un-normalized) ``[uvw]`` direction, so this normalizes it;
        the result equals the authoritative top-level ``/bias`` dataset
        (:attr:`SequenceDataset.bias`).
        """
        b0 = float(self._manifest["bias_B0_T"])
        bdir = np.asarray(self._manifest["bias_direction_uvw"], dtype=np.float64)
        norm = np.linalg.norm(bdir)
        unit = bdir / norm if norm > 0 else bdir
        return (b0 * unit).astype(np.float32)
