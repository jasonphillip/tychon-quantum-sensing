"""Per-split label statistics for time-series ODMR datasets.

Computed from the rendered labels (resonance centers, collision masks, field
trajectories) at generation time and stored in the manifest's
``sequence_stats`` block, so consumers can see the crossing/collision content
of each split without re-scanning the HDF5:

- **crossings** — a crossing is a pair of lines actually swapping frequency
  order between consecutive frames (sign flip of ``f_i - f_j``), as opposed to
  a *collision* (two lines within ``k * Gamma``). Sequences with zero crossings
  are identity-hold negatives: lines move but never trade places.
- **collision dwell** — lengths of consecutive collision-frame runs, i.e. how
  long line pairs stay unresolved per event.
- **near-merge margin** — the minimum same-axis splitting ``f+ - f-`` and the
  minimum per-axis ``|B . n_i|``; splittings below ``2 * Gamma`` mean an axis'
  own two lines approach within the collision resolution of each other.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT


def count_crossings(centers_TL: np.ndarray) -> tuple[int, np.ndarray]:
    """Count line-order swaps (crossings) in one sequence's resonance centers.

    A crossing is counted at frame ``t`` when ``sign(f_i - f_j)`` differs
    between frames ``t - 1`` and ``t`` for a line pair ``(i, j)``.

    Parameters
    ----------
    centers_TL : np.ndarray
        Resonance centers, shape (T, L), in Hz.

    Returns
    -------
    tuple[int, np.ndarray]
        ``(n_crossings, crossing_frames)``: total pairwise order swaps and the
        frame index of each swap (length ``n_crossings``, values in ``1..T-1``).
    """
    centers = np.asarray(centers_TL, dtype=float)
    n_lines = centers.shape[1]
    iu, ju = np.triu_indices(n_lines, k=1)
    diff = centers[:, iu] - centers[:, ju]  # (T, P) pairwise differences
    sign = np.sign(diff)
    flips = sign[1:] * sign[:-1] < 0  # (T-1, P)
    per_frame_counts = flips.sum(axis=1)  # (T-1,)
    crossing_frames = np.repeat(np.arange(1, centers.shape[0]), per_frame_counts)
    return int(flips.sum()), crossing_frames


def collision_dwell_lengths(mask_T: np.ndarray) -> np.ndarray:
    """Lengths of consecutive True runs in a per-frame collision mask.

    Parameters
    ----------
    mask_T : np.ndarray
        Collision mask, shape (T,), bool.

    Returns
    -------
    np.ndarray
        Run lengths in frames (possibly empty).
    """
    mask = np.asarray(mask_T, dtype=bool).astype(int)
    padded = np.concatenate([[0], mask, [0]])
    edges = np.diff(padded)
    starts = np.nonzero(edges == 1)[0]
    ends = np.nonzero(edges == -1)[0]
    return ends - starts


def _summary(values: np.ndarray, percentiles: tuple[int, ...] = (10, 50, 90)) -> dict:
    """Compact JSON-serializable summary of a 1-D array (empty-safe)."""
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return {"n": 0}
    out: dict = {"n": int(v.size), "min": float(v.min()), "max": float(v.max())}
    for p in percentiles:
        out[f"p{p}"] = float(np.percentile(v, p))
    out["mean"] = float(v.mean())
    return out


def split_sequence_stats(
    resonance_NTL: np.ndarray,
    collision_mask_NT: np.ndarray,
    B_true_NT3: np.ndarray,
    gamma_fwhm_hz: float,
    nv_axes: np.ndarray = NV_AXES_UNIT,
) -> dict:
    """Label statistics for one split of a sequence dataset.

    Parameters
    ----------
    resonance_NTL : np.ndarray
        Resonance centers, shape (N, T, L), Hz. Line ordering follows
        ``nv_geometry_matrix()`` rows: line ``2i`` / ``2i+1`` are axis i's
        ms0->+1 / ms0->-1 transitions.
    collision_mask_NT : np.ndarray
        Per-frame collision flags, shape (N, T).
    B_true_NT3 : np.ndarray
        Lab-frame field per frame, shape (N, T, 3), Tesla.
    gamma_fwhm_hz : float
        Linewidth Gamma (FWHM) in Hz.
    nv_axes : np.ndarray
        Unit vectors of the NV axes, shape (n_axes, 3).

    Returns
    -------
    dict
        JSON-serializable stats block. Keys: ``n_sequences``,
        ``crossing_count_per_sequence`` (list), ``crossing_count`` (summary),
        ``no_crossing_fraction``, ``crossing_frame`` (summary, frame indices),
        ``collision_frame_fraction`` (summary over sequences),
        ``collision_dwell_frames`` (summary over runs),
        ``min_axis_splitting_Hz`` (summary of per-sequence minima),
        ``near_merge_fraction`` (splitting < 2*Gamma),
        ``min_abs_projection_T`` (summary of per-sequence minima),
        ``max_line_speed_Hz_per_frame`` and
        ``max_line_speed_linewidths_per_frame`` (summaries of per-sequence
        maxima).
    """
    resonance = np.asarray(resonance_NTL, dtype=float)
    collision = np.asarray(collision_mask_NT, dtype=bool)
    B_true = np.asarray(B_true_NT3, dtype=float)
    n_seq = resonance.shape[0]

    crossing_counts = np.empty(n_seq, dtype=int)
    crossing_frames: list[np.ndarray] = []
    dwell_runs: list[np.ndarray] = []
    for s in range(n_seq):
        n_cross, frames = count_crossings(resonance[s])
        crossing_counts[s] = n_cross
        crossing_frames.append(frames)
        dwell_runs.append(collision_dwell_lengths(collision[s]))
    all_crossing_frames = (
        np.concatenate(crossing_frames) if crossing_frames else np.empty(0)
    )
    all_dwells = np.concatenate(dwell_runs) if dwell_runs else np.empty(0)

    # Same-axis splitting f+ - f- per (sequence, frame, axis); line 2i is the
    # ms0->+1 transition of axis i and 2i+1 its ms0->-1 partner.
    splitting = np.abs(resonance[:, :, 0::2] - resonance[:, :, 1::2])  # (N, T, A)
    min_splitting_per_seq = splitting.min(axis=(1, 2))  # (N,)
    near_merge = min_splitting_per_seq < 2.0 * gamma_fwhm_hz

    # Per-axis signed projections from the stored ground-truth field.
    proj = np.abs(np.einsum("ntk,ak->nta", B_true, np.asarray(nv_axes, dtype=float)))
    min_proj_per_seq = proj.min(axis=(1, 2))  # (N,)

    # Line speed: per-frame center motion, max over lines/frames per sequence.
    speed = np.abs(np.diff(resonance, axis=1))  # (N, T-1, L)
    max_speed_per_seq = speed.max(axis=(1, 2)) if speed.size else np.zeros(n_seq)

    return {
        "n_sequences": int(n_seq),
        "crossing_count_per_sequence": crossing_counts.tolist(),
        "crossing_count": _summary(crossing_counts),
        "no_crossing_fraction": float(np.mean(crossing_counts == 0)),
        "crossing_frame": _summary(all_crossing_frames),
        "collision_frame_fraction": _summary(collision.mean(axis=1)),
        "collision_dwell_frames": _summary(all_dwells),
        "min_axis_splitting_Hz": _summary(min_splitting_per_seq),
        "near_merge_fraction": float(np.mean(near_merge)),
        "n_near_merge_sequences": int(near_merge.sum()),
        "min_abs_projection_T": _summary(min_proj_per_seq),
        "max_line_speed_Hz_per_frame": _summary(max_speed_per_seq),
        "max_line_speed_linewidths_per_frame": _summary(max_speed_per_seq / gamma_fwhm_hz),
    }
