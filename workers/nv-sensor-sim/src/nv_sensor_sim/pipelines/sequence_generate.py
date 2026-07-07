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
from nv_sensor_sim.datasets.hashing import content_md5
from nv_sensor_sim.datasets.schema import DatasetManifest
from nv_sensor_sim.datasets.writer import DatasetWriter
from nv_sensor_sim.dynamics.angle_stratified import sample_angle_stratified_ramp
from nv_sensor_sim.dynamics.coverage_geometry import (
    min_field_magnitude_T,
    offbias_angle_deg,
)
from nv_sensor_sim.dynamics.directed_crossing import sample_directed_crossing
from nv_sensor_sim.dynamics.dwell_trajectory import enumerate_dwell_templates
from nv_sensor_sim.dynamics.field_trajectory import (
    held_ramp_trajectory,
    ou_field_perturbation,
    ramp_crossing_trajectory,
    reversal_trajectory,
    sample_isotropic_held_ramp,
    sample_reversal_ramp,
    static_bias_vector,
)
from nv_sensor_sim.dynamics.render import render_multi_axis_frame, render_sequence
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.dynamics.sequence_stats import split_sequence_stats
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

# Trajectory families for the per-sequence mixture (isotropic mode). Canonical
# order fixes the family-selection stream's index -> name mapping.
_TRAJECTORY_FAMILIES = ("held", "reversal", "ou")

# Per-sequence derived rng spawn keys: geometry uses the bare seed inside the
# samplers; [seed, 1] = contrast drift, [seed, 2, k] = OU field perturbation
# (k = guard retry), [seed, 3] = family selection, [seed, 6] = sub-population
# (widened isotropic vs directed merge-crossing). Key 5 is the dwell jitter key.
_DRIFT_KEY, _OU_KEY, _FAMILY_KEY = 1, 2, 3
_SUBPOP_KEY = 6

# Per-sequence sampling-family integer codes (stored in the sampling_family array):
# 0 iso-held, 1 iso-reversal, 2 iso-ou, 3 directed-held, 4 directed-reversal.
_SAMPLING_FAMILY_CODE = {
    "held": 0,
    "reversal": 1,
    "ou": 2,
    "directed-held": 3,
    "directed-reversal": 4,
}


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


def _axis_scale_trajectory(
    axis_contrast_scale: tuple[float, ...] | None,
    drift_std: float,
    tau_frames: float,
    n_timesteps: int,
    n_axes: int,
    seed: int,
) -> np.ndarray | None:
    """Per-frame (T, A) axis MW-scale factors, static (A,) factors, or None.

    With drift enabled, each axis' factor follows a stationary AR(1) (discrete
    OU) around its nominal value with fractional std ``drift_std`` and
    correlation time ``tau_frames``. The drift stream is derived from the
    sequence seed on a separate spawn key so it does not perturb the geometry
    draws.
    """
    if axis_contrast_scale is None and drift_std <= 0.0:
        return None
    base = (
        np.ones(n_axes)
        if axis_contrast_scale is None
        else np.asarray(axis_contrast_scale, dtype=float)
    )
    if drift_std <= 0.0:
        return base
    rng = np.random.default_rng([seed, _DRIFT_KEY])
    alpha = float(np.exp(-1.0 / tau_frames))
    innov = np.sqrt(1.0 - alpha**2)
    x = np.empty((n_timesteps, n_axes))
    x[0] = rng.standard_normal(n_axes) * drift_std
    for t in range(1, n_timesteps):
        x[t] = alpha * x[t - 1] + innov * drift_std * rng.standard_normal(n_axes)
    return np.clip(base[None, :] * (1.0 + x), 0.05, None)


def _reference_line_depths(
    adapter: SimOSAdapter,
    bias_vec: np.ndarray,
    p1_ppm: float,
    extra_b_perp_T: float,
    nv_axes: np.ndarray,
    axis_contrast_scale: tuple[float, ...] | None,
) -> list[float]:
    """Per-line dip depths at the bias-only field (geometry-matrix order).

    Measured from the averaged multi-axis spectrum at each diagonalized line
    center, with nominal contrast scales and no drift. At the ~5 mT bias all 8
    lines are resolved (>= ~7 Gamma apart), so tail overlap is negligible.
    """
    scales = None if axis_contrast_scale is None else np.asarray(axis_contrast_scale, dtype=float)
    freqs, spec, centers = render_multi_axis_frame(
        adapter,
        bias_vec,
        p1_ppm=p1_ppm,
        extra_b_perp_T=extra_b_perp_T,
        nv_axes=nv_axes,
        axis_mw_scales=scales,
    )
    idx = np.abs(freqs[None, :] - centers[:, None]).argmin(axis=1)
    return [float(1.0 - spec[i]) for i in idx]


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
    sweep_mode: str = "fixed",
    sweep_scalar_range_T: tuple[float, float] | None = None,
    min_sweep_delta_T: float = 1.0e-3,
    min_ramp_window_frac: float = 0.25,
    min_axis_projection_T: float = 0.0,
    axis_contrast_scale: tuple[float, ...] | None = None,
    axis_contrast_drift_std: float = 0.0,
    axis_contrast_drift_tau_frames: float = 64.0,
    family_weights: tuple[float, float, float] = (1.0, 0.0, 0.0),
    reversal_turn_frac_range: tuple[float, float] = (0.2, 0.8),
    field_ou_sigma_T: float = 45.0e-6,
    field_ou_tau_frames: float = 16.0,
    min_field_T: float = 0.0,
    directed_fraction: float = 0.0,
    directed_approach_lw_range: tuple[float, float] = (3.0, 6.0),
    templates: list[dict] | None = None,
    window_pin_Hz: tuple[float, float] | None = None,
    D_hz: float = 0.0,
    gamma_hz_per_T: float = 0.0,
    window_margin_hz: float = 0.0,
    angle_max_deg: float = 62.0,
    field_range_T: tuple[float, float] = (3.0e-3, 6.0e-3),
    cold_start_fraction: float = 0.5,
    carry_start_max_deg: float = 15.0,
    carry_field_range_T: tuple[float, float] = (4.0e-3, 5.6e-3),
) -> tuple[dict[str, np.ndarray], int, dict[str, list]]:
    """Render every sequence in a split and stack into (N, T, ...) arrays.

    Returns the stacked arrays, the number of candidate geometries rejected by
    the envelope guards across the split, and per-sequence metadata (trajectory
    family, reversal turn frame or -1, OU wander metrics, and the v3 coverage
    labels: sampling-family code, realized max off-bias angle, min |B|, directed
    template index).
    """
    is_isotropic = sweep_mode in ("isotropic", "isotropic_widened")
    is_widened = sweep_mode == "isotropic_widened"
    guard_kw = dict(
        min_field_T=min_field_T,
        window_pin_Hz=window_pin_Hz,
        D_hz=D_hz,
        gamma_hz_per_T=gamma_hz_per_T,
        window_margin_hz=window_margin_hz,
    )
    floor_active = min_field_T > 0.0
    window_active = window_pin_Hz is not None

    def _traj_guards_ok(candidate: np.ndarray) -> bool:
        """Min-projection + |B| floor + window containment on a full trajectory."""
        if min_axis_projection_T > 0.0:
            proj = np.abs(candidate @ np.asarray(nv_axes, dtype=float).T)
            if float(proj.min()) < min_axis_projection_T:
                return False
        if floor_active and min_field_magnitude_T(candidate) < min_field_T:
            return False
        if window_active:
            from nv_sensor_sim.dynamics.coverage_geometry import max_line_offset_over_traj_hz

            allowed = min(D_hz - window_pin_Hz[0], window_pin_Hz[1] - D_hz) - window_margin_hz
            if max_line_offset_over_traj_hz(candidate, nv_axes, D_hz, gamma_hz_per_T) > allowed:
                return False
        return True

    def _apply_ou(base_traj: np.ndarray, seed: int) -> tuple[np.ndarray, float, float, int]:
        """Add the seeded OU perturbation to a held base, re-guarding the result.

        Returns ``(perturbed_traj, wander_std_lw, wander_inc8_p95_lw, n_rejected)``.
        Shared by the legacy-isotropic and angle-stratified ``ou`` families.
        """
        n_rej = 0
        ou = None
        for retry in range(500):
            ou = ou_field_perturbation(
                field_ou_sigma_T, field_ou_tau_frames, n_timesteps, seed=[int(seed), _OU_KEY, retry]
            )
            candidate = base_traj + ou
            if _traj_guards_ok(candidate):
                break
            n_rej += 1
        else:
            raise RuntimeError(
                "OU-perturbed trajectory failed the envelope guards 500 times; "
                "check field_ou_sigma_T vs the guards"
            )
        ou_proj = ou @ np.asarray(nv_axes, dtype=float).T  # (T, A)
        gamma_scale = GAMMA_HZ_PER_T / gamma_fwhm_hz
        std_lw = float(np.std(ou_proj) * gamma_scale)
        lag = min(8, n_timesteps - 1)
        inc = np.abs(ou_proj[lag:] - ou_proj[:-lag])
        inc8_lw = float(np.percentile(inc, 95) * gamma_scale)
        return candidate, std_lw, inc8_lw, n_rej

    n_split = len(split_seeds)
    per_seq: list[dict[str, np.ndarray]] = []
    frequencies: np.ndarray | None = None
    n_resamples = 0
    meta: dict[str, list] = {
        "family": [],
        "turn_frame": [],
        "ou_std_lw": [],
        "ou_inc8_lw": [],
        "sampling_family": [],
        "max_offbias_angle_deg": [],
        "min_B_T": [],
        "directed_template_idx": [],
        "start_mode": [],
    }

    print(f"Generating {n_split} sequences for {split_name} split...")
    for idx, seed in enumerate(split_seeds):
        family = "held"
        turn_frame = -1
        sampling_family = "held"
        directed_template_idx = -1
        start_mode = -1  # -1 = not applicable (directed / legacy-isotropic / fixed)
        # Sub-population assignment (widened mode only): a seed-derived bit selects
        # the directed merge-crossing sub-population. Drawn on a dedicated spawn
        # key so it never perturbs the geometry stream; skipped when off, so the
        # legacy isotropic path is byte-identical.
        is_directed = False
        if is_widened and directed_fraction > 0.0 and templates:
            sub_rng = np.random.default_rng([int(seed), _SUBPOP_KEY])
            is_directed = bool(sub_rng.random() < directed_fraction)

        if is_directed:
            traj, dmeta = sample_directed_crossing(
                templates,
                bias_T,
                n_timesteps,
                int(seed),
                approach_lw_range=directed_approach_lw_range,
                gamma_fwhm_hz=gamma_fwhm_hz,
                min_window_frac=min_ramp_window_frac,
                reversal_turn_frac_range=reversal_turn_frac_range,
                jitter_frac=jitter_frac,
                min_axis_projection_T=min_axis_projection_T,
                nv_axes=nv_axes,
                **guard_kw,
            )
            family = dmeta["family"]
            sampling_family = f"directed-{family}"
            directed_template_idx = int(dmeta["template_idx"])
        elif is_widened:
            # Angle-stratified widened sub-population (Amendment 1 Option A). The
            # v1-style family sets the ramp SHAPE; the geometry is drawn by
            # off-bias angle so the wide cone (>=60 deg) is actually covered.
            fam_rng = np.random.default_rng([int(seed), _FAMILY_KEY])
            family = _TRAJECTORY_FAMILIES[int(fam_rng.choice(3, p=family_weights))]
            sampling_family = family
            shape = "reversal" if family == "reversal" else "held"
            traj, smeta = sample_angle_stratified_ramp(
                bias_T,
                n_timesteps,
                int(seed),
                shape=shape,
                angle_max_deg=angle_max_deg,
                field_range_T=field_range_T,
                cold_start_fraction=cold_start_fraction,
                carry_start_max_deg=carry_start_max_deg,
                carry_field_range_T=carry_field_range_T,
                min_sweep_delta_T=min_sweep_delta_T,
                min_window_frac=min_ramp_window_frac,
                reversal_turn_frac_range=reversal_turn_frac_range,
                jitter_frac=jitter_frac,
                min_axis_projection_T=min_axis_projection_T,
                nv_axes=nv_axes,
                **guard_kw,
            )
            start_mode = int(smeta["start_mode"])
            if family == "ou":
                traj, std_lw, inc8_lw, n_rej = _apply_ou(traj, int(seed))
                n_resamples += n_rej
                meta["ou_std_lw"].append(std_lw)
                meta["ou_inc8_lw"].append(inc8_lw)
        elif is_isotropic:
            assert sweep_scalar_range_T is not None  # validated by the caller
            fam_rng = np.random.default_rng([int(seed), _FAMILY_KEY])
            family = _TRAJECTORY_FAMILIES[int(fam_rng.choice(3, p=family_weights))]
            sampling_family = family

            if family == "reversal":
                start, turn, end, t_turn, n_rej = sample_reversal_ramp(
                    sweep_scalar_range_T,
                    min_sweep_delta_T,
                    n_timesteps,
                    reversal_turn_frac_range,
                    seed=int(seed),
                    jitter_frac=jitter_frac,
                    bias_T=bias_T,
                    min_axis_proj_T=min_axis_projection_T,
                    nv_axes=nv_axes,
                    **guard_kw,
                )
                n_resamples += n_rej
                traj = reversal_trajectory(bias_T, start, turn, end, n_timesteps, t_turn)
                turn_frame = t_turn
            else:
                start, end, t0, t1, n_rej = sample_isotropic_held_ramp(
                    sweep_scalar_range_T,
                    min_sweep_delta_T,
                    n_timesteps,
                    min_ramp_window_frac,
                    seed=int(seed),
                    jitter_frac=jitter_frac,
                    bias_T=bias_T,
                    min_axis_proj_T=min_axis_projection_T,
                    nv_axes=nv_axes,
                    **guard_kw,
                )
                n_resamples += n_rej
                traj = held_ramp_trajectory(bias_T, start, end, n_timesteps, t0, t1)

            if family == "ou":
                traj, std_lw, inc8_lw, n_rej = _apply_ou(traj, int(seed))
                n_resamples += n_rej
                meta["ou_std_lw"].append(std_lw)
                meta["ou_inc8_lw"].append(inc8_lw)
        else:
            traj = ramp_crossing_trajectory(
                bias_T,
                ramp_start_T,
                ramp_end_T,
                n_timesteps,
                seed=int(seed),
                jitter_frac=jitter_frac,
            )
        meta["family"].append(family)
        meta["turn_frame"].append(turn_frame)
        meta["sampling_family"].append(_SAMPLING_FAMILY_CODE[sampling_family])
        meta["max_offbias_angle_deg"].append(float(offbias_angle_deg(traj, bias_T).max()))
        meta["min_B_T"].append(min_field_magnitude_T(traj))
        meta["directed_template_idx"].append(directed_template_idx)
        meta["start_mode"].append(start_mode)
        axis_scales = _axis_scale_trajectory(
            axis_contrast_scale,
            axis_contrast_drift_std,
            axis_contrast_drift_tau_frames,
            n_timesteps,
            len(nv_axes),
            int(seed),
        )
        out = render_sequence(
            adapter,
            traj,
            p1_ppm=p1_ppm,
            gamma_fwhm_hz=gamma_fwhm_hz,
            k=k,
            extra_b_perp_T=extra_b_perp_T,
            nv_axes=nv_axes,
            axis_mw_scales=axis_scales,
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
    return stacked, n_resamples, meta


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
    sweep_mode: str = "fixed",
    sweep_scalar_range_T: tuple[float, float] | None = None,
    min_sweep_delta_T: float = 1.0e-3,
    min_ramp_window_frac: float = 0.25,
    min_axis_projection_T: float = 0.0,
    min_field_T: float = 0.0,
    directed_fraction: float = 0.0,
    directed_approach_lw_range: tuple[float, float] = (3.0, 6.0),
    window_margin_frac: float = 0.0,
    offbias_angle_target_deg: float | None = None,
    field_range_T: tuple[float, float] = (3.0e-3, 6.0e-3),
    cold_start_fraction: float = 0.5,
    carry_start_max_deg: float = 15.0,
    carry_field_range_T: tuple[float, float] = (4.0e-3, 5.6e-3),
    jitter_frac: float = 0.05,
    axis_contrast_scale: tuple[float, ...] | None = None,
    axis_contrast_drift_std: float = 0.0,
    axis_contrast_drift_tau_frames: float = 64.0,
    trajectory_family_weights: dict[str, float] | None = None,
    reversal_turn_frac_range: tuple[float, float] = (0.2, 0.8),
    field_ou_sigma_T: float = 45.0e-6,
    field_ou_tau_frames: float = 16.0,
    collision_threshold_linewidths: float = 1.0,
    extra_b_perp_T: float = 0.0,
    hyperfine: bool = False,
    freq_range_Hz: tuple[float, float] | None = None,
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
        External swept-field 3-vectors (Tesla) at first and last frame
        (``sweep_mode="fixed"`` only; ignored for ``"isotropic"``).
    sweep_mode : str
        ``"fixed"`` (default): every sequence ramps between the configured
        endpoints over the whole sequence, with endpoint jitter.
        ``"isotropic"``: each sequence draws its own held ramp — direction
        ``u`` uniform on the sphere, independent endpoint scalars from
        ``sweep_scalar_range_T`` along ``u``, ramping over a random
        sub-interval of the sequence and holding outside it (see
        ``sample_isotropic_held_ramp``) — so crossing geometry, crossing time,
        crossing count (including none), and ramp rate all vary.
    sweep_scalar_range_T : tuple[float, float], optional
        ``(lo, hi)`` uniform range (Tesla) for the signed endpoint scalars.
        Required for ``sweep_mode="isotropic"``.
    min_sweep_delta_T : float
        Minimum ``|s_end - s_start|`` (Tesla) so every sequence has motion
        (isotropic mode only).
    min_ramp_window_frac : float
        Minimum ramp-window length as a fraction of the sequence (isotropic
        mode only).
    min_axis_projection_T : float
        Reject-and-resample ramp geometries whose total field would drive any
        NV axis' ``|B . n_i|`` below this (Tesla) anywhere along the ramp —
        near a projection zero the diagonalized labels jump discontinuously.
        0.0 disables the guard (isotropic mode only).
    jitter_frac : float
        Per-sequence fractional jitter on the ramp endpoints.
    axis_contrast_scale : tuple[float, ...], optional
        Per-axis MW Rabi-amplitude factors (length = number of NV axes),
        modelling the MW polarization projecting differently onto each axis.
        Contrast follows via saturation (C ~ s/(1+s)); weaker-driven axes also
        render slightly narrower. None (default) drives all axes uniformly —
        the maximally-ambiguous case. Reference per-line depths are recorded
        in the manifest (``line_depths``).
    axis_contrast_drift_std : float
        Fractional std of a slow per-sequence AR(1) drift multiplied onto the
        axis factors (0.0 = static factors, the default).
    axis_contrast_drift_tau_frames : float
        Drift correlation time in frames (used when the drift std is > 0).
    trajectory_family_weights : dict[str, float], optional
        Per-sequence trajectory-family mixture for isotropic mode, keyed by
        ``"held"`` (hold-ramp-hold), ``"reversal"`` (ramp out, turn around,
        ramp back — field velocity crosses zero, revisiting the crossing
        region), and ``"ou"`` (held ramp plus a seeded OU field perturbation).
        Weights are normalized; None (default) = 100% held. The family is
        drawn per sequence from a seed-derived stream and recorded in the
        manifest. The min-projection guard and window-containment asserts
        apply to every family.
    reversal_turn_frac_range : tuple[float, float]
        Turn-frame range for reversal sequences as fractions of the sequence
        (default the middle 60%).
    field_ou_sigma_T : float
        Stationary per-component std (Tesla) of the OU field perturbation
        (``"ou"`` family). Default 45 uT ~ 0.84 linewidths of resonance wander.
    field_ou_tau_frames : float
        OU correlation time in frames (default 16, the collision dwell scale).
    collision_threshold_linewidths : float
        k in the ``|f_i - f_j| < k * Gamma`` collision rule. The threshold uses
        the *intrinsic* linewidth and applies to ALL line pairs, including the
        two transitions of the same axis.
    extra_b_perp_T : float
        Additional stray transverse field beyond the geometric projection.
    hyperfine : bool
        14N hyperfine (L=24). Not implemented for v0 (raises).
    freq_range_Hz : tuple[float, float], optional
        Explicit MW window pin (Hz). When set, the window derivation is
        bypassed; generation refuses to start unless the derived worst-case
        window fits inside the pin. Use to hold the frequency grid fixed
        across lineages (e.g. pin v1 to v0's grid).
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
    if sweep_mode not in ("fixed", "isotropic", "isotropic_widened"):
        raise ValueError(
            f"sweep_mode must be 'fixed', 'isotropic', or 'isotropic_widened', got {sweep_mode!r}"
        )
    is_isotropic = sweep_mode in ("isotropic", "isotropic_widened")
    is_widened = sweep_mode == "isotropic_widened"
    if not 0.0 < min_ramp_window_frac <= 1.0:
        raise ValueError(f"min_ramp_window_frac must be in (0, 1], got {min_ramp_window_frac}")
    if is_widened:
        # Angle-stratified widening (Amendment 1 Option A): geometry is drawn by
        # off-bias angle + |B| law, so sweep_scalar_range_T is not required (a
        # nominal is derived for the window-derivation / dry-run only).
        if not 0.0 <= directed_fraction <= 1.0:
            raise ValueError(f"directed_fraction must be in [0, 1], got {directed_fraction}")
        if min_field_T < 0.0:
            raise ValueError(f"min_field_T must be >= 0, got {min_field_T}")
        if min_sweep_delta_T <= 0.0:
            raise ValueError(f"min_sweep_delta_T must be > 0, got {min_sweep_delta_T}")
        d_lo, d_hi = float(directed_approach_lw_range[0]), float(directed_approach_lw_range[1])
        if not 0.0 < d_lo <= d_hi:
            raise ValueError(
                f"directed_approach_lw_range must satisfy 0 < lo <= hi, got ({d_lo}, {d_hi})"
            )
        directed_approach_lw_range = (d_lo, d_hi)
        if not 0.0 <= window_margin_frac < 1.0:
            raise ValueError(f"window_margin_frac must be in [0, 1), got {window_margin_frac}")
        fr_lo, fr_hi = float(field_range_T[0]), float(field_range_T[1])
        if not 0.0 < fr_lo < fr_hi:
            raise ValueError(f"field_range_T must satisfy 0 < lo < hi, got ({fr_lo}, {fr_hi})")
        field_range_T = (fr_lo, fr_hi)
        cr_lo, cr_hi = float(carry_field_range_T[0]), float(carry_field_range_T[1])
        if not 0.0 < cr_lo < cr_hi:
            raise ValueError(f"carry_field_range_T must satisfy 0 < lo < hi, got ({cr_lo}, {cr_hi})")
        carry_field_range_T = (cr_lo, cr_hi)
        if not 0.0 <= cold_start_fraction <= 1.0:
            raise ValueError(f"cold_start_fraction must be in [0, 1], got {cold_start_fraction}")
        if not 0.0 < carry_start_max_deg < 90.0:
            raise ValueError(f"carry_start_max_deg must be in (0, 90), got {carry_start_max_deg}")
        if offbias_angle_target_deg is None:
            offbias_angle_target_deg = 62.0
        if not 0.0 < offbias_angle_target_deg <= 90.0:
            raise ValueError(
                f"offbias_angle_target_deg must be in (0, 90], got {offbias_angle_target_deg}"
            )
        if sweep_scalar_range_T is None:
            sweep_scalar_range_T = (-fr_hi, fr_hi)  # nominal (unused for geometry)
    elif directed_fraction > 0.0:
        raise ValueError("directed_fraction > 0 requires sweep_mode='isotropic_widened'")
    if is_isotropic:
        if sweep_scalar_range_T is None:
            raise ValueError(f"sweep_mode={sweep_mode!r} requires sweep_scalar_range_T=(lo, hi)")
        s_lo, s_hi = float(sweep_scalar_range_T[0]), float(sweep_scalar_range_T[1])
        if not s_lo < s_hi:
            raise ValueError(f"sweep_scalar_range_T must satisfy lo < hi, got ({s_lo}, {s_hi})")
        if not 0.0 < min_sweep_delta_T <= s_hi - s_lo:
            raise ValueError(
                f"min_sweep_delta_T must satisfy 0 < delta <= hi - lo = {s_hi - s_lo}, "
                f"got {min_sweep_delta_T}"
            )
        sweep_scalar_range_T = (s_lo, s_hi)
    if axis_contrast_scale is not None:
        scale_tuple = tuple(float(v) for v in axis_contrast_scale)
        if len(scale_tuple) != len(NV_AXES_UNIT):
            raise ValueError(
                f"axis_contrast_scale must have {len(NV_AXES_UNIT)} entries, got {len(scale_tuple)}"
            )
        if any(v <= 0.0 for v in scale_tuple):
            raise ValueError(f"axis_contrast_scale entries must be > 0, got {scale_tuple}")
        axis_contrast_scale = scale_tuple
    if axis_contrast_drift_std < 0.0:
        raise ValueError(f"axis_contrast_drift_std must be >= 0, got {axis_contrast_drift_std}")
    if axis_contrast_drift_std > 0.0 and axis_contrast_drift_tau_frames <= 0.0:
        raise ValueError(
            f"axis_contrast_drift_tau_frames must be > 0, got {axis_contrast_drift_tau_frames}"
        )

    # Trajectory-family mixture (isotropic mode): normalize to the canonical
    # ("held", "reversal", "ou") order.
    if trajectory_family_weights is not None and not is_isotropic:
        raise ValueError(
            "trajectory_family_weights requires sweep_mode='isotropic' or 'isotropic_widened'"
        )
    if trajectory_family_weights is None:
        family_weights = (1.0, 0.0, 0.0)
    else:
        unknown = set(trajectory_family_weights) - set(_TRAJECTORY_FAMILIES)
        if unknown:
            raise ValueError(
                f"unknown trajectory families {sorted(unknown)}; "
                f"expected keys from {_TRAJECTORY_FAMILIES}"
            )
        raw = [float(trajectory_family_weights.get(f, 0.0)) for f in _TRAJECTORY_FAMILIES]
        if any(w < 0.0 for w in raw) or sum(raw) <= 0.0:
            raise ValueError(f"trajectory_family_weights must be non-negative and sum > 0: {raw}")
        total_w = sum(raw)
        family_weights = (raw[0] / total_w, raw[1] / total_w, raw[2] / total_w)
        if family_weights[1] > 0.0 and n_timesteps < 3:
            raise ValueError("reversal family requires n_timesteps >= 3")
        if family_weights[2] > 0.0:
            if field_ou_sigma_T <= 0.0:
                raise ValueError(f"field_ou_sigma_T must be > 0, got {field_ou_sigma_T}")
            if field_ou_tau_frames <= 0.0:
                raise ValueError(f"field_ou_tau_frames must be > 0, got {field_ou_tau_frames}")
        tf_lo, tf_hi = float(reversal_turn_frac_range[0]), float(reversal_turn_frac_range[1])
        if not 0.0 < tf_lo < tf_hi < 1.0:
            raise ValueError(
                f"reversal_turn_frac_range must satisfy 0 < lo < hi < 1, got ({tf_lo}, {tf_hi})"
            )
        reversal_turn_frac_range = (tf_lo, tf_hi)

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

    if is_isotropic:
        # Worst case over all ramp directions: an endpoint of maximum |s| can
        # land parallel (or perpendicular) to any axis, on top of the bias
        # projection. Jitter (3 sigma, scaled to the max ramp length) inflates
        # only the sampled sweep; the bias is exact. The OU-family field
        # perturbation (sigma ~ tens of uT ~ 1 linewidth in frequency) is
        # deliberately NOT part of this nominal envelope — the post-render
        # per-split label-containment assert covers it empirically.
        assert sweep_scalar_range_T is not None  # validated above
        b_par_bias, b_perp_bias = project_field_onto_axes(bias_vec, nv_axes=nv_axes)
        s_abs_max = max(abs(sweep_scalar_range_T[0]), abs(sweep_scalar_range_T[1]))
        delta_max = sweep_scalar_range_T[1] - sweep_scalar_range_T[0]
        s_eff = s_abs_max + 3.0 * jitter_frac * delta_max
        b_par_max = float(np.max(np.abs(b_par_bias))) + s_eff
        b_perp_max = float(np.max(b_perp_bias)) + s_eff
    else:
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
    needed_range = (D_hz - half_window, D_hz + half_window)

    if freq_range_Hz is not None:
        pin_lo, pin_hi = float(freq_range_Hz[0]), float(freq_range_Hz[1])
        if not pin_lo < pin_hi:
            raise ValueError(f"freq_range_Hz must satisfy lo < hi, got ({pin_lo}, {pin_hi})")
        if (pin_lo > needed_range[0] or pin_hi < needed_range[1]) and not is_widened:
            raise ValueError(
                f"pinned freq_range_Hz [{pin_lo / 1e9:.4f}, {pin_hi / 1e9:.4f}] GHz does not "
                f"contain the derived worst-case window "
                f"[{needed_range[0] / 1e9:.4f}, {needed_range[1] / 1e9:.4f}] GHz for this "
                f"sweep; widen the pin or shrink the sweep"
            )
        if is_widened:
            # The widened worst-case (scalar parallel to an axis) intentionally
            # exceeds the pin; the per-frame window-containment guard keeps every
            # accepted geometry inside it, and the post-render label-containment
            # assert is the exact backstop.
            print(
                f"widened envelope: skipping config-time worst-case containment (derived "
                f"half-window {half_window / 1e6:.1f} MHz vs pinned "
                f"{(pin_hi - pin_lo) / 2e6:.1f} MHz); per-frame window guard enforces the pin"
            )
        freq_range = (pin_lo, pin_hi)
    else:
        freq_range = needed_range

    if n_freq_points is None:
        span = freq_range[1] - freq_range[0]
        n_freq_points = int(np.ceil(span / (gamma_fwhm_hz / aliasing_safety))) + 1

    window_kind = "pinned" if freq_range_Hz is not None else "derived"
    print(
        f"D={D_hz / 1e9:.5f} GHz  Gamma={gamma_fwhm_hz / 1e6:.4f} MHz  "
        f"window=[{freq_range[0] / 1e9:.4f}, {freq_range[1] / 1e9:.4f}] GHz ({window_kind})  "
        f"F={n_freq_points}  step={(freq_range[1] - freq_range[0]) / (n_freq_points - 1) / 1e6:.4f} MHz"
    )

    # --- Widened envelope: per-frame guard params + directed merge templates ---
    window_pin_for_guard = freq_range if is_widened else None
    half_window_hz = 0.5 * (freq_range[1] - freq_range[0])
    window_margin_hz = window_margin_frac * half_window_hz if is_widened else 0.0
    templates: list[dict] = []
    if is_widened and directed_fraction > 0.0:
        plan_cfg = SimulationConfig(
            use_optics=False,
            include_nitrogen=False,
            temperature_K=temperature_K,
            n_freq_points=41,
            mw_freq_range_Hz=freq_range,
        )
        plan_adapter = SimOSAdapter(plan_cfg)
        templates = enumerate_dwell_templates(
            plan_adapter,
            bias_vec,
            approach_linewidths=directed_approach_lw_range[1],
            gamma_fwhm_hz=gamma_fwhm_hz,
            sep_min_linewidths=1.5,
            min_axis_projection_T=min_axis_projection_T,
            nv_axes=nv_axes,
        )
        if not templates:
            raise RuntimeError(
                "directed sub-population requested but no viable cross-axis merge templates "
                "exist at this bias/grid; loosen sep_min or set directed_fraction=0"
            )
        print(
            f"directed sub-population: {len(templates)} merge templates "
            f"(pairs {[(t['p'], t['q']) for t in templates]}); "
            f"target directed fraction {directed_fraction:.0%}"
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
    # Fixed mode keeps the original hash-string layout so existing lineages
    # (e.g. sequence_sanity_v0) rehash identically.
    if sweep_mode == "isotropic":
        sweep_cfg = (
            f"isotropic:{sweep_scalar_range_T}:{min_sweep_delta_T}:{min_ramp_window_frac}"
            f":{min_axis_projection_T}"
        )
    elif sweep_mode == "isotropic_widened":
        sweep_cfg = (
            f"isotropic_widened:{sweep_scalar_range_T}:{min_sweep_delta_T}:{min_ramp_window_frac}"
            f":{min_axis_projection_T}:floor={min_field_T}:directed={directed_fraction}"
            f":{directed_approach_lw_range}:wmargin={window_margin_frac}"
        )
    else:
        sweep_cfg = f"{ramp_start_T}:{ramp_end_T}"
    config_str = (
        f"{master_seed}:{n_timesteps}:{dt_s}:{p1_ppm}:{bias_B0_T}:{bias_direction_uvw}"
        f":{sweep_cfg}:{collision_threshold_linewidths}:{freq_range}"
    )
    # Appended only when the contrast knob / family mixture is active, so
    # legacy configs rehash identically.
    if axis_contrast_scale is not None or axis_contrast_drift_std > 0.0:
        config_str += (
            f":contrast:{axis_contrast_scale}:{axis_contrast_drift_std}"
            f":{axis_contrast_drift_tau_frames}"
        )
    if family_weights != (1.0, 0.0, 0.0):
        config_str += (
            f":families:{family_weights}:{reversal_turn_frac_range}"
            f":{field_ou_sigma_T}:{field_ou_tau_frames}"
        )
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

    if not sweep_description:
        if is_isotropic:
            assert sweep_scalar_range_T is not None  # validated above
            s_lo_mt = sweep_scalar_range_T[0] * 1e3
            s_hi_mt = sweep_scalar_range_T[1] * 1e3
            fam_desc = ""
            if family_weights != (1.0, 0.0, 0.0):
                fam_desc = (
                    f"; family mix held/reversal/ou = {family_weights[0]:.2f}/"
                    f"{family_weights[1]:.2f}/{family_weights[2]:.2f} (reversal turns in "
                    f"the middle {reversal_turn_frac_range} of the sequence; ou adds a "
                    f"seeded OU field perturbation sigma={field_ou_sigma_T * 1e6:.0f} uT, "
                    f"tau={field_ou_tau_frames:.0f} frames)"
                )
            pin_desc = ""
            if is_widened:
                pin_desc = (
                    f"; WIDENED off-bias envelope with per-frame reject guards (|B| floor "
                    f"{min_field_T * 1e3:.2f} mT, window containment to the pinned grid, "
                    f"min per-axis |B.n| {min_axis_projection_T * 1e3:.2f} mT) so the cone "
                    f"reaches the increment-5 failure geometry; {directed_fraction:.0%} directed "
                    f"merge-crossings aimed at the cross-axis degeneracies "
                    f"(approach {directed_approach_lw_range[0]:.0f}-{directed_approach_lw_range[1]:.0f} "
                    f"linewidths)"
                )
            elif freq_range_Hz is not None:
                pin_desc = (
                    f"; scalar range capped at {s_hi_mt:.2f} mT so the derived worst-case "
                    f"window fits the pinned frequency grid"
                )
            sweep_description = (
                f"per-sequence isotropic held ramp: direction u uniform on the sphere, "
                f"independent endpoints s_start,s_end ~ U[{s_lo_mt:.2f}, {s_hi_mt:.2f}] mT "
                f"along u with |s_end-s_start| >= {min_sweep_delta_T * 1e3:.2f} mT, linear "
                f"ramp over a random sub-interval >= {min_ramp_window_frac:.0%} of "
                f"{n_timesteps} frames (held outside), on a {bias_B0_T * 1e3:.2f} mT bias "
                f"along {bias_direction_uvw}; jitter_frac={jitter_frac}{fam_desc}{pin_desc}"
            )
        else:
            sweep_description = (
                f"linear ramp of external field {ramp_start_T}->{ramp_end_T} T over "
                f"{n_timesteps} frames on a {bias_B0_T * 1e3:.2f} mT bias along "
                f"{bias_direction_uvw}; jitter_frac={jitter_frac}"
            )

    # Angle-stratified widening law (Amendment 1 Option A) — records the training
    # DENSITY change vs v1/v2 isotropic sampling for increment-6 attribution.
    stratification_law = None
    if is_widened:
        stratification_law = {
            "method": "angle_stratified_option_A",
            "offbias_angle_deg": f"U[0,{offbias_angle_target_deg}]",
            "field_magnitude_T": f"U[{field_range_T[0]},{field_range_T[1]}]",
            "cold_start_fraction": cold_start_fraction,
            "carry_start_offbias_deg": f"U[0,{carry_start_max_deg}]",
            "carry_field_magnitude_T": f"U[{carry_field_range_T[0]},{carry_field_range_T[1]}]",
            "directed_fraction": directed_fraction,
            "min_field_floor_T": min_field_T,
            "note": (
                "Density change vs v1/v2 isotropic sampling: off-bias ANGLE drawn "
                "uniformly (not direction isotropic on the sphere). A cold_start_fraction "
                "of sequences begins frame-0 at the drawn (possibly wide) stratum "
                "(acquisition); the rest carry a lock outward from the near-bias cone. "
                "Start mode recorded per sequence (0=acquire, 1=carry, -1=directed)."
            ),
        }

    # Rendered lines are power-broadened by the MW drive; labels keep the
    # intrinsic Gamma (v0 convention) but both are recorded. Mirrors the
    # adapter's saturation model: Gamma_rendered = Gamma * sqrt(1 + s0) at
    # mw_scale = 1.
    mw_s0 = float(getattr(probe_cfg, "base_saturation_s0", 0.1))
    linewidth_rendered_hz = gamma_fwhm_hz * float(np.sqrt(1.0 + mw_s0))

    manifest = DatasetManifest(
        generator_git_sha=_get_git_sha(),
        config_hash=config_hash,
        simos_version=simos_ver,
        qutip_version=qutip_ver,
        numpy_version=np.__version__,
        backend="qutip",
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        contract_version="v1",
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
        linewidth_rendered_Hz=linewidth_rendered_hz,
        mw_saturation_s0=mw_s0,
        collision_threshold_linewidths=collision_threshold_linewidths,
        sweep_description=sweep_description,
        # Structured sweep geometry (sweep_description keeps the prose)
        sweep_mode=sweep_mode,
        sweep_scalar_range_T=sweep_scalar_range_T if is_isotropic else None,
        min_sweep_delta_T=min_sweep_delta_T if is_isotropic else None,
        min_ramp_window_frac=min_ramp_window_frac if is_isotropic else None,
        min_axis_projection_T=min_axis_projection_T if is_isotropic else None,
        ramp_start_T=ramp_start_T if sweep_mode == "fixed" else None,
        ramp_end_T=ramp_end_T if sweep_mode == "fixed" else None,
        jitter_frac=jitter_frac,
        # v3 widened-envelope keys (None unless sweep_mode='isotropic_widened')
        min_field_T=min_field_T if is_widened else None,
        directed_fraction=directed_fraction if is_widened else None,
        directed_approach_lw_range=directed_approach_lw_range if is_widened else None,
        offbias_angle_target_deg=offbias_angle_target_deg if is_widened else None,
        window_margin_frac=window_margin_frac if is_widened else None,
        stratification_law=stratification_law,
        axis_contrast_scale=axis_contrast_scale,
        axis_contrast_drift_std=(
            axis_contrast_drift_std if axis_contrast_drift_std > 0.0 else None
        ),
        axis_contrast_drift_tau_frames=(
            axis_contrast_drift_tau_frames if axis_contrast_drift_std > 0.0 else None
        ),
        trajectory_family_weights=(
            dict(zip(_TRAJECTORY_FAMILIES, family_weights))
            if family_weights != (1.0, 0.0, 0.0)
            else None
        ),
        reversal_turn_frac_range=(reversal_turn_frac_range if family_weights[1] > 0.0 else None),
        field_ou_sigma_T=field_ou_sigma_T if family_weights[2] > 0.0 else None,
        field_ou_tau_frames=field_ou_tau_frames if family_weights[2] > 0.0 else None,
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

    # Reference per-line depths at the bias-only field (nominal scales, no
    # drift) — records the contrast-asymmetry fingerprint downstream baselines
    # may exploit.
    manifest.line_depths = _reference_line_depths(
        adapter, bias_vec, p1_ppm, extra_b_perp_T, nv_axes, axis_contrast_scale
    )

    n_dry = min(10, n_timesteps)
    if is_isotropic:
        # Representative sampled ramp; per-frame cost is field-independent.
        assert sweep_scalar_range_T is not None  # validated above
        dry_start, dry_end, dry_t0, dry_t1, _ = sample_isotropic_held_ramp(
            sweep_scalar_range_T,
            min_sweep_delta_T,
            n_timesteps,
            min_ramp_window_frac,
            seed=master_seed,
            jitter_frac=jitter_frac,
        )
        dry_traj = held_ramp_trajectory(bias_vec, dry_start, dry_end, n_timesteps, dry_t0, dry_t1)
    else:
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
    sequence_stats: dict[str, dict] = {}
    total_resamples = 0
    md5_arrays: dict[str, np.ndarray] = {}  # widened mode: reproducible data_md5
    for split_name, split_seeds in splits:
        if len(split_seeds) == 0:
            continue
        data, split_resamples, seq_meta = _generate_sequence_split(
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
            sweep_mode=sweep_mode,
            sweep_scalar_range_T=sweep_scalar_range_T,
            min_sweep_delta_T=min_sweep_delta_T,
            min_ramp_window_frac=min_ramp_window_frac,
            min_axis_projection_T=min_axis_projection_T,
            axis_contrast_scale=axis_contrast_scale,
            axis_contrast_drift_std=axis_contrast_drift_std,
            axis_contrast_drift_tau_frames=axis_contrast_drift_tau_frames,
            family_weights=family_weights,
            reversal_turn_frac_range=reversal_turn_frac_range,
            field_ou_sigma_T=field_ou_sigma_T,
            field_ou_tau_frames=field_ou_tau_frames,
            min_field_T=min_field_T,
            directed_fraction=directed_fraction,
            directed_approach_lw_range=directed_approach_lw_range,
            templates=templates,
            window_pin_Hz=window_pin_for_guard,
            D_hz=D_hz,
            gamma_hz_per_T=GAMMA_HZ_PER_T,
            window_margin_hz=window_margin_hz,
            angle_max_deg=(offbias_angle_target_deg or 62.0),
            field_range_T=field_range_T,
            cold_start_fraction=cold_start_fraction,
            carry_start_max_deg=carry_start_max_deg,
            carry_field_range_T=carry_field_range_T,
        )
        total_resamples += split_resamples

        # Every stored label must lie on the frequency grid, pinned or derived.
        res_lo = float(data["resonance_freqs"].min())
        res_hi = float(data["resonance_freqs"].max())
        if res_lo < freq_range[0] or res_hi > freq_range[1]:
            raise RuntimeError(
                f"[{split_name}] resonance labels leave the MW window: labels span "
                f"[{res_lo / 1e9:.4f}, {res_hi / 1e9:.4f}] GHz vs freq_range "
                f"[{freq_range[0] / 1e9:.4f}, {freq_range[1] / 1e9:.4f}] GHz"
            )

        stats = split_sequence_stats(
            data["resonance_freqs"],
            data["collision_mask"],
            data["B_true"],
            gamma_fwhm_hz,
            nv_axes=nv_axes,
        )
        stats["n_ramp_resamples"] = int(split_resamples)

        # Trajectory-family bookkeeping: per-sequence family, reversal turn
        # frames, reversals landing inside a collision dwell, per-family
        # stratified summaries, and achieved OU wander.
        families = seq_meta["family"]
        turn_frames = seq_meta["turn_frame"]
        stats["trajectory_family_per_sequence"] = families
        stats["reversal_turn_frame_per_sequence"] = turn_frames
        cc_per_seq = np.asarray(stats["crossing_count_per_sequence"])
        coll = np.asarray(data["collision_mask"], dtype=bool)
        res = np.asarray(data["resonance_freqs"], dtype=float)
        min_split_per_seq = np.abs(res[:, :, 0::2] - res[:, :, 1::2]).min(axis=(1, 2))
        rev_in_dwell = sum(1 for s, tf in enumerate(turn_frames) if tf >= 0 and bool(coll[s, tf]))
        stats["n_reversal_sequences"] = int(sum(1 for f in families if f == "reversal"))
        stats["n_reversals_inside_collision_dwell"] = int(rev_in_dwell)
        fam_arr = np.asarray(families)
        family_blocks: dict[str, dict] = {}
        for fam in _TRAJECTORY_FAMILIES:
            mask = fam_arr == fam
            n_fam = int(mask.sum())
            if n_fam == 0:
                family_blocks[fam] = {"n": 0}
                continue
            cc_f = cc_per_seq[mask]
            family_blocks[fam] = {
                "n": n_fam,
                "no_crossing_fraction": float(np.mean(cc_f == 0)),
                "crossing_count_mean": float(cc_f.mean()),
                "collision_frame_fraction_mean": float(coll[mask].mean()),
                "n_near_merge_sequences": int(
                    (min_split_per_seq[mask] < 2.0 * gamma_fwhm_hz).sum()
                ),
            }
        if seq_meta["ou_std_lw"]:
            family_blocks["ou"]["wander_std_linewidths_mean"] = float(
                np.mean(seq_meta["ou_std_lw"])
            )
            family_blocks["ou"]["wander_dwell8_p95_linewidths_mean"] = float(
                np.mean(seq_meta["ou_inc8_lw"])
            )
        stats["family_stats"] = family_blocks

        # --- v3 widened-envelope coverage labels + stats (widened mode only) ---
        per_sequence: dict[str, np.ndarray] | None = None
        if is_widened:
            sf = np.asarray(seq_meta["sampling_family"], dtype=np.int8)
            ang = np.asarray(seq_meta["max_offbias_angle_deg"], dtype=np.float32)
            min_b = np.asarray(seq_meta["min_B_T"], dtype=np.float32)
            dti = np.asarray(seq_meta["directed_template_idx"], dtype=np.int8)
            sm = np.asarray(seq_meta["start_mode"], dtype=np.int8)
            per_sequence = {
                "sampling_family": sf,
                "max_offbias_angle_deg": ang,
                "min_B_T": min_b,
                "directed_template_idx": dti,
                "start_mode": sm,
            }
            n_directed = int((dti >= 0).sum())
            stats["coverage"] = {
                "offbias_angle_deg": {
                    "min": float(ang.min()),
                    "mean": float(ang.mean()),
                    "max": float(ang.max()),
                    "frac_ge_41_5": float(np.mean(ang >= 41.5)),
                    "frac_ge_53_2": float(np.mean(ang >= 53.2)),
                    "frac_ge_60": float(np.mean(ang >= 60.0)),
                },
                "field_magnitude_mT": {
                    "min": float(min_b.min() * 1e3),
                    "mean": float(min_b.mean() * 1e3),
                    "max": float(min_b.max() * 1e3),
                },
                "n_directed": n_directed,
                "n_isotropic": int(len(sf) - n_directed),
                "directed_fraction_realized": (float(n_directed / len(sf)) if len(sf) else 0.0),
                "n_acquire": int((sm == 0).sum()),
                "n_carry": int((sm == 1).sum()),
                "cold_start_fraction_realized": (
                    float((sm == 0).sum() / max(1, (sm >= 0).sum()))
                ),
                "sampling_family_counts": {
                    name: int((sf == code).sum()) for name, code in _SAMPLING_FAMILY_CODE.items()
                },
                "directed_template_counts": {
                    int(t): int((dti == t).sum()) for t in sorted(set(dti[dti >= 0].tolist()))
                },
            }
        sequence_stats[split_name] = stats

        cov_msg = ""
        if is_widened:
            cov = stats["coverage"]
            cov_msg = (
                f", off-bias max {cov['offbias_angle_deg']['max']:.1f} deg "
                f"(>=60 {cov['offbias_angle_deg']['frac_ge_60']:.0%}), |B| min "
                f"{cov['field_magnitude_mT']['min']:.2f} mT, directed {cov['n_directed']}"
            )
        print(
            f"  {split_name} labels: no-crossing {stats['no_crossing_fraction']:.1%}, "
            f"crossings/seq mean {stats['crossing_count']['mean']:.1f}, "
            f"collision frames mean {stats['collision_frame_fraction'].get('mean', 0.0):.2%}, "
            f"near-merge seqs {stats['n_near_merge_sequences']}/{stats['n_sequences']}, "
            f"ramp resamples {split_resamples}, families "
            f"h/r/o {family_blocks['held'].get('n', 0)}/{family_blocks['reversal'].get('n', 0)}"
            f"/{family_blocks['ou'].get('n', 0)}, reversals-in-dwell {rev_in_dwell}{cov_msg}"
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
            per_sequence=per_sequence,
        )
        if is_widened:
            for key in _SEQ_ARRAY_KEYS:
                md5_arrays[f"{split_name}/{key}"] = data[key]
            md5_arrays[f"{split_name}/seeds"] = data["seeds"]
            md5_arrays["frequencies"] = data["frequencies"]
            for k, v in (per_sequence or {}).items():
                md5_arrays[f"{split_name}/per_seq/{k}"] = v

    # Label statistics + guard counters are known only after rendering.
    manifest.sequence_stats = sequence_stats
    manifest.n_ramp_resamples = total_resamples
    if is_widened:
        md5_arrays["bias"] = bias_vec
        manifest.data_md5 = content_md5(md5_arrays)
    writer.write_manifest(manifest)
    output_path = writer.finalize()
    md5_msg = f" (data_md5 {manifest.data_md5})" if manifest.data_md5 else ""
    print(f"Sequence dataset written to {output_path}{md5_msg}")
    return output_path


if __name__ == "__main__":
    generate_sequence_dataset("./data/sequence_v0")
