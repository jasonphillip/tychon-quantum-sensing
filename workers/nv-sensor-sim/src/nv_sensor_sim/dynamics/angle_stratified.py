"""Angle-stratified widened field trajectories (v3, dispatch Amendment 1 Option A).

Uniform isotropic sampling structurally under-fills the wide off-bias cone: the
reachable angle is bounded by ``arcsin(|ext|/|bias|)`` and the high-angle band sits
at a measure-zero sliver near the |B| floor that random draws essentially never hit
(measured: isotropic +/-4.5 mT reaches median 21 deg, p99 44 deg, 0/1500 >= 53 deg).
To *cover* the cone to >=60 deg (so the 53.2 deg increment-5 failure geometry sits in
the interior) we sample the **off-bias angle** directly: draw a target angle from
``U[0, angle_max_deg]`` and a magnitude from the |B| law, then construct the field at
that stratum. The stratification law is recorded in the manifest -- it is a training
**density** change relative to v1/v2 isotropic sampling, not just an envelope change.

**Cold-start diversity.** The measured failure is off-cone *acquisition*, not
lock-carrying. A ``cold_start_fraction`` of sequences therefore *start* frame-0 at a
(possibly wide) drawn stratum -- forcing cold acquisition off-cone -- while the rest
*carry*: they start near the bias cone and ramp outward. The per-sequence start mode
(0 = acquire/cold, 1 = carry) is recorded so increment-6 can split on it.

The v1-style families (held / reversal / ou) are preserved as the ramp **shape** over
the stratified endpoints. The same envelope guards (|B| floor, window containment,
min per-axis projection) apply, with the stratum draws redrawn on rejection.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.dynamics.coverage_geometry import (
    max_line_offset_over_traj_hz,
    min_field_magnitude_T,
)
from nv_sensor_sim.dynamics.field_trajectory import (
    held_ramp_trajectory,
    reversal_trajectory,
)
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

# Start-mode integer codes recorded per sequence.
START_MODE_ACQUIRE = 0  # cold: starts at a drawn (possibly wide) stratum
START_MODE_CARRY = 1  # starts near the bias cone and ramps outward


def field_at_angle(
    bias_T: np.ndarray,
    theta_deg: float,
    B_mag_T: float,
    azimuth_rad: float,
) -> np.ndarray:
    """Lab-frame field of magnitude ``B_mag_T`` at ``theta_deg`` off the bias.

    The direction is ``cos(theta) * bias_hat + sin(theta) * perp(azimuth)`` where
    ``perp`` is a unit vector in the plane perpendicular to the bias, selected by
    ``azimuth_rad``. So the returned vector has exactly off-bias angle ``theta_deg``
    and magnitude ``B_mag_T`` for any azimuth.

    Parameters
    ----------
    bias_T : np.ndarray
        Static bias 3-vector (Tesla); only its direction is used.
    theta_deg : float
        Off-bias angle in degrees.
    B_mag_T : float
        Field magnitude in Tesla.
    azimuth_rad : float
        Azimuth around the bias axis in radians.

    Returns
    -------
    np.ndarray
        Lab-frame field 3-vector (Tesla).
    """
    bias = np.asarray(bias_T, dtype=float).reshape(3)
    b_norm = np.linalg.norm(bias)
    if b_norm == 0.0:
        raise ValueError("bias_T must be non-zero")
    b_hat = bias / b_norm
    ref = np.array([1.0, 0.0, 0.0]) if abs(b_hat[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = ref - (ref @ b_hat) * b_hat
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(b_hat, e1)
    perp = np.cos(azimuth_rad) * e1 + np.sin(azimuth_rad) * e2
    theta = np.radians(theta_deg)
    direction = np.cos(theta) * b_hat + np.sin(theta) * perp
    return B_mag_T * direction


def sample_angle_stratified_ramp(
    bias_T: np.ndarray,
    n_timesteps: int,
    seed: int,
    *,
    shape: str,
    angle_max_deg: float,
    field_range_T: tuple[float, float],
    cold_start_fraction: float,
    carry_start_max_deg: float,
    carry_field_range_T: tuple[float, float],
    min_sweep_delta_T: float,
    min_window_frac: float = 0.25,
    reversal_turn_frac_range: tuple[float, float] = (0.2, 0.8),
    jitter_frac: float = 0.05,
    min_field_T: float = 0.0,
    window_pin_Hz: tuple[float, float] | None = None,
    D_hz: float = 0.0,
    gamma_hz_per_T: float = 0.0,
    window_margin_hz: float = 0.0,
    min_axis_projection_T: float = 0.0,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    max_resamples: int = 10_000,
) -> tuple[np.ndarray, dict]:
    """Sample an angle-stratified widened ramp of the given shape.

    Draws a target stratum ``(theta1, |B|1, azimuth1)`` with ``theta1 ~
    U[0, angle_max_deg]`` and ``|B|1 ~ U[field_range_T]``, a start mode
    (``acquire`` with probability ``cold_start_fraction``, else ``carry``), and a
    start stratum: for ``acquire`` from the full cone (cold start, possibly wide),
    for ``carry`` from the near-bias cone (``theta0 ~ U[0, carry_start_max_deg]``,
    ``|B|0 ~ U[carry_field_range_T]``). Builds a ``held`` (hold-ramp-hold) or
    ``reversal`` (out-and-back) trajectory between the endpoints, redrawing on
    minimum-motion or envelope-guard failure.

    Returns ``(traj (T, 3) Tesla, meta)`` with ``meta`` = ``{"start_mode",
    "target_angle_deg", "target_B_T", "start_angle_deg"}``.
    """
    if shape not in ("held", "reversal"):
        raise ValueError(f"shape must be 'held' or 'reversal', got {shape!r}")
    if n_timesteps < (3 if shape == "reversal" else 2):
        raise ValueError(f"n_timesteps too small for shape {shape!r}: {n_timesteps}")
    bias = np.asarray(bias_T, dtype=float).reshape(3)
    rng = np.random.default_rng(seed)

    floor_active = min_field_T > 0.0
    window_active = window_pin_Hz is not None
    window_allowed_hz = (
        min(D_hz - window_pin_Hz[0], window_pin_Hz[1] - D_hz) - window_margin_hz
        if window_active
        else 0.0
    )
    span_min = max(1, int(np.ceil(min_window_frac * (n_timesteps - 1))))
    tf_lo, tf_hi = float(reversal_turn_frac_range[0]), float(reversal_turn_frac_range[1])
    t_lo = max(1, int(np.ceil(tf_lo * (n_timesteps - 1))))
    t_hi = min(n_timesteps - 2, int(np.floor(tf_hi * (n_timesteps - 1))))

    def _guards_ok(traj: np.ndarray) -> bool:
        if min_axis_projection_T > 0.0:
            proj = np.abs(traj @ np.asarray(nv_axes, dtype=float).T)
            if float(proj.min()) < min_axis_projection_T:
                return False
        if floor_active and min_field_magnitude_T(traj) < min_field_T:
            return False
        if window_active and (
            max_line_offset_over_traj_hz(traj, nv_axes, D_hz, gamma_hz_per_T) > window_allowed_hz
        ):
            return False
        return True

    # The target off-bias angle is drawn in the OUTER loop and the |B|, azimuth and
    # start stratum in the INNER loop, so guard rejection (mostly projection-zeros
    # at random wide-angle azimuths) does not bias the accepted angle distribution
    # away from the U[0, angle_max_deg] law -- preserving the recorded density.
    inner_max = 2000
    n_resamples = 0
    while True:
        theta1 = float(rng.uniform(0.0, angle_max_deg))
        cold = bool(rng.random() < cold_start_fraction)
        start_mode = START_MODE_ACQUIRE if cold else START_MODE_CARRY
        for _inner in range(inner_max):
            b1 = float(rng.uniform(field_range_T[0], field_range_T[1]))
            phi1 = float(rng.uniform(0.0, 2.0 * np.pi))
            if cold:
                theta0 = float(rng.uniform(0.0, angle_max_deg))
                b0 = float(rng.uniform(field_range_T[0], field_range_T[1]))
            else:
                theta0 = float(rng.uniform(0.0, carry_start_max_deg))
                b0 = float(rng.uniform(carry_field_range_T[0], carry_field_range_T[1]))
            phi0 = float(rng.uniform(0.0, 2.0 * np.pi))

            ext_start = field_at_angle(bias, theta0, b0, phi0) - bias
            ext_end = field_at_angle(bias, theta1, b1, phi1) - bias
            if jitter_frac > 0.0:
                leg = float(np.linalg.norm(ext_end - ext_start))
                ext_start = ext_start + jitter_frac * leg * rng.standard_normal(3)
                ext_end = ext_end + jitter_frac * leg * rng.standard_normal(3)
            if float(np.linalg.norm(ext_end - ext_start)) < min_sweep_delta_T:
                n_resamples += 1
                continue

            if shape == "held":
                t0 = int(rng.integers(0, n_timesteps - span_min))
                t1 = int(rng.integers(t0 + span_min, n_timesteps))
                traj = held_ramp_trajectory(bias, ext_start, ext_end, n_timesteps, t0, t1)
            else:
                t_turn = int(rng.integers(t_lo, t_hi + 1))
                traj = reversal_trajectory(bias, ext_start, ext_end, ext_start, n_timesteps, t_turn)

            if _guards_ok(traj):
                return traj, {
                    "start_mode": start_mode,
                    "target_angle_deg": theta1,
                    "target_B_T": b1,
                    "start_angle_deg": theta0,
                }
            n_resamples += 1

        # This target angle admitted no feasible |B|/azimuth within the inner
        # budget: redraw it. Persistent failure means angle_max_deg exceeds the
        # pinned-grid feasible cone -- a stop-and-report condition.
        if n_resamples > max_resamples:
            raise RuntimeError(
                f"angle-stratified sampler rejected {max_resamples} geometries "
                f"(min_field_T={min_field_T}, min_axis_projection_T={min_axis_projection_T}); "
                f"angle_max_deg={angle_max_deg} likely exceeds the pinned-grid feasible cone -- "
                f"stop-and-report the achievable envelope"
            )


__all__ = ["field_at_angle", "sample_angle_stratified_ramp", "START_MODE_ACQUIRE", "START_MODE_CARRY"]
