"""Dataset loader — reads ODMR dataset + manifest from disk."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from nv_sensor_sim.datasets.schema import DatasetManifest


class DatasetLoader:
    """Reads ODMR dataset and manifest from disk.

    Parameters
    ----------
    dataset_path : str or Path
        Path to the dataset directory containing manifest.json and data files.
    """

    def __init__(self, dataset_path: str | Path) -> None:
        self.dataset_path = Path(dataset_path)
        self._manifest: DatasetManifest | None = None

    def load_manifest(self) -> DatasetManifest:
        """Load and validate the dataset manifest.

        Returns
        -------
        DatasetManifest
            Loaded and validated manifest.
        """
        if self._manifest is None:
            manifest_path = self.dataset_path / "manifest.json"
            self._manifest = DatasetManifest.from_json(manifest_path)
        return self._manifest

    def load_split(
        self, split: str
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Load a data split (train/val/test).

        Parameters
        ----------
        split : str
            Split name: "train", "val", or "test".

        Returns
        -------
        tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
            (spectra, frequencies, labels, corruption_params, seeds).
        """
        # Try HDF5 first, then npz
        h5_path = self.dataset_path / "dataset.h5"
        npz_path = self.dataset_path / f"{split}.npz"

        if h5_path.exists():
            return self._load_h5_split(h5_path, split)
        elif npz_path.exists():
            return self._load_npz_split(npz_path)
        else:
            raise FileNotFoundError(
                f"No dataset file found for split '{split}' in {self.dataset_path}. "
                f"Expected either {h5_path} or {npz_path}."
            )

    def _load_h5_split(self, h5_path, split):
        """Load split from HDF5 file."""
        import h5py

        with h5py.File(h5_path, "r") as f:
            grp = f[split]
            spectra = grp["spectra"][:]
            frequencies = grp["frequencies"][:]
            labels = grp["labels"][:]
            corruption_params = grp["corruption_params"][:]
            seeds = grp["seeds"][:]
        return spectra, frequencies, labels, corruption_params, seeds

    def _load_npz_split(self, npz_path):
        """Load split from numpy compressed file."""
        data = np.load(npz_path)
        return (
            data["spectra"],
            data["frequencies"],
            data["labels"],
            data["corruption_params"],
            data["seeds"],
        )

    _SEQUENCE_KEYS = (
        "spectra",
        "frequencies",
        "B_true",
        "resonance_freqs",
        "line_axis",
        "line_transition",
        "collision_mask",
        "line_collision",
        "seeds",
    )

    def load_sequence_split(self, split: str) -> dict[str, np.ndarray]:
        """Load a time-series (sequence) split.

        Parameters
        ----------
        split : str
            Split name: "train", "val", or "test".

        Returns
        -------
        dict[str, np.ndarray]
            The sequence datasets (``spectra``, ``frequencies``, ``B_true``,
            ``resonance_freqs``, ``line_axis``, ``line_transition``,
            ``collision_mask``, ``line_collision``, ``seeds``) plus the top-level
            ``bias`` (3,) vector.
        """
        h5_path = self.dataset_path / "dataset.h5"
        npz_path = self.dataset_path / f"{split}.npz"

        if h5_path.exists():
            import h5py

            out: dict[str, np.ndarray] = {}
            with h5py.File(h5_path, "r") as f:
                grp = f[split]
                for key in self._SEQUENCE_KEYS:
                    out[key] = grp[key][:]
                out["bias"] = f["bias"][:]
            return out
        elif npz_path.exists():
            data = np.load(npz_path)
            return {key: data[key] for key in (*self._SEQUENCE_KEYS, "bias")}
        else:
            raise FileNotFoundError(
                f"No dataset file found for split '{split}' in {self.dataset_path}. "
                f"Expected either {h5_path} or {npz_path}."
            )
