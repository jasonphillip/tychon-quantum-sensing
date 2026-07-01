"""Lab-frame magnetic field trajectories B(t) for time-series ODMR.

A trajectory is a static bias plus a swept external field. The sweep is designed
to drag resonances from different NV axes across each other in frequency space so
a tracker can be trained/evaluated on holding per-axis identity through the
crossing. Fields are kept in the honest regime (a few mT to ~tens of mT, below
ESLAC ~51 mT) where the 8 lines are resolved and the first-order Zeeman geometry
holds.

The static bias is set from the path-agnostic bias config (``bias_B0_T``,
``bias_direction_uvw``) shared with the static vector pipeline; the lab-frame
bias vector is ``bias_B0_T * normalize(bias_direction_uvw)`` (the repo convention
aligns the diamond crystal [uvw] axes with lab xyz).
"""

from __future__ import annotations

import numpy as np


def static_bias_vector(
    bias_B0_T: float,
    bias_direction_uvw: tuple[float, float, float] | np.ndarray,
) -> np.ndarray:
    """Lab-frame static bias vector ``bias_B0_T * normalize(uvw)`` in Tesla.

    Parameters
    ----------
    bias_B0_T : float
        Bias-field magnitude in Tesla.
    bias_direction_uvw : tuple[float, float, float] or np.ndarray
        Bias direction in crystal [uvw] (== lab xyz under the repo convention).
        Need not be normalized.

    Returns
    -------
    np.ndarray
        Lab-frame bias 3-vector in Tesla. Zero vector if ``bias_B0_T == 0``.
    """
    direction = np.asarray(bias_direction_uvw, dtype=float).reshape(3)
    norm = np.linalg.norm(direction)
    if norm == 0.0 or bias_B0_T == 0.0:
        return np.zeros(3)
    return bias_B0_T * direction / norm


def sample_isotropic_held_ramp(
    scalar_range_T: tuple[float, float],
    min_delta_T: float,
    n_timesteps: int,
    min_window_frac: float,
    seed: int,
    jitter_frac: float = 0.0,
    bias_T: np.ndarray | None = None,
    min_axis_proj_T: float = 0.0,
    nv_axes: np.ndarray | None = None,
    max_resamples: int = 10_000,
) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    """Sample a per-sequence held ramp: independent endpoints on a random axis.

    Draws a ramp direction ``u`` uniformly on the unit sphere and two
    *independent* signed scalars ``s_start, s_end ~ U[scalar_range_T]`` along
    ``u`` (rejection-sampled until ``|s_end - s_start| >= min_delta_T`` so every
    sequence has motion), plus a ramp sub-interval ``[t0, t1]`` of the sequence
    with ``t1 - t0 >= min_window_frac * (n_timesteps - 1)``. The external field
    holds at ``s_start*u`` before ``t0``, ramps linearly to ``s_end*u`` by
    ``t1``, and holds there after — see ``held_ramp_trajectory``.

    Compared to a forced antisymmetric ``-m*u -> +m*u`` sweep this yields
    variable crossing times (not pinned mid-sequence), variable crossing
    counts including sequences with *no* crossing (identity-hold negatives),
    ramp rates decoupled from sequence length, and steady pre/post-ramp
    segments for re-lock evaluation.

    Each endpoint is perturbed by Gaussian jitter ``jitter_frac * |s_end -
    s_start| * N(0, I3)`` (scaled to the ramp length, so near-zero endpoints
    still jitter). All draws come from one seeded stream so a sequence's
    geometry is reproducible from its seed alone.

    When ``bias_T`` and ``min_axis_proj_T`` are given, geometries whose total
    field would drive any NV axis' ``|B . n_i|`` below ``min_axis_proj_T``
    anywhere along the ramp are rejected and redrawn (from the same stream):
    near a projection zero-crossing the diagonalized transition labels jump
    discontinuously and the splitting relation degenerates. The projection is
    linear along the ramp segment, so the exact minimum is at an endpoint, or
    zero if the endpoint projections differ in sign.

    Parameters
    ----------
    scalar_range_T : tuple[float, float]
        ``(lo, hi)`` uniform range in Tesla for the signed endpoint scalars,
        ``lo < hi``.
    min_delta_T : float
        Minimum ``|s_end - s_start|`` in Tesla, ``0 < min_delta_T <= hi - lo``.
    n_timesteps : int
        Number of frames T (>= 2).
    min_window_frac : float
        Minimum ramp-window length as a fraction of ``n_timesteps - 1``,
        in ``(0, 1]``.
    seed : int
        Per-sequence seed for direction, endpoint, window, and jitter draws.
    jitter_frac : float
        Fractional Gaussian perturbation of each endpoint (relative to the
        ramp length ``|s_end - s_start|``). Default 0.0.
    bias_T : np.ndarray, optional
        Static bias 3-vector in Tesla. Enables the min-projection guard.
    min_axis_proj_T : float
        Minimum allowed per-axis ``|B . n_i|`` (Tesla) along the ramp.
        0.0 disables the guard.
    nv_axes : np.ndarray, optional
        Unit vectors of the NV axes, shape (n_axes, 3). Required when the
        min-projection guard is enabled.
    max_resamples : int
        Bail out with ``RuntimeError`` after this many rejected geometries
        (guards against configs where the acceptance region is tiny).

    Returns
    -------
    tuple[np.ndarray, np.ndarray, int, int, int]
        ``(ramp_start_T, ramp_end_T, t0, t1, n_resamples)``: external-field
        3-vectors in Tesla, the ramp-window frame indices ``0 <= t0 < t1 <=
        T - 1``, and how many candidate geometries were rejected.
    """
    lo, hi = float(scalar_range_T[0]), float(scalar_range_T[1])
    if not lo < hi:
        raise ValueError(f"scalar_range_T must satisfy lo < hi, got ({lo}, {hi})")
    min_delta = float(min_delta_T)
    if not 0.0 < min_delta <= hi - lo:
        raise ValueError(
            f"min_delta_T must satisfy 0 < min_delta_T <= hi - lo = {hi - lo}, got {min_delta}"
        )
    if n_timesteps < 2:
        raise ValueError(f"n_timesteps must be >= 2, got {n_timesteps}")
    if not 0.0 < min_window_frac <= 1.0:
        raise ValueError(f"min_window_frac must be in (0, 1], got {min_window_frac}")
    guard_active = bias_T is not None and min_axis_proj_T > 0.0
    if guard_active and nv_axes is None:
        raise ValueError("min-projection guard requires nv_axes")

    rng = np.random.default_rng(seed)
    span_min = max(1, int(np.ceil(min_window_frac * (n_timesteps - 1))))
    n_resamples = 0

    while True:
        u = rng.standard_normal(3)
        norm = np.linalg.norm(u)
        while norm < 1e-12:  # numerically degenerate draw; probability ~0
            u = rng.standard_normal(3)
            norm = np.linalg.norm(u)
        u /= norm

        s_start = rng.uniform(lo, hi)
        s_end = rng.uniform(lo, hi)
        while abs(s_end - s_start) < min_delta:
            s_start = rng.uniform(lo, hi)
            s_end = rng.uniform(lo, hi)
        delta = abs(s_end - s_start)

        t0 = int(rng.integers(0, n_timesteps - span_min))
        t1 = int(rng.integers(t0 + span_min, n_timesteps))

        start = s_start * u
        end = s_end * u
        if jitter_frac > 0.0:
            start = start + jitter_frac * delta * rng.standard_normal(3)
            end = end + jitter_frac * delta * rng.standard_normal(3)

        if not guard_active:
            return start, end, t0, t1, n_resamples

        # Exact per-axis min |B . n_i| on the ramp segment: the projection is
        # linear in t, so the minimum is at an endpoint unless the sign flips.
        axes = np.asarray(nv_axes, dtype=float)
        bias = np.asarray(bias_T, dtype=float).reshape(3)
        p0 = axes @ (bias + start)
        p1 = axes @ (bias + end)
        seg_min = np.where(p0 * p1 <= 0.0, 0.0, np.minimum(np.abs(p0), np.abs(p1)))
        if float(seg_min.min()) >= min_axis_proj_T:
            return start, end, t0, t1, n_resamples

        n_resamples += 1
        if n_resamples > max_resamples:
            raise RuntimeError(
                f"min-projection guard rejected {max_resamples} consecutive geometries "
                f"(min_axis_proj_T={min_axis_proj_T}); check the sweep/bias configuration"
            )


def sample_reversal_ramp(
    scalar_range_T: tuple[float, float],
    min_delta_T: float,
    n_timesteps: int,
    turn_frac_range: tuple[float, float],
    seed: int,
    jitter_frac: float = 0.0,
    bias_T: np.ndarray | None = None,
    min_axis_proj_T: float = 0.0,
    nv_axes: np.ndarray | None = None,
    max_resamples: int = 10_000,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Sample a reversal ramp: out along a random axis, turn around, ramp back.

    Draws a direction ``u`` uniform on the sphere, an out-leg ``s_start ->
    s_turn`` (independent scalars from ``scalar_range_T`` with ``|s_turn -
    s_start| >= min_delta_T``), a turn frame ``t_turn`` uniform in
    ``turn_frac_range`` of the sequence, and a return leg ``s_turn -> s_end``
    that *reverses direction* (``sign(s_end - s_turn) = -sign(s_turn -
    s_start)``, ``|s_end - s_turn| >= min_delta_T``) — so the field revisits
    the crossing region at a generally different rate. Field velocity is
    momentarily zero at the turn; reversals landing inside a collision dwell
    are the velocity-ambiguous tracking case.

    Endpoint jitter and the min-projection guard follow
    ``sample_isotropic_held_ramp`` conventions (jitter scaled to the larger
    leg; the guard checks both linear legs exactly).

    Parameters
    ----------
    scalar_range_T : tuple[float, float]
        ``(lo, hi)`` uniform range in Tesla for the signed scalars, ``lo < hi``.
    min_delta_T : float
        Minimum leg length in Tesla, ``0 < min_delta_T <= hi - lo``.
    n_timesteps : int
        Number of frames T (>= 3).
    turn_frac_range : tuple[float, float]
        ``(lo, hi)`` fraction of ``n_timesteps - 1`` for the turn frame,
        ``0 < lo < hi < 1`` (e.g. ``(0.2, 0.8)`` = the middle 60%).
    seed : int
        Per-sequence seed for all draws.
    jitter_frac : float
        Fractional Gaussian perturbation of each knot (relative to the larger
        leg length). Default 0.0.
    bias_T : np.ndarray, optional
        Static bias 3-vector in Tesla. Enables the min-projection guard.
    min_axis_proj_T : float
        Minimum allowed per-axis ``|B . n_i|`` (Tesla) along both legs.
    nv_axes : np.ndarray, optional
        Unit vectors of the NV axes. Required when the guard is enabled.
    max_resamples : int
        Bail out with ``RuntimeError`` after this many rejected geometries.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray, int, int]
        ``(start_T, turn_T, end_T, t_turn, n_resamples)``: external-field
        3-vectors at the first frame, the turn, and the last frame; the turn
        frame index; and the rejected-geometry count.
    """
    lo, hi = float(scalar_range_T[0]), float(scalar_range_T[1])
    if not lo < hi:
        raise ValueError(f"scalar_range_T must satisfy lo < hi, got ({lo}, {hi})")
    min_delta = float(min_delta_T)
    if not 0.0 < min_delta <= hi - lo:
        raise ValueError(
            f"min_delta_T must satisfy 0 < min_delta_T <= hi - lo = {hi - lo}, got {min_delta}"
        )
    if n_timesteps < 3:
        raise ValueError(f"n_timesteps must be >= 3 for a reversal, got {n_timesteps}")
    tf_lo, tf_hi = float(turn_frac_range[0]), float(turn_frac_range[1])
    if not 0.0 < tf_lo < tf_hi < 1.0:
        raise ValueError(f"turn_frac_range must satisfy 0 < lo < hi < 1, got ({tf_lo}, {tf_hi})")
    guard_active = bias_T is not None and min_axis_proj_T > 0.0
    if guard_active and nv_axes is None:
        raise ValueError("min-projection guard requires nv_axes")

    rng = np.random.default_rng(seed)
    t_lo = max(1, int(np.ceil(tf_lo * (n_timesteps - 1))))
    t_hi = min(n_timesteps - 2, int(np.floor(tf_hi * (n_timesteps - 1))))
    if t_hi < t_lo:
        raise ValueError(
            f"turn_frac_range {turn_frac_range} leaves no valid turn frame for T={n_timesteps}"
        )
    n_resamples = 0

    while True:
        u = rng.standard_normal(3)
        norm = np.linalg.norm(u)
        while norm < 1e-12:  # numerically degenerate draw; probability ~0
            u = rng.standard_normal(3)
            norm = np.linalg.norm(u)
        u /= norm

        s_start = rng.uniform(lo, hi)
        s_turn = rng.uniform(lo, hi)
        while abs(s_turn - s_start) < min_delta:
            s_start = rng.uniform(lo, hi)
            s_turn = rng.uniform(lo, hi)
        out_sign = np.sign(s_turn - s_start)
        # Return leg reverses direction; redraw the geometry if the range
        # leaves no room for a min_delta return on that side.
        back_room = (s_turn - lo) if out_sign > 0 else (hi - s_turn)
        if back_room < min_delta:
            n_resamples += 1
            if n_resamples > max_resamples:
                raise RuntimeError(
                    f"reversal sampler rejected {max_resamples} consecutive geometries; "
                    f"check scalar_range/min_delta"
                )
            continue
        back_len = rng.uniform(min_delta, back_room)
        s_end = s_turn - out_sign * back_len
        t_turn = int(rng.integers(t_lo, t_hi + 1))

        start = s_start * u
        turn = s_turn * u
        end = s_end * u
        if jitter_frac > 0.0:
            leg = max(abs(s_turn - s_start), abs(s_end - s_turn))
            start = start + jitter_frac * leg * rng.standard_normal(3)
            turn = turn + jitter_frac * leg * rng.standard_normal(3)
            end = end + jitter_frac * leg * rng.standard_normal(3)

        if not guard_active:
            return start, turn, end, t_turn, n_resamples

        axes = np.asarray(nv_axes, dtype=float)
        bias = np.asarray(bias_T, dtype=float).reshape(3)
        p_start = axes @ (bias + start)
        p_turn = axes @ (bias + turn)
        p_end = axes @ (bias + end)
        ok = True
        for p0, p1 in ((p_start, p_turn), (p_turn, p_end)):
            seg_min = np.where(p0 * p1 <= 0.0, 0.0, np.minimum(np.abs(p0), np.abs(p1)))
            if float(seg_min.min()) < min_axis_proj_T:
                ok = False
                break
        if ok:
            return start, turn, end, t_turn, n_resamples

        n_resamples += 1
        if n_resamples > max_resamples:
            raise RuntimeError(
                f"min-projection guard rejected {max_resamples} consecutive reversal "
                f"geometries (min_axis_proj_T={min_axis_proj_T})"
            )


def reversal_trajectory(
    bias_T: np.ndarray,
    start_T: np.ndarray,
    turn_T: np.ndarray,
    end_T: np.ndarray,
    n_timesteps: int,
    t_turn: int,
) -> np.ndarray:
    """Two-leg piecewise-linear trajectory: out to the turn knot, then back.

    ``B(t)`` interpolates ``bias + start -> bias + turn`` over ``0..t_turn``
    and ``bias + turn -> bias + end`` over ``t_turn..T-1``.

    Parameters
    ----------
    bias_T : np.ndarray
        Static bias 3-vector in Tesla (lab frame).
    start_T, turn_T, end_T : np.ndarray
        External-field 3-vectors (Tesla) at the first frame, turn, last frame.
    n_timesteps : int
        Number of frames T (>= 3).
    t_turn : int
        Turn frame index, ``0 < t_turn < n_timesteps - 1``.

    Returns
    -------
    np.ndarray
        Field trajectory of shape (n_timesteps, 3) in Tesla.
    """
    if n_timesteps < 3:
        raise ValueError(f"n_timesteps must be >= 3 for a reversal, got {n_timesteps}")
    if not 0 < t_turn < n_timesteps - 1:
        raise ValueError(
            f"turn frame must satisfy 0 < t_turn < T - 1, got t_turn={t_turn}, T={n_timesteps}"
        )

    bias = np.asarray(bias_T, dtype=float).reshape(3)
    start = np.asarray(start_T, dtype=float).reshape(3)
    turn = np.asarray(turn_T, dtype=float).reshape(3)
    end = np.asarray(end_T, dtype=float).reshape(3)

    t = np.arange(n_timesteps)
    frac_out = np.clip(t / t_turn, 0.0, 1.0)[:, None]
    frac_back = np.clip((t - t_turn) / (n_timesteps - 1 - t_turn), 0.0, 1.0)[:, None]
    external = np.where(
        (t <= t_turn)[:, None],
        start[None, :] * (1.0 - frac_out) + turn[None, :] * frac_out,
        turn[None, :] * (1.0 - frac_back) + end[None, :] * frac_back,
    )
    return bias[None, :] + external


def ou_field_perturbation(
    sigma_T: float,
    tau_frames: float,
    n_timesteps: int,
    seed: int | list[int],
) -> np.ndarray:
    """Stationary discrete-OU (AR(1)) 3-vector field perturbation, (T, 3) Tesla.

    Each component follows ``x[t+1] = a x[t] + sqrt(1 - a^2) sigma N(0,1)``
    with ``a = exp(-1/tau_frames)`` and stationary per-component std
    ``sigma_T``; ``x[0]`` is drawn from the stationary distribution. Added to
    a ramp's external field it produces O(gamma * sigma_T) resonance wander
    with correlation time ``tau_frames``.

    Parameters
    ----------
    sigma_T : float
        Stationary per-component standard deviation in Tesla (> 0).
    tau_frames : float
        Correlation time in frames (> 0).
    n_timesteps : int
        Number of frames T (>= 1).
    seed : int or list[int]
        Seed (or spawn-key sequence) for the perturbation stream.

    Returns
    -------
    np.ndarray
        Perturbation trajectory of shape (n_timesteps, 3) in Tesla.
    """
    if sigma_T <= 0.0:
        raise ValueError(f"sigma_T must be > 0, got {sigma_T}")
    if tau_frames <= 0.0:
        raise ValueError(f"tau_frames must be > 0, got {tau_frames}")
    if n_timesteps < 1:
        raise ValueError(f"n_timesteps must be >= 1, got {n_timesteps}")

    rng = np.random.default_rng(seed)
    alpha = float(np.exp(-1.0 / tau_frames))
    innov = np.sqrt(1.0 - alpha**2)
    x = np.empty((n_timesteps, 3))
    x[0] = rng.standard_normal(3) * sigma_T
    for t in range(1, n_timesteps):
        x[t] = alpha * x[t - 1] + innov * sigma_T * rng.standard_normal(3)
    return x


def held_ramp_trajectory(
    bias_T: np.ndarray,
    ramp_start_T: tuple[float, float, float] | np.ndarray,
    ramp_end_T: tuple[float, float, float] | np.ndarray,
    n_timesteps: int,
    t0: int,
    t1: int,
) -> np.ndarray:
    """Hold–ramp–hold trajectory: linear ramp over the sub-interval [t0, t1].

    ``B(t) = bias + start`` for ``t <= t0``, linear interpolation to ``end``
    over ``t0..t1``, then ``bias + end`` for ``t >= t1``.

    Parameters
    ----------
    bias_T : np.ndarray
        Static bias 3-vector in Tesla (lab frame).
    ramp_start_T, ramp_end_T : tuple[float, float, float] or np.ndarray
        External-field 3-vectors (Tesla) held before ``t0`` / after ``t1``.
    n_timesteps : int
        Number of frames T (>= 2).
    t0, t1 : int
        Ramp-window frame indices, ``0 <= t0 < t1 <= n_timesteps - 1``.

    Returns
    -------
    np.ndarray
        Field trajectory of shape (n_timesteps, 3) in Tesla.
    """
    if n_timesteps < 2:
        raise ValueError(f"n_timesteps must be >= 2, got {n_timesteps}")
    if not 0 <= t0 < t1 <= n_timesteps - 1:
        raise ValueError(
            f"ramp window must satisfy 0 <= t0 < t1 <= T - 1, got t0={t0}, t1={t1}, T={n_timesteps}"
        )

    bias = np.asarray(bias_T, dtype=float).reshape(3)
    start = np.asarray(ramp_start_T, dtype=float).reshape(3)
    end = np.asarray(ramp_end_T, dtype=float).reshape(3)

    frac = np.clip((np.arange(n_timesteps) - t0) / (t1 - t0), 0.0, 1.0)[:, None]  # (T, 1)
    external = start[None, :] * (1.0 - frac) + end[None, :] * frac  # (T, 3)
    return bias[None, :] + external


def ramp_crossing_trajectory(
    bias_T: np.ndarray,
    ramp_start_T: tuple[float, float, float] | np.ndarray,
    ramp_end_T: tuple[float, float, float] | np.ndarray,
    n_timesteps: int,
    *,
    seed: int | None = None,
    jitter_frac: float = 0.0,
) -> np.ndarray:
    """Linear ramp of an external field added to a static bias.

    ``B(t) = bias + lerp(ramp_start, ramp_end, t / (T - 1))``. With ``jitter_frac``
    > 0 the ramp endpoints are perturbed per-sequence (seeded) so a dataset of
    sequences varies while still sweeping through a crossing. Choose
    ``ramp_start``/``ramp_end`` so a target axis pair's lines move toward and
    through each other near mid-sequence (see ``configs/sequence_sanity_v0.yaml``).

    Parameters
    ----------
    bias_T : np.ndarray
        Static bias 3-vector in Tesla (lab frame).
    ramp_start_T, ramp_end_T : tuple[float, float, float] or np.ndarray
        External-field 3-vectors (Tesla) at the first and last frame.
    n_timesteps : int
        Number of frames T (>= 2).
    seed : int, optional
        Seed for per-sequence endpoint jitter. None disables jitter.
    jitter_frac : float
        Fractional Gaussian perturbation of each endpoint (relative to its norm).
        Default 0.0 (deterministic nominal trajectory).

    Returns
    -------
    np.ndarray
        Field trajectory of shape (n_timesteps, 3) in Tesla.
    """
    if n_timesteps < 2:
        raise ValueError(f"n_timesteps must be >= 2, got {n_timesteps}")

    bias = np.asarray(bias_T, dtype=float).reshape(3)
    start = np.asarray(ramp_start_T, dtype=float).reshape(3)
    end = np.asarray(ramp_end_T, dtype=float).reshape(3)

    if jitter_frac > 0.0 and seed is not None:
        rng = np.random.default_rng(seed)
        start = start + jitter_frac * np.linalg.norm(start) * rng.standard_normal(3)
        end = end + jitter_frac * np.linalg.norm(end) * rng.standard_normal(3)

    frac = np.linspace(0.0, 1.0, n_timesteps)[:, None]  # (T, 1)
    external = start[None, :] * (1.0 - frac) + end[None, :] * frac  # (T, 3)
    return bias[None, :] + external


def orbit_trajectory(*args, **kwargs) -> np.ndarray:
    """Orbit-driven B(t) from ``orbits.trajectory`` (planned).

    The ``orbits`` package already produces a per-step lab/payload-frame B(t) on a
    uniform dt grid (``build_trajectory_batch`` -> ``B_payload_{x,y,z}``); wiring
    those columns in as a field trajectory is a future increment.
    """
    raise NotImplementedError(
        "Orbit-driven field trajectories are not yet wired in. Use "
        "ramp_crossing_trajectory; orbits.trajectory.build_trajectory_batch "
        "provides B(t) columns to adapt here later."
    )
