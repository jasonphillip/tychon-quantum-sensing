"""Dataset writer — writes ODMR spectra + manifest to disk.

Supports HDF5 (.h5) and numpy compressed (.npz) output formats.
Manifest is always written as a JSON sidecar file.

HDF5 layout per split (static single-frame datasets):
    /{split}/spectra          — shape (N, n_freq_points)
    /{split}/frequencies      — shape (n_freq_points,)
    /{split}/labels           — shape (N, 3) (B-field vector ground truth)
    /{split}/corruption_params — shape (N, 4 or 5):
        deterministic: (p1, T, b1_grad, b_perp)
        stochastic:    (p1, T, b1_grad, b_perp, mw_power_scale)
    /{split}/seeds            — shape (N,) (per-spectrum seeds)

HDF5 layout per split (time-series / sequence datasets, written by
``write_sequences``); see docs/dataset-contract.md:
    /{split}/spectra          — float32 (N, T, F) normalized PL time-series
    /{split}/frequencies      — float32 (F,) MW frequency axis (Hz)
    /{split}/B_true           — float32 (N, T, 3) lab-frame B (Tesla) per frame
    /{split}/resonance_freqs  — float32 (N, T, L) line centers (Hz) per frame
    /{split}/line_axis        — int8    (N, T, L) NV axis id 0-3
    /{split}/line_transition  — int8    (N, T, L) 0 = ms0->-1, 1 = ms0->+1
    /{split}/collision_mask   — bool    (N, T) any two lines within k*Gamma
    /{split}/line_collision   — bool    (N, T, L) which lines are within k*Gamma
    /{split}/seeds            — int64   (N,) per-sequence seeds
    /bias                     — float32 (3,) static bias vector (Tesla), top-level
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

    def write_sequences(
        self,
        *,
        spectra: np.ndarray,
        frequencies: np.ndarray,
        B_true: np.ndarray,
        resonance_freqs: np.ndarray,
        line_axis: np.ndarray,
        line_transition: np.ndarray,
        collision_mask: np.ndarray,
        line_collision: np.ndarray,
        bias: np.ndarray,
        seeds: np.ndarray,
        split: str,
    ) -> None:
        """Write a time-series (sequence) split to disk.

        Arrays are cast to the dataset-contract dtypes (float32 / int8 / bool /
        int64) at write time. The static bias is written once at the top level.

        Parameters
        ----------
        spectra : np.ndarray
            Normalized PL time-series, shape (N, T, F).
        frequencies : np.ndarray
            MW frequency axis (Hz), shape (F,).
        B_true : np.ndarray
            Ground-truth lab-frame B per frame (Tesla), shape (N, T, 3).
        resonance_freqs : np.ndarray
            Line centers (Hz) per frame, shape (N, T, L).
        line_axis : np.ndarray
            NV axis id per line, shape (N, T, L).
        line_transition : np.ndarray
            Transition id per line, shape (N, T, L).
        collision_mask : np.ndarray
            Per-frame collision flag, shape (N, T).
        line_collision : np.ndarray
            Per-line collision flag, shape (N, T, L).
        bias : np.ndarray
            Static bias vector (Tesla), shape (3,).
        seeds : np.ndarray
            Per-sequence seeds, shape (N,).
        split : str
            Split name: "train", "val", or "test".
        """
        if self.format == "h5":
            self._write_sequences_h5(
                spectra, frequencies, B_true, resonance_freqs, line_axis,
                line_transition, collision_mask, line_collision, bias, seeds, split,
            )
        elif self.format == "npz":
            self._write_sequences_npz(
                spectra, frequencies, B_true, resonance_freqs, line_axis,
                line_transition, collision_mask, line_collision, bias, seeds, split,
            )
        else:
            raise ValueError(f"Unknown format: {self.format}. Use 'h5' or 'npz'.")

    def _write_sequences_h5(
        self, spectra, frequencies, B_true, resonance_freqs, line_axis,
        line_transition, collision_mask, line_collision, bias, seeds, split,
    ):
        """Write a sequence split to HDF5 format."""
        import h5py

        h5_path = self.output_dir / "dataset.h5"
        with h5py.File(h5_path, "a") as f:
            grp = f.require_group(split)
            keys = (
                "spectra", "frequencies", "B_true", "resonance_freqs", "line_axis",
                "line_transition", "collision_mask", "line_collision", "seeds",
            )
            for key in keys:
                if key in grp:
                    del grp[key]
            grp.create_dataset("spectra", data=np.asarray(spectra, dtype=np.float32))
            grp.create_dataset("frequencies", data=np.asarray(frequencies, dtype=np.float32))
            grp.create_dataset("B_true", data=np.asarray(B_true, dtype=np.float32))
            grp.create_dataset(
                "resonance_freqs", data=np.asarray(resonance_freqs, dtype=np.float32)
            )
            grp.create_dataset("line_axis", data=np.asarray(line_axis, dtype=np.int8))
            grp.create_dataset(
                "line_transition", data=np.asarray(line_transition, dtype=np.int8)
            )
            grp.create_dataset(
                "collision_mask", data=np.asarray(collision_mask, dtype=bool)
            )
            grp.create_dataset(
                "line_collision", data=np.asarray(line_collision, dtype=bool)
            )
            grp.create_dataset("seeds", data=np.asarray(seeds, dtype=np.int64))
            # Static bias is shared across all splits — write once at top level.
            if "bias" in f:
                del f["bias"]
            f.create_dataset("bias", data=np.asarray(bias, dtype=np.float32))

    def _write_sequences_npz(
        self, spectra, frequencies, B_true, resonance_freqs, line_axis,
        line_transition, collision_mask, line_collision, bias, seeds, split,
    ):
        """Write a sequence split to numpy compressed format."""
        npz_path = self.output_dir / f"{split}.npz"
        np.savez_compressed(
            npz_path,
            spectra=np.asarray(spectra, dtype=np.float32),
            frequencies=np.asarray(frequencies, dtype=np.float32),
            B_true=np.asarray(B_true, dtype=np.float32),
            resonance_freqs=np.asarray(resonance_freqs, dtype=np.float32),
            line_axis=np.asarray(line_axis, dtype=np.int8),
            line_transition=np.asarray(line_transition, dtype=np.int8),
            collision_mask=np.asarray(collision_mask, dtype=bool),
            line_collision=np.asarray(line_collision, dtype=bool),
            bias=np.asarray(bias, dtype=np.float32),
            seeds=np.asarray(seeds, dtype=np.int64),
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
