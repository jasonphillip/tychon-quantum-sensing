"""Dataset writer — writes ODMR spectra + manifest to disk.

Supports HDF5 (.h5) and numpy compressed (.npz) output formats.
Manifest is always written as a JSON sidecar file.

HDF5 layout per split:
    /{split}/spectra          — shape (N, n_freq_points)
    /{split}/frequencies      — shape (n_freq_points,)
    /{split}/labels           — shape (N, 3) (B-field vector ground truth)
    /{split}/corruption_params — shape (N, 4 or 5):
        deterministic: (p1, T, b1_grad, b_perp)
        stochastic:    (p1, T, b1_grad, b_perp, mw_power_scale)
    /{split}/seeds            — shape (N,) (per-spectrum seeds)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from nv_sensor_sim.datasets.schema import DatasetManifest


class DatasetWriter:
    """Writes ODMR spectra and manifest to disk.

    Parameters
    ----------
    output_dir : str or Path
        Output directory path.
    format : str
        Output format: "h5" for HDF5 or "npz" for numpy compressed.
    """

    def __init__(self, output_dir: str | Path, format: str = "h5") -> None:
        self.output_dir = Path(output_dir)
        self.format = format
        self._h5_file = None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_spectra(
        self,
        spectra: np.ndarray,
        frequencies: np.ndarray,
        labels: np.ndarray,
        corruption_params: np.ndarray,
        seeds: np.ndarray,
        split: str,
    ) -> None:
        """Write spectra array for a split (train/val/test).

        Parameters
        ----------
        spectra : np.ndarray
            ODMR spectra, shape (N, n_freq_points).
        frequencies : np.ndarray
            Frequency array, shape (n_freq_points,).
        labels : np.ndarray
            Ground truth B-field vectors, shape (N, 3).
        corruption_params : np.ndarray
            Corruption parameters, shape (N, 4) or (N, 5). See module docstring.
        seeds : np.ndarray
            Per-spectrum random seeds, shape (N,).
        split : str
            Split name: "train", "val", or "test".
        """
        if self.format == "h5":
            self._write_h5(spectra, frequencies, labels, corruption_params, seeds, split)
        elif self.format == "npz":
            self._write_npz(spectra, frequencies, labels, corruption_params, seeds, split)
        else:
            raise ValueError(f"Unknown format: {self.format}. Use 'h5' or 'npz'.")

    def _write_h5(self, spectra, frequencies, labels, corruption_params, seeds, split):
        """Write to HDF5 format."""
        import h5py

        h5_path = self.output_dir / "dataset.h5"
        with h5py.File(h5_path, "a") as f:
            grp = f.require_group(split)
            # Overwrite if exists
            for key in ("spectra", "frequencies", "labels", "corruption_params", "seeds"):
                if key in grp:
                    del grp[key]
            grp.create_dataset("spectra", data=spectra)
            grp.create_dataset("frequencies", data=frequencies)
            grp.create_dataset("labels", data=labels)
            grp.create_dataset("corruption_params", data=corruption_params)
            grp.create_dataset("seeds", data=seeds)

    def _write_npz(self, spectra, frequencies, labels, corruption_params, seeds, split):
        """Write to numpy compressed format."""
        npz_path = self.output_dir / f"{split}.npz"
        np.savez_compressed(
            npz_path,
            spectra=spectra,
            frequencies=frequencies,
            labels=labels,
            corruption_params=corruption_params,
            seeds=seeds,
        )

    def write_manifest(self, manifest: DatasetManifest) -> None:
        """Write manifest as JSON sidecar file.

        Parameters
        ----------
        manifest : DatasetManifest
            Dataset manifest to write.
        """
        manifest_path = self.output_dir / "manifest.json"
        manifest.to_json(manifest_path)

    def finalize(self) -> str:
        """Finalize writing and return output directory path.

        Returns
        -------
        str
            Absolute path to the output directory.
        """
        return str(self.output_dir.resolve())
