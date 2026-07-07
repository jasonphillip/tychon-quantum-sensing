"""Directed merge-crossing trajectories for the v3 widened envelope.

The directed sub-population aims v1-style pass-through crossings *at* the
cross-axis merge geometries the tracker fails on (increment-5: pairs (0,2)/(4,6),
41.5deg/53.2deg off-bias, 3.9/3.3 mT). It reuses the dwell merge machinery
(``merge_direction`` / ``first_order_a_merge`` / ``delta_a_for_separation``) to
drive one chosen pair along ``w_hat`` **through** its degeneracy ``a_merge`` — but
without the sustained D-frame hold of the dwell eval. Two flavors:

- ``held``  — a hold-ramp-hold that ramps from ``a_merge + s*delta`` through
  ``a_merge`` to ``a_merge - s*delta``: the pair separation changes sign (the
  lines swap), a cross.
- ``reversal`` — ramps in to ``a_merge`` and back to the entry side: the field
  reverses at the degeneracy, a bounce (velocity-ambiguous).

The merge *direction* is used exactly (no ``w_hat`` jitter) so the trajectory hits
the exact failure geometry; only the approach distance, exit family/sign, and ramp
timing vary per sequence. The same three envelope guards as the isotropic sampler
apply (|B| floor, window containment, min per-axis projection); kinematics are
redrawn on rejection.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.dynamics.coverage_geometry import (
    max_line_offset_over_traj_hz,
    min_field_magnitude_T,
)
from nv_sensor_sim.dynamics.dwell_trajectory import delta_a_for_separation
from nv_sensor_sim.dynamics.field_trajectory import (
    held_ramp_trajectory,
    reversal_trajectory,
)
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

_DIRECTED_FAMILIES = ("held", "reversal")


def _traj_within_guards(
    traj: np.ndarray,
    nv_axes: np.ndarray,
    min_field_T: float,
    min_axis_projection_T: float,
    window_pin_Hz: tuple[float, float] | None,
    D_hz: float,
    gamma_hz_per_T: float,
    window_margin_hz: float,
) -> bool:
    """True if the trajectory satisfies every active envelope guard."""
    if min_field_T > 0.0 and min_field_magnitude_T(traj) < min_field_T:
        return False
    if min_axis_projection_T > 0.0:
        b_par = np.asarray(traj, dtype=float) @ np.asarray(nv_axes, dtype=float).T
        if float(np.min(np.abs(b_par))) < min_axis_projection_T:
            return False
    if window_pin_Hz is not None:
        allowed = min(D_hz - window_pin_Hz[0], window_pin_Hz[1] - D_hz) - window_margin_hz
        if max_line_offset_over_traj_hz(traj, nv_axes, D_hz, gamma_hz_per_T) > allowed:
            return False
    return True


def sample_directed_crossing(
    templates: list[dict],
    bias_T: np.ndarray,
    n_timesteps: int,
    seed: int,
    *,
    approach_lw_range: tuple[float, float],
    gamma_fwhm_hz: float,
    min_window_frac: float = 0.25,
    reversal_turn_frac_range: tuple[float, float] = (0.3, 0.7),
    jitter_frac: float = 0.05,
    min_field_T: float = 0.0,
    window_pin_Hz: tuple[float, float] | None = None,
    D_hz: float = 0.0,
    gamma_hz_per_T: float = 0.0,
    window_margin_hz: float = 0.0,
    min_axis_projection_T: float = 0.0,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    max_resamples: int = 2000,
    template_idx: int | None = None,
) -> tuple[np.ndarray, dict]:
    """Sample one directed merge-crossing trajectory.

    Picks a template (seeded uniform unless ``template_idx`` is given), an exit
    family (held cross / reversal bounce), an approach distance in linewidths, and
    a ramp window; builds the trajectory along the template's ``w_hat`` through
    ``a_merge``; redraws the kinematics until the envelope guards pass.

    Parameters
    ----------
    templates : list[dict]
        Merge templates from ``enumerate_dwell_templates`` (need ``w_hat``,
        ``w_norm``, ``a_merge``, ``p``, ``q``, ``p_mirror``, ``q_mirror``).
    bias_T : np.ndarray
        Static bias 3-vector (Tesla).
    n_timesteps : int
        Frames T (>= 3).
    seed : int
        Per-sequence seed for all directed draws.
    approach_lw_range : tuple[float, float]
        Uniform range (linewidths) for the pre-merge pair separation.
    gamma_fwhm_hz : float
        Intrinsic linewidth (Hz), sets the approach scalar via
        ``delta_a_for_separation``.
    min_window_frac : float
        Minimum held ramp-window fraction of the sequence.
    reversal_turn_frac_range : tuple[float, float]
        Turn-frame range (fraction of the sequence) for the reversal family.
    jitter_frac : float
        Fractional jitter on the approach scalar.
    min_field_T, window_pin_Hz, D_hz, gamma_hz_per_T, window_margin_hz,
    min_axis_projection_T, nv_axes :
        Envelope-guard parameters (see the isotropic sampler).
    max_resamples : int
        Bail out with ``RuntimeError`` after this many rejected kinematics (a
        template whose merge cannot satisfy the guards is a stop-and-report
        finding, not a silent drop).
    template_idx : int, optional
        Force a specific template (round-robin coverage); default seeded uniform.

    Returns
    -------
    tuple[np.ndarray, dict]
        ``(traj (T, 3) Tesla, meta)`` with ``meta`` = ``{"template_idx",
        "merge_p", "merge_q", "family", "approach_sign"}``.
    """
    if not templates:
        raise ValueError("sample_directed_crossing requires at least one template")
    if n_timesteps < 3:
        raise ValueError(f"n_timesteps must be >= 3, got {n_timesteps}")
    bias = np.asarray(bias_T, dtype=float).reshape(3)
    rng = np.random.default_rng(seed)

    ti = int(rng.integers(len(templates))) if template_idx is None else int(template_idx)
    template = templates[ti]
    w_hat = np.asarray(template["w_hat"], dtype=float).reshape(3)
    a_merge = float(template["a_merge"])
    w_norm = float(template["w_norm"])

    span_min = max(1, int(np.ceil(min_window_frac * (n_timesteps - 1))))
    tf_lo, tf_hi = float(reversal_turn_frac_range[0]), float(reversal_turn_frac_range[1])
    t_lo = max(1, int(np.ceil(tf_lo * (n_timesteps - 1))))
    t_hi = min(n_timesteps - 2, int(np.floor(tf_hi * (n_timesteps - 1))))

    n_resamples = 0
    while True:
        family = _DIRECTED_FAMILIES[int(rng.integers(2))]
        approach_lw = float(rng.uniform(approach_lw_range[0], approach_lw_range[1]))
        base_delta_a = delta_a_for_separation(approach_lw, gamma_fwhm_hz, w_norm)
        delta_a = float(base_delta_a * (1.0 + jitter_frac * rng.standard_normal()))
        delta_a = max(delta_a, 0.25 * base_delta_a)  # keep the ramp meaningful
        approach_sign = 1 if rng.random() < 0.5 else -1

        a_in = a_merge + approach_sign * delta_a
        if family == "held":
            # Pass through a_merge to the far side: the pair swaps (cross).
            a_out = a_merge - approach_sign * delta_a
            t0 = int(rng.integers(0, n_timesteps - span_min))
            t1 = int(rng.integers(t0 + span_min, n_timesteps))
            traj = held_ramp_trajectory(
                bias, a_in * w_hat, a_out * w_hat, n_timesteps, t0, t1
            )
        else:
            # Ramp in to the degeneracy and back to the entry side (bounce).
            t_turn = int(rng.integers(t_lo, t_hi + 1))
            traj = reversal_trajectory(
                bias, a_in * w_hat, a_merge * w_hat, a_in * w_hat, n_timesteps, t_turn
            )

        if _traj_within_guards(
            traj, nv_axes, min_field_T, min_axis_projection_T,
            window_pin_Hz, D_hz, gamma_hz_per_T, window_margin_hz,
        ):
            meta = {
                "template_idx": ti,
                "merge_p": int(template["p"]),
                "merge_q": int(template["q"]),
                "family": family,
                "approach_sign": int(approach_sign),
            }
            return traj, meta

        n_resamples += 1
        if n_resamples > max_resamples:
            raise RuntimeError(
                f"directed merge-crossing for template {ti} (pair "
                f"{template['p']},{template['q']}, a_merge={a_merge:.4e} T) could not "
                f"satisfy the envelope guards in {max_resamples} draws "
                f"(min_field_T={min_field_T}); reduce approach_lw_range or report the "
                f"unreachable geometry"
            )


__all__ = ["sample_directed_crossing"]
