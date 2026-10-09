"""Synthetic v1-contract fixtures — a hand-scripted MOCK, NOT physics.

These tiny analytic sequences exist so the consumer-side code (loader, contract validator,
classical baseline, metrics) can be developed and tested **before** the real upstream
``nv-sensor-sim`` time-series + collision generator exists. They are deliberately NOT a
physics simulation: there is no SimOS call, no real lineshape, no noise model — just a
first-order linear-Zeeman analytic model
(:func:`odmr_vector_tracking.vector.geometry.resonance_frequencies`) driven by a hand-scripted
field trajectory that forces a clean, localized inter-axis crossing.

Self-consistency is intentional: ``resonance_freqs`` are derived from ``B_true`` via the
vendored geometry, so ``B_true`` round-trips through the BLUE inversion. That gives the
classical baseline and the metrics valid ground truth to test against. When the real dataset
lands, the *same* loader reads it — only the producer changes.

The default scenario (8 mT off-axis bias, a 2 mT signal ramp) keeps all 8 lines well-resolved
for the first ~50 frames, then drives one inter-axis pair through a true crossing near frame 60
— the regime where a nearest-peak classical tracker swaps line identities and loses lock.

Schema emitted: the exact v1 contract (see ``docs/design/03_data_contract.md``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

from odmr_vector_tracking.vector.geometry import (
    LINE_AXIS_8,
    LINE_TRANSITION_8,
    N_LINES_ELECTRONIC,
    ZFS_D_HZ,
    resonance_frequencies_diagonalized,
)

GENERATED_AT = "2026-06-29T00:00:00Z"  # fixed for deterministic fixtures

# Default scenario parameters (tuned for a clean, localized inter-axis crossing; see the
# module docstring). Shared by the split builder and the dataset/manifest builder so the
# manifest always describes the data that was actually generated.
DEFAULTS: dict[str, object] = {
    "n_timesteps": 200,
    "n_freq": 400,
    "dt_s": 1.0e-3,
    "linewidth_Hz": 4.0e6,
    "collision_threshold_linewidths": 1.5,
    "bias_B0_T": 8.0e-3,
    "bias_direction_uvw": (0.2, 0.3, 0.93),
    "signal_direction_uvw": (0.0, 1.0, 0.0),
    "signal_amplitude_T": 2.0e-3,
    "contrast": 0.12,
    "noise_std": 2.0e-3,
    "window_margin": 1.3,
}


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def _field_trajectory(
    n_timesteps: int,
    bias_vec_T: np.ndarray,
    signal_dir: np.ndarray,
    signal_amplitude_T: float,
) -> np.ndarray:
    """Hand-scripted B(t): off-axis bias + a linear ramp along ``signal_dir``.

    The ramp sweeps the signal projection from ``-A`` to ``+A``, dragging the per-axis
    resonance frequencies across one another. Returns shape ``(T, 3)`` in Tesla.
    """
    s = np.linspace(-1.0, 1.0, n_timesteps) * signal_amplitude_T
    return bias_vec_T[None, :] + s[:, None] * _unit(signal_dir)[None, :]


def _resonance_series(B_t: np.ndarray) -> np.ndarray:
    """Per-frame 8-line **diagonalized** resonance frequencies for a (T,3) trajectory → (T, 8) Hz.

    Uses the diagonalized model (first-order Zeeman + second-order common-mode shift) so the
    fixture centers match the upstream generator; the per-axis splitting still equals
    ``γ_e·(B·n_i)`` exactly, so BLUE round-trips B.
    """
    return np.stack(
        [resonance_frequencies_diagonalized(B_t[t]) for t in range(B_t.shape[0])], axis=0
    )


def _label_collisions(
    res_freqs: np.ndarray, threshold_hz: float
) -> tuple[np.ndarray, np.ndarray]:
    """Collision labels from pairwise line proximity.

    Returns ``(collision_mask (T,), line_collision (T, L))``: a frame collides if any two of
    its resonances are within ``threshold_hz``; a line collides if it is within
    ``threshold_hz`` of any *other* line that frame.
    """
    diff = np.abs(res_freqs[:, :, None] - res_freqs[:, None, :])  # (T, L, L)
    n_lines = res_freqs.shape[1]
    diag = np.eye(n_lines, dtype=bool)[None, :, :]
    within = (diff < threshold_hz) & ~diag
    line_collision = np.any(within, axis=2)  # (T, L)
    collision_mask = np.any(line_collision, axis=1)  # (T,)
    return collision_mask, line_collision


def _lorentzian_spectrum(
    freqs_hz: np.ndarray,
    centers_hz: np.ndarray,
    hwhm_hz: float,
    contrast: float,
) -> np.ndarray:
    """PL spectrum = 1 − Σ contrast · Lorentzian(center, hwhm). PL ≈ 1 off-resonance."""
    d = freqs_hz[:, None] - centers_hz[None, :]  # (F, L)
    lor = (hwhm_hz**2) / (d**2 + hwhm_hz**2)
    return 1.0 - contrast * lor.sum(axis=1)


def compute_mw_window(
    *,
    n_timesteps: int,
    bias_B0_T: float,
    bias_direction_uvw: tuple[float, float, float],
    signal_direction_uvw: tuple[float, float, float],
    signal_amplitude_T: float,
    window_margin: float,
) -> tuple[float, float]:
    """MW sweep window (Hz) that comfortably contains all 8 lines, centered on the ZFS.

    Computed from the nominal (un-perturbed) trajectory; the ±5% per-sequence perturbation
    stays inside ``window_margin``.
    """
    bias_vec = bias_B0_T * _unit(np.asarray(bias_direction_uvw))
    B_t = _field_trajectory(
        n_timesteps, bias_vec, np.asarray(signal_direction_uvw), signal_amplitude_T
    )
    rf = _resonance_series(B_t)
    half = float(np.max(np.abs(rf - ZFS_D_HZ))) * window_margin
    return (ZFS_D_HZ - half, ZFS_D_HZ + half)


def make_synthetic_split(
    n_sequences: int,
    seeds: list[int],
    *,
    mw_window_Hz: tuple[float, float] | None = None,
    n_timesteps: int = 200,
    n_freq: int = 400,
    linewidth_Hz: float = 4.0e6,
    collision_threshold_linewidths: float = 1.5,
    bias_B0_T: float = 8.0e-3,
    bias_direction_uvw: tuple[float, float, float] = (0.2, 0.3, 0.93),
    signal_direction_uvw: tuple[float, float, float] = (0.0, 1.0, 0.0),
    signal_amplitude_T: float = 2.0e-3,
    contrast: float = 0.12,
    noise_std: float = 2.0e-3,
    window_margin: float = 1.3,
) -> dict[str, np.ndarray]:
    """Build one split's worth of v1-schema arrays (in memory).

    Each sequence shares the scripted crossing but is slightly perturbed (signal direction +
    amplitude jitter, independent PL noise) keyed by its seed, so sequences are not identical.

    Returns a dict of numpy arrays in contract dtypes (see module docstring / v1 contract).
    """
    if len(seeds) != n_sequences:
        raise ValueError(f"need {n_sequences} seeds, got {len(seeds)}")

    if mw_window_Hz is None:
        mw_window_Hz = compute_mw_window(
            n_timesteps=n_timesteps,
            bias_B0_T=bias_B0_T,
            bias_direction_uvw=bias_direction_uvw,
            signal_direction_uvw=signal_direction_uvw,
            signal_amplitude_T=signal_amplitude_T,
            window_margin=window_margin,
        )

    L = N_LINES_ELECTRONIC
    freqs = np.linspace(mw_window_Hz[0], mw_window_Hz[1], n_freq)
    bias_vec = bias_B0_T * _unit(np.asarray(bias_direction_uvw))
    threshold_hz = collision_threshold_linewidths * linewidth_Hz
    hwhm = linewidth_Hz / 2.0

    spectra = np.empty((n_sequences, n_timesteps, n_freq), dtype=np.float32)
    B_true = np.empty((n_sequences, n_timesteps, 3), dtype=np.float32)
    res_freqs = np.empty((n_sequences, n_timesteps, L), dtype=np.float32)
    coll_mask = np.empty((n_sequences, n_timesteps), dtype=bool)
    line_coll = np.empty((n_sequences, n_timesteps, L), dtype=bool)

    for i, seed in enumerate(seeds):
        rng = np.random.default_rng(seed)
        # Mild per-sequence perturbation keeps the crossing while breaking identicality.
        sig_dir = _unit(np.asarray(signal_direction_uvw) + rng.normal(0.0, 0.05, size=3))
        amp = signal_amplitude_T * (1.0 + rng.normal(0.0, 0.05))

        B_t = _field_trajectory(n_timesteps, bias_vec, sig_dir, amp)
        rf = _resonance_series(B_t)  # (T, L)
        cmask, lcoll = _label_collisions(rf, threshold_hz)

        spec = np.stack(
            [_lorentzian_spectrum(freqs, rf[t], hwhm, contrast) for t in range(n_timesteps)],
            axis=0,
        )
        spec = spec + rng.normal(0.0, noise_std, size=spec.shape)

        B_true[i] = B_t.astype(np.float32)
        res_freqs[i] = rf.astype(np.float32)
        coll_mask[i] = cmask
        line_coll[i] = lcoll
        spectra[i] = spec.astype(np.float32)

    line_axis = np.broadcast_to(LINE_AXIS_8, (n_sequences, n_timesteps, L)).astype(np.int8).copy()
    line_transition = (
        np.broadcast_to(LINE_TRANSITION_8, (n_sequences, n_timesteps, L)).astype(np.int8).copy()
    )

    return {
        "spectra": spectra,
        "frequencies": freqs.astype(np.float32),
        "B_true": B_true,
        "resonance_freqs": res_freqs,
        "line_axis": line_axis,
        "line_transition": line_transition,
        "collision_mask": coll_mask,
        "line_collision": line_coll,
        "bias": bias_vec.astype(np.float32),
        "seeds": np.asarray(seeds, dtype=np.int64),
    }


def _has_inter_axis_collision(split: dict[str, np.ndarray]) -> bool:
    """True if any labeled collision involves two lines of *different* NV axes."""
    axes = split["line_axis"][0, 0]  # (L,)
    line_coll = split["line_collision"]  # (N,T,L)
    n, t, _ = line_coll.shape
    for ni in range(n):
        for ti in range(t):
            flagged = np.where(line_coll[ni, ti])[0]
            if flagged.size >= 2 and np.unique(axes[flagged]).size > 1:
                return True
    return False


def make_synthetic_dataset(
    split_sizes: dict[str, int] | None = None,
    *,
    master_seed: int = 0,
    **overrides: object,
) -> tuple[dict[str, dict[str, np.ndarray]], dict]:
    """Build all splits + a valid v1 manifest (in memory).

    Parameters
    ----------
    split_sizes
        ``{"train": N, "val": N, "test": N}``. Defaults to ``{train:4, val:2, test:2}``.
    master_seed
        Base for the disjoint per-split seed lists.
    **overrides
        Override any key in :data:`DEFAULTS` (n_timesteps, n_freq, linewidth_Hz, ...).

    Returns
    -------
    (splits, manifest)
        ``splits`` maps split name → array dict; ``manifest`` is the JSON sidecar dict.
    """
    if split_sizes is None:
        split_sizes = {"train": 4, "val": 2, "test": 2}

    params = {**DEFAULTS, **overrides}

    # Disjoint seed blocks per split.
    seed_lists: dict[str, list[int]] = {}
    cursor = master_seed + 1
    for split in ("train", "val", "test"):
        count = split_sizes.get(split, 0)
        seed_lists[split] = list(range(cursor, cursor + count))
        cursor += count

    # One shared MW window for the whole dataset, from the nominal trajectory.
    mw_window = compute_mw_window(
        n_timesteps=int(params["n_timesteps"]),  # type: ignore[arg-type]
        bias_B0_T=float(params["bias_B0_T"]),  # type: ignore[arg-type]
        bias_direction_uvw=params["bias_direction_uvw"],  # type: ignore[arg-type]
        signal_direction_uvw=params["signal_direction_uvw"],  # type: ignore[arg-type]
        signal_amplitude_T=float(params["signal_amplitude_T"]),  # type: ignore[arg-type]
        window_margin=float(params["window_margin"]),  # type: ignore[arg-type]
    )

    # dt_s and window_margin are not split-builder kwargs (dt_s is manifest-only;
    # window_margin is passed explicitly above alongside the precomputed window).
    split_params = {k: v for k, v in params.items() if k not in ("window_margin", "dt_s")}
    splits: dict[str, dict[str, np.ndarray]] = {}
    for split, count in split_sizes.items():
        if count <= 0:
            continue
        splits[split] = make_synthetic_split(
            count, seed_lists[split], mw_window_Hz=mw_window,
            window_margin=float(params["window_margin"]),  # type: ignore[arg-type]
            **split_params,  # type: ignore[arg-type]
        )

    # Guard: the fixture must actually contain a labeled inter-axis crossing.
    if not any(_has_inter_axis_collision(s) for s in splits.values()):
        raise RuntimeError(
            "synthetic fixture produced no inter-axis crossing — increase signal_amplitude_T "
            "or collision_threshold_linewidths"
        )

    n_lines = N_LINES_ELECTRONIC
    bias_dir = _unit(np.asarray(params["bias_direction_uvw"]))
    config_hash = hashlib.sha256(
        json.dumps(
            {"split_sizes": split_sizes, "master_seed": master_seed,
             "params": {k: str(v) for k, v in params.items()}},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]

    manifest = {
        "contract_version": "v1",
        "generator_git_sha": "synthetic-fixture",
        "config_hash": config_hash,
        "generated_at": GENERATED_AT,
        "backend": "synthetic",
        "master_seed": master_seed,
        "train_seeds": seed_lists["train"],
        "val_seeds": seed_lists["val"],
        "test_seeds": seed_lists["test"],
        "n_spectra_train": split_sizes.get("train", 0),
        "n_spectra_val": split_sizes.get("val", 0),
        "n_spectra_test": split_sizes.get("test", 0),
        "n_timesteps": int(params["n_timesteps"]),  # type: ignore[arg-type]
        "dt_s": float(params["dt_s"]),  # type: ignore[arg-type]
        "n_lines": n_lines,
        "hyperfine": False,
        "linewidth_Hz": float(params["linewidth_Hz"]),  # type: ignore[arg-type]
        "collision_threshold_linewidths": float(params["collision_threshold_linewidths"]),  # type: ignore[arg-type]
        "n_freq_points": int(params["n_freq"]),  # type: ignore[arg-type]
        "freq_range_Hz": [float(mw_window[0]), float(mw_window[1])],
        "bias_B0_T": float(params["bias_B0_T"]),  # type: ignore[arg-type]
        "bias_direction_uvw": [float(c) for c in bias_dir],
        "sweep_description": (
            "SYNTHETIC MOCK (not physics): 8 mT off-axis bias + linear signal ramp driving a "
            "scripted inter-axis ODMR crossing near mid-sequence; first-order linear-Zeeman "
            "analytic model."
        ),
        "units": {"frequency": "Hz", "magnetic_field": "T", "time": "s"},
    }
    return splits, manifest


def write_synthetic_h5(
    out_dir: Path | str,
    split_sizes: dict[str, int] | None = None,
    *,
    master_seed: int = 0,
    **overrides: object,
) -> Path:
    """Materialize a synthetic v1 dataset (``dataset.h5`` + ``manifest.json``) to ``out_dir``.

    Returns the directory path. The result passes
    :func:`odmr_vector_tracking.data.contract.validate_dataset_dir`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    splits, manifest = make_synthetic_dataset(split_sizes, master_seed=master_seed, **overrides)

    h5_path = out_dir / "dataset.h5"
    bias = next(iter(splits.values()))["bias"]  # identical across splits
    with h5py.File(h5_path, "w") as f:
        f.create_dataset("bias", data=bias)  # top-level /bias, per the v1 contract
        for split, arrays in splits.items():
            g = f.create_group(split)
            for name, arr in arrays.items():
                if name == "bias":
                    continue  # bias lives top-level, not per-split
                g.create_dataset(name, data=arr)

    with open(out_dir / "manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2)

    return out_dir
