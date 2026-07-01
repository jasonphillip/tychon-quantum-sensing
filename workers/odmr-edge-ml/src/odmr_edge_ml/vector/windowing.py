"""Per-spectrum resonance windowing for the 8-FCNN vector readout.

Given a multi-axis CW-ODMR spectrum and the true lab-frame B-field, computes
the 4 NV-axis projections, predicts where each of the 8 (axis, sign) Zeeman
resonances should land in the frequency grid, and slices a fixed-width
window centred on each dip. The 8 windowed sub-spectra are the inputs to the
8 FCNN-v2 instances.

Spectra where a given (axis, sign) dip falls outside the frequency grid (or
too close to the edge to centre a full-width window) are flagged via the
``valid_mask`` return so the per-resonance FCNN trains only on samples where
its dip is actually visible.

Constants
---------
The NV gyromagnetic ratio (28.024 GHz/T) and zero-field splitting (D = 2.87
GHz) are pinned to the values used by ``odmr_edge_ml.evaluation.pid_proxy``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from odmr_edge_ml.vector.blue_projection import nv_axis_geometry_matrix

# Pinned NV constants — keep in sync with evaluation/pid_proxy.py
NV_GYROMAGNETIC_RATIO_HZ_T: float = 28.024e9
NV_ZERO_FIELD_SPLITTING_HZ: float = 2.87e9

# 4 NV crystallographic axes as unit vectors in the lab frame (rows of the
# top half of the 8x3 BLUE A matrix; same convention as
# nv_sensor_sim.physics.lineshape.NV_AXES_UNIT).
NV_AXES_UNIT: np.ndarray = nv_axis_geometry_matrix()[::2].copy()  # (4, 3)


@dataclass(frozen=True)
class WindowSliceBatch:
    """Per-spectrum windowed slices for one (axis_idx, sign) pair.

    Attributes
    ----------
    windows
        (N, window_size) array of sliced sub-spectra. Rows where the dip is
        out of bounds are zero-filled.
    centre_bins
        (N,) integer bin index of the expected dip in the *original* full
        frequency grid (–1 where out of bounds).
    valid_mask
        (N,) boolean mask of samples where the dip is fully inside the grid
        with room for a centred window.
    b_proj_uT
        (N,) signed projection ``B · n_i * sign`` for that (axis, sign),
        in micro-Tesla. The FCNN learns to predict this scalar from the
        windowed spectrum.
    """

    windows: np.ndarray
    centre_bins: np.ndarray
    valid_mask: np.ndarray
    b_proj_uT: np.ndarray


def compute_axis_projections(
    b_lab_T: np.ndarray, axes: np.ndarray = NV_AXES_UNIT,
) -> np.ndarray:
    """Signed projection of each lab-frame B vector onto each NV axis.

    Parameters
    ----------
    b_lab_T
        (N, 3) lab-frame B-field vectors in Tesla.
    axes
        (4, 3) unit vectors of the 4 NV crystallographic axes.

    Returns
    -------
    (N, 4) array of signed scalar projections ``B · n_i`` in Tesla.
    """
    b_lab_T = np.asarray(b_lab_T, dtype=np.float64)
    if b_lab_T.ndim != 2 or b_lab_T.shape[1] != 3:
        raise ValueError(f"b_lab_T must be (N, 3), got {b_lab_T.shape}")
    if axes.shape != (4, 3):
        raise ValueError(f"axes must be (4, 3), got {axes.shape}")
    return b_lab_T @ axes.T  # (N, 4)


def dip_frequency_hz(
    b_proj_T: np.ndarray,
    sign: int,
    gamma: float = NV_GYROMAGNETIC_RATIO_HZ_T,
    D: float = NV_ZERO_FIELD_SPLITTING_HZ,
) -> np.ndarray:
    """Predicted dip frequency for one (axis_idx-already-fixed, sign) channel.

    ``f_dip = D + sign · γ · (B · n_i)``.
    """
    if sign not in (+1, -1):
        raise ValueError(f"sign must be +1 or -1, got {sign}")
    return D + float(sign) * gamma * np.asarray(b_proj_T, dtype=np.float64)


def slice_resonance_window(
    spectra: np.ndarray,
    freq_grid: np.ndarray,
    target_freqs: np.ndarray,
    window_size: int = 100,
) -> WindowSliceBatch:
    """Slice a fixed-width window from each spectrum centred on its target dip.

    For each row i, locates ``target_freqs[i]`` on the frequency grid, takes a
    window of length ``window_size`` centred on that bin, and fills the
    output row with the spectrum sliced over those bins. Rows where the
    centred window would extend past either edge of the grid are zero-filled
    and ``valid_mask[i] = False``.

    Parameters
    ----------
    spectra
        (N, n_bins) full-resolution ODMR spectra.
    freq_grid
        (n_bins,) frequency axis in Hz, monotonically increasing.
    target_freqs
        (N,) expected dip frequencies in Hz.
    window_size
        Number of bins per window. Must be even (the centre bin lives at
        ``window_size // 2``) and ≤ ``n_bins``.

    Returns
    -------
    WindowSliceBatch
        See dataclass docs. The caller fills ``b_proj_uT`` itself; this
        function only handles the geometry.
    """
    if window_size <= 0 or window_size % 2 != 0:
        raise ValueError(f"window_size must be a positive even int, got {window_size}")
    spectra = np.asarray(spectra, dtype=np.float64)
    freq_grid = np.asarray(freq_grid, dtype=np.float64)
    target_freqs = np.asarray(target_freqs, dtype=np.float64).reshape(-1)

    n, n_bins = spectra.shape
    if freq_grid.shape != (n_bins,):
        raise ValueError(
            f"freq_grid shape {freq_grid.shape} != spectra column count {n_bins}"
        )
    if target_freqs.shape != (n,):
        raise ValueError(
            f"target_freqs shape {target_freqs.shape} != spectra row count {n}"
        )

    # Nearest-bin lookup is the simplest faithful reading on a uniform grid.
    bin_spacing = float(freq_grid[1] - freq_grid[0])
    bin_idx_float = (target_freqs - freq_grid[0]) / bin_spacing
    centre_bins = np.rint(bin_idx_float).astype(np.int64)

    half = window_size // 2
    starts = centre_bins - half
    ends = starts + window_size

    valid_mask = (starts >= 0) & (ends <= n_bins)

    windows = np.zeros((n, window_size), dtype=np.float64)
    # Mark out-of-bounds centre_bins as -1 for downstream filtering
    centre_bins_out = np.where(valid_mask, centre_bins, -1)

    if valid_mask.any():
        valid_idx = np.where(valid_mask)[0]
        for i in valid_idx:
            windows[i] = spectra[i, starts[i]:ends[i]]

    return WindowSliceBatch(
        windows=windows,
        centre_bins=centre_bins_out,
        valid_mask=valid_mask,
        b_proj_uT=np.zeros(n, dtype=np.float64),  # caller fills
    )


def build_windows_for_axis_sign(
    spectra: np.ndarray,
    labels_T: np.ndarray,
    freq_grid: np.ndarray,
    axis_idx: int,
    sign: int,
    window_size: int = 100,
    axes: np.ndarray = NV_AXES_UNIT,
) -> WindowSliceBatch:
    """End-to-end window construction for one of the 8 (axis_idx, sign) channels.

    Combines projection + dip-frequency + slicing into a single call, and
    fills ``b_proj_uT`` with the signed projection (in µT) that the
    per-channel FCNN should learn to predict.
    """
    if axis_idx not in (0, 1, 2, 3):
        raise ValueError(f"axis_idx must be in [0..3], got {axis_idx}")
    proj_T = compute_axis_projections(labels_T, axes)[:, axis_idx]  # (N,)
    target = dip_frequency_hz(proj_T, sign=sign)
    batch = slice_resonance_window(spectra, freq_grid, target, window_size)
    # Per the per-resonance label convention (positive on +sign side):
    #   sign=+1 → label = +γ·B·n_i   →   in B_proj units (Tesla)
    #   sign=-1 → label = -γ·B·n_i
    # We store the FCNN target in µT (signed) so the BLUE inversion at eval
    # time reads δ[axis,sign] = sign · B·n_i, matching the 8x3 A matrix in
    # blue_projection.py (row 2i is +n_i, row 2i+1 is -n_i).
    b_proj_uT = (float(sign) * proj_T * 1e6).astype(np.float64)
    # Re-pack with the filled label
    return WindowSliceBatch(
        windows=batch.windows,
        centre_bins=batch.centre_bins,
        valid_mask=batch.valid_mask,
        b_proj_uT=b_proj_uT,
    )
