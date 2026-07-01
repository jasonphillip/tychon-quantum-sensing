#!/usr/bin/env python3
"""Waterfall plot of one sequence from a time-series ODMR dataset.

Renders the (T, F) spectrum image with the per-line resonance labels overlaid
(colored by NV axis) and collision frames marked, e.g.:

    python scripts/plot_sequence_waterfall.py \
        artifacts/datasets/sequence_train_v1 \
        --split train --index 0 \
        --output artifacts/datasets/sequence_train_v1/waterfall_sample.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_AXIS_COLORS = ("cyan", "springgreen", "gold", "deeppink")


def _read(group: h5py.Group, name: str) -> h5py.Dataset:
    """Fetch an HDF5 dataset (narrows the h5py union type)."""
    ds = group[name]
    assert isinstance(ds, h5py.Dataset)
    return ds


def plot_sequence_waterfall(
    dataset_dir: Path,
    split: str = "train",
    index: int = 0,
    output: Path | None = None,
) -> Path:
    """Plot one sequence's spectrum waterfall with labels and collision frames.

    Parameters
    ----------
    dataset_dir : Path
        Dataset directory containing ``dataset.h5``.
    split : str
        Split group to read ("train", "val", or "test").
    index : int
        Sequence index within the split.
    output : Path, optional
        Output PNG path. Defaults to ``<dataset_dir>/waterfall_sample.png``.

    Returns
    -------
    Path
        Path of the written PNG.
    """
    with h5py.File(dataset_dir / "dataset.h5", "r") as f:
        g = f[split]
        assert isinstance(g, h5py.Group)
        spectra = np.asarray(_read(g, "spectra")[index])  # (T, F)
        freqs = np.asarray(_read(g, "frequencies")[()])  # (F,)
        resonance = np.asarray(_read(g, "resonance_freqs")[index])  # (T, L)
        line_axis = np.asarray(_read(g, "line_axis")[index])  # (T, L)
        collision = np.asarray(_read(g, "collision_mask")[index])  # (T,)

    n_steps = spectra.shape[0]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(
        1.0 - spectra.T,  # dips bright on dark background
        aspect="auto",
        origin="lower",
        cmap="inferno",
        extent=(0, n_steps, freqs[0] / 1e9, freqs[-1] / 1e9),
        interpolation="nearest",
    )
    for frame in np.nonzero(collision)[0]:
        ax.axvline(frame + 0.5, color="white", alpha=0.25, lw=2, zorder=1)
    t_grid = np.arange(n_steps) + 0.5
    for axis_id in range(4):
        mask = line_axis == axis_id  # (T, L)
        t_pts = np.broadcast_to(t_grid[:, None], mask.shape)[mask]
        f_pts = resonance[mask] / 1e9
        ax.scatter(
            t_pts, f_pts, s=4, color=_AXIS_COLORS[axis_id], label=f"NV axis {axis_id}", zorder=2
        )
    ax.scatter([], [], s=40, color="white", alpha=0.4, marker="|", label="collision frame")
    ax.set_xlabel("frame (time)")
    ax.set_ylabel("MW frequency (GHz)")
    ax.set_title(
        f"Dynamic ODMR sequence #{index}: resonances move & cross (labels overlaid on spectrum)"
    )
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()

    out = output if output is not None else dataset_dir / "waterfall_sample.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Waterfall plot of one ODMR sequence.")
    parser.add_argument("dataset_dir", type=Path, help="Dataset directory with dataset.h5")
    parser.add_argument("--split", default="train", choices=("train", "val", "test"))
    parser.add_argument("--index", type=int, default=0, help="Sequence index within the split")
    parser.add_argument("--output", type=Path, default=None, help="Output PNG path")
    args = parser.parse_args()

    out = plot_sequence_waterfall(args.dataset_dir, args.split, args.index, args.output)
    print(f"Waterfall plot written to {out}")


if __name__ == "__main__":
    main()
