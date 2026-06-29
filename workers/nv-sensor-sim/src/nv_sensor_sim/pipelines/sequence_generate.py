"""Time-series ("dynamic") ODMR dataset generation pipeline.

Generates train/val/test splits of ODMR *sequences*: each sample is a field
trajectory B(t) (static bias + swept external field) rendered into a per-frame
multi-axis spectrum with moving, crossing resonances, plus ground-truth B(t),
per-line resonance positions with axis/transition identity, and collision labels.

Writes the HDF5 + JSON manifest bundle described in docs/dataset-contract.md
(time-series layout). Per-sequence seeds are drawn disjoint across splits and the
separation is enforced by ``DatasetManifest.validate()`` (shared with the static
pipeline).

The MW window and frequency-point count are derived from the trajectory's field
extent and the linewidth so the moving lines stay resolved inside the window.
"""

from __future__ import annotations

import datetime
import hashlib
import time
from pathlib import Path

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.datasets.schema import DatasetManifest
from nv_sensor_sim.datasets.writer import DatasetWriter
from nv_sensor_sim.dynamics.field_trajectory import ramp_crossing_trajectory, static_bias_vector
from nv_sensor_sim.dynamics.render import render_multi_axis_frame, render_sequence
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT, project_field_onto_axes
from nv_sensor_sim.physics.parameters import compute_linewidth
from nv_sensor_sim.pipelines.batch_generate import _get_git_sha, _get_versions

# Datasets written by write_sequences / read by load_sequence_split.
_SEQ_ARRAY_KEYS = (
    "spectra",
    "B_true",
    "resonance_freqs",
    "line_axis",
    "line_transition",
    "collision_mask",
    "line_collision",
)


def _trajectory_extent(
    bias_T: np.ndarray,
    ramp_start_T: tuple[float, float, float],
    ramp_end_T: tuple[float, float, float],
    n_timesteps: int,
    nv_axes: np.ndarray,
) -> tuple[float, float]:
    """Max axial projection and max transverse magnitude over a nominal ramp.

    Returns ``(B_par_max, B_perp_max)`` in Tesla — the field extent used to size
    the MW window so the swept lines stay inside it.
    """
    traj = ramp_crossing_trajectory(bias_T, ramp_start_T, ramp_end_T, n_timesteps)
    b_par_max, b_perp_max = 0.0, 0.0
    for t in range(traj.shape[0]):
        b_par, b_perp = project_field_onto_axes(traj[t], nv_axes=nv_axes)
        b_par_max = max(b_par_max, float(np.max(np.abs(b_par))))
        b_perp_max = max(b_perp_max, float(np.max(b_perp)))
    return b_par_max, b_perp_max


def _generate_sequence_split(
    adapter: SimOSAdapter,
    split_seeds: list[int],
    bias_T: np.ndarray,
    ramp_start_T: tuple[float, float, float],
    ramp_end_T: tuple[float, float, float],
    n_timesteps: int,
    p1_ppm: float,
    gamma_fwhm_hz: float,
    k: float,
    extra_b_perp_T: float,
    jitter_frac: float,
    nv_axes: np.ndarray,
    split_name: str,
) -> dict[str, np.ndarray]:
    """Render every sequence in a split and stack into (N, T, ...) arrays."""
    n_split = len(split_seeds)
    per_seq: list[dict[str, np.ndarray]] = []
    frequencies: np.ndarray | None = None

    print(f"Generating {n_split} sequences for {split_name} split...")
    for idx, seed in enumerate(split_seeds):
        traj = ramp_crossing_trajectory(
            bias_T,
            ramp_start_T,
            ramp_end_T,
            n_timesteps,
            seed=int(seed),
            jitter_frac=jitter_frac,
        )
        out = render_sequence(
            adapter,
            traj,
            p1_ppm=p1_ppm,
            gamma_fwhm_hz=gamma_fwhm_hz,
            k=k,
            extra_b_perp_T=extra_b_perp_T,
            nv_axes=nv_axes,
        )
        if frequencies is None:
            frequencies = out["frequencies"]
        per_seq.append(out)
        if (idx + 1) % 8 == 0 or idx + 1 == n_split:
            print(f"  {split_name}: {idx + 1}/{n_split}")

    assert frequencies is not None  # n_split >= 1 (caller skips empty splits)
    stacked = {key: np.stack([s[key] for s in per_seq], axis=0) for key in _SEQ_ARRAY_KEYS}
    stacked["frequencies"] = frequencies
    stacked["seeds"] = np.asarray(split_seeds, dtype=np.int64)
    return stacked


def generate_sequence_dataset(
    output_dir: str,
    n_train: int = 64,
    n_val: int = 16,
    n_test: int = 16,
    master_seed: int = 42,
    n_timesteps: int = 128,
    dt_s: float = 1.0e-3,
    p1_ppm: float = 40.0,
    temperature_K: float = 300.0,
    bias_B0_T: float = 5.0e-3,
    bias_direction_uvw: tuple[float, float, float] = (0.2, 0.1, 1.0),
    ramp_start_T: tuple[float, float, float] = (-2.0e-3, 0.0, 0.0),
    ramp_end_T: tuple[float, float, float] = (2.0e-3, 0.0, 0.0),
    jitter_frac: float = 0.05,
    collision_threshold_linewidths: float = 1.0,
    extra_b_perp_T: float = 0.0,
    hyperfine: bool = False,
    n_freq_points: int | None = None,
    freq_margin_factor: float = 1.15,
    aliasing_safety: float = 3.5,
    sweep_description: str = "",
) -> str:
    """Generate a complete time-series ODMR dataset with manifest.

    Parameters
    ----------
    output_dir : str
        Output directory for HDF5 + manifest.
    n_train, n_val, n_test : int
        Number of sequences per split.
    master_seed : int
        Master random seed (drives per-sequence seeds + trajectory jitter).
    n_timesteps : int
        Number of frames T per sequence.
    dt_s : float
        Time between frames in seconds (recorded for df/dB slope and the
        Gamma/2-per-cycle loss-of-lock comparison downstream).
    p1_ppm : float
        P1 concentration in ppm (fixed across the dataset, sets Gamma).
    temperature_K : float
        Sample temperature in Kelvin (fixed across the dataset).
    bias_B0_T : float
        Static bias magnitude in Tesla.
    bias_direction_uvw : tuple[float, float, float]
        Bias direction (crystal [uvw] == lab xyz).
    ramp_start_T, ramp_end_T : tuple[float, float, float]
        External swept-field 3-vectors (Tesla) at first and last frame.
    jitter_frac : float
        Per-sequence fractional jitter on the ramp endpoints.
    collision_threshold_linewidths : float
        k in the ``|f_i - f_j| < k * Gamma`` collision rule.
    extra_b_perp_T : float
        Additional stray transverse field beyond the geometric projection.
    hyperfine : bool
        14N hyperfine (L=24). Not implemented for v0 (raises).
    n_freq_points : int, optional
        Frequency points F. If None, derived from window span and Gamma so the
        grid step is <= Gamma / aliasing_safety.
    freq_margin_factor : float
        Multiplier on the first-order field extent when sizing the window.
    aliasing_safety : float
        Grid step is kept below Gamma / aliasing_safety (adapter warns at /3).
    sweep_description : str
        Free-text description of the sweep (stored in the manifest).

    Returns
    -------
    str
        Absolute path to the output directory.
    """
    if hyperfine:
        raise NotImplementedError(
            "14N hyperfine (L=24) sequence datasets are not yet implemented: the 24 "
            "lines need a per-component line_mI label to be uniquely keyed. Use "
            "hyperfine=False (L=8) for now."
        )

    nv_axes = NV_AXES_UNIT
    n_lines = 2 * len(nv_axes)  # 8 electronic lines
    gamma_fwhm_hz = compute_linewidth(p1_ppm)
    bias_vec = static_bias_vector(bias_B0_T, bias_direction_uvw)

    # --- Derive the MW window from the trajectory field extent + linewidth ---
    # Read D once from a zero-field diagonalization (grid-independent) so the
    # window is centred on the true ZFS.
    probe_cfg = SimulationConfig(
        use_optics=False,
        include_nitrogen=False,
        temperature_K=temperature_K,
    )
    probe_adapter = SimOSAdapter(probe_cfg)
    _, _, zf_centers = probe_adapter.generate_odmr_spectrum(
        B_field=np.zeros(3), temperature_K=temperature_K, return_line_centers=True
    )
    D_hz = float(np.mean(zf_centers))

    b_par_max, b_perp_max = _trajectory_extent(
        bias_vec, ramp_start_T, ramp_end_T, n_timesteps, nv_axes
    )
    # Inflate for per-sequence jitter on the endpoints.
    jitter_infl = 1.0 + 3.0 * jitter_frac
    b_par_max *= jitter_infl
    b_perp_max *= jitter_infl

    first_order = freq_margin_factor * GAMMA_HZ_PER_T * b_par_max
    second_order = 1.5 * (GAMMA_HZ_PER_T * b_perp_max) ** 2 / D_hz  # common-mode shift
    half_window = first_order + second_order + 5.0 * gamma_fwhm_hz
    freq_range = (D_hz - half_window, D_hz + half_window)

    if n_freq_points is None:
        span = freq_range[1] - freq_range[0]
        n_freq_points = int(np.ceil(span / (gamma_fwhm_hz / aliasing_safety))) + 1

    print(
        f"D={D_hz / 1e9:.5f} GHz  Gamma={gamma_fwhm_hz / 1e6:.4f} MHz  "
        f"window=[{freq_range[0] / 1e9:.4f}, {freq_range[1] / 1e9:.4f}] GHz  "
        f"F={n_freq_points}  step={(freq_range[1] - freq_range[0]) / (n_freq_points - 1) / 1e6:.4f} MHz"
    )

    # --- Seeds: disjoint across splits (enforced by validate) ---
    rng = np.random.default_rng(master_seed)
    total = n_train + n_val + n_test
    seeds = rng.choice(2**31, size=total, replace=False).tolist()
    train_seeds = seeds[:n_train]
    val_seeds = seeds[n_train : n_train + n_val]
    test_seeds = seeds[n_train + n_val :]

    # --- Provenance + manifest ---
    simos_ver, qutip_ver = _get_versions()
    config_str = (
        f"{master_seed}:{n_timesteps}:{dt_s}:{p1_ppm}:{bias_B0_T}:{bias_direction_uvw}"
        f":{ramp_start_T}:{ramp_end_T}:{collision_threshold_linewidths}:{freq_range}"
    )
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

    if not sweep_description:
        sweep_description = (
            f"linear ramp of external field {ramp_start_T}->{ramp_end_T} T over "
            f"{n_timesteps} frames on a {bias_B0_T * 1e3:.2f} mT bias along "
            f"{bias_direction_uvw}; jitter_frac={jitter_frac}"
        )

    manifest = DatasetManifest(
        generator_git_sha=_get_git_sha(),
        config_hash=config_hash,
        simos_version=simos_ver,
        qutip_version=qutip_ver,
        backend="qutip",
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        master_seed=master_seed,
        train_seeds=train_seeds,
        val_seeds=val_seeds,
        test_seeds=test_seeds,
        n_spectra_train=n_train,
        n_spectra_val=n_val,
        n_spectra_test=n_test,
        train_indices=list(range(n_train)),
        val_indices=list(range(n_train, n_train + n_val)),
        test_indices=list(range(n_train + n_val, total)),
        n_freq_points=n_freq_points,
        freq_range_Hz=freq_range,
        p1_concentration_range_ppm=(p1_ppm, p1_ppm),
        temperature_range_K=(temperature_K, temperature_K),
        b1_gradient_range=(0.0, 0.0),
        b_perp_range_T=(extra_b_perp_T, extra_b_perp_T),
        # Time-series fields
        sequence_mode=True,
        n_timesteps=n_timesteps,
        dt_s=dt_s,
        n_lines=n_lines,
        hyperfine=hyperfine,
        linewidth_Hz=gamma_fwhm_hz,
        collision_threshold_linewidths=collision_threshold_linewidths,
        sweep_description=sweep_description,
        # Bias configuration (shared with the static vector path)
        bias_B0_T=bias_B0_T,
        bias_direction_uvw=bias_direction_uvw,
    )
    manifest.validate()

    # --- Adapter + dry-run pre-flight ---
    config = SimulationConfig(
        random_seed=master_seed,
        use_optics=False,
        include_nitrogen=False,
        temperature_K=temperature_K,
        n_freq_points=n_freq_points,
        mw_freq_range_Hz=freq_range,
    )
    adapter = SimOSAdapter(config)

    n_dry = min(10, n_timesteps)
    dry_traj = ramp_crossing_trajectory(bias_vec, ramp_start_T, ramp_end_T, n_timesteps)
    t0 = time.perf_counter()
    for t in range(n_dry):
        render_multi_axis_frame(adapter, dry_traj[t], p1_ppm=p1_ppm, extra_b_perp_T=extra_b_perp_T)
    per_frame_s = (time.perf_counter() - t0) / n_dry
    total_frames = total * n_timesteps
    print(
        f"Dry-run: {per_frame_s * 1e3:.1f} ms/frame -> ETA "
        f"{per_frame_s * total_frames:.0f} s for {total} sequences x {n_timesteps} frames; "
        f"per-split spectra shape (N, {n_timesteps}, {n_freq_points})"
    )

    # --- Render + write each split ---
    writer = DatasetWriter(Path(output_dir))
    splits = [("train", train_seeds), ("val", val_seeds), ("test", test_seeds)]
    for split_name, split_seeds in splits:
        if len(split_seeds) == 0:
            continue
        data = _generate_sequence_split(
            adapter,
            split_seeds,
            bias_vec,
            ramp_start_T,
            ramp_end_T,
            n_timesteps,
            p1_ppm,
            gamma_fwhm_hz,
            collision_threshold_linewidths,
            extra_b_perp_T,
            jitter_frac,
            nv_axes,
            split_name,
        )
        writer.write_sequences(
            spectra=data["spectra"],
            frequencies=data["frequencies"],
            B_true=data["B_true"],
            resonance_freqs=data["resonance_freqs"],
            line_axis=data["line_axis"],
            line_transition=data["line_transition"],
            collision_mask=data["collision_mask"],
            line_collision=data["line_collision"],
            bias=bias_vec,
            seeds=data["seeds"],
            split=split_name,
        )

    writer.write_manifest(manifest)
    output_path = writer.finalize()
    print(f"Sequence dataset written to {output_path}")
    return output_path


if __name__ == "__main__":
    generate_sequence_dataset("./data/sequence_v0")
