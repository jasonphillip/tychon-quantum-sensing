"""Parameterized merged-dwell field trajectories for the identity dwell-sweep.

The dwell family is a *held template*: one chosen cross-axis line pair ``(p, q)``
is driven together along a single field direction and made to sit within a
linewidth for a controlled number of frames, then either cross or bounce.

Merge coordinate
----------------
Line ``p`` has (first-order) frequency ``f_p = D + sigma_p * gamma * (B . n_i)``,
with ``sigma_p = +1`` for even line indices (the ``+n_i`` transition) and ``-1``
for odd (``-n_i``), ``i = p // 2``. So for a cross-axis pair the separation is

    f_p - f_q = gamma * (sigma_p n_i - sigma_q n_j) . B  =  gamma * w . B ,

i.e. a linear projection of the field onto ``w = sigma_p n_i - sigma_q n_j``.
Driving the external field along ``w_hat = w / |w|`` moves the pair together;
holding at ``w . B = 0`` (the scalar ``a_merge`` along ``w_hat``) holds them
merged. The exit topology is set by the ramp-out side:

- **cross**  — ramp out to the far side of ``a_merge`` (``f_p - f_q`` changes
  sign): the two lines swap. A constant-velocity field prior predicts this.
- **bounce** — ramp out back to the entry side (``f_p - f_q`` returns to its
  entry sign): the field reverses during the dwell and the lines return to the
  sides they came from — the velocity-ambiguous case a CV prior gets wrong.

Because the two orientations' *other* transition pair is degenerate at the same
``|B.n_i| = |B.n_j|`` (the mirror pair), a clean single-pair merge exists only
where the second-order transverse shift (present in the diagonalized labels)
resolves the mirror. ``plan_dwell_merge`` therefore verifies isolation on the
real per-axis diagonalized centers, not the first-order model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nv_sensor_sim.dynamics.render import render_multi_axis_frame
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT, project_field_onto_axes

if TYPE_CHECKING:
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter


def line_sign(line_index: int) -> float:
    """Frequency sign ``sigma_p`` of a line: +1 for even (``+n_i``), -1 for odd."""
    return 1.0 if line_index % 2 == 0 else -1.0


def merge_direction(p: int, q: int, nv_axes: np.ndarray = NV_AXES_UNIT) -> tuple[np.ndarray, float]:
    """Unit field direction that separates line pair ``(p, q)`` fastest.

    Returns ``(w_hat, |w|)`` where ``w = sigma_p n_i - sigma_q n_j`` and the
    first-order pair separation is ``gamma * |w| * (a - a_merge)`` for external
    field ``a * w_hat``.
    """
    i, j = p // 2, q // 2
    w = line_sign(p) * np.asarray(nv_axes[i], dtype=float) - line_sign(q) * np.asarray(
        nv_axes[j], dtype=float
    )
    w_norm = float(np.linalg.norm(w))
    if w_norm < 1e-12:
        raise ValueError(f"lines {p},{q} have no separating direction (same axis+sign)")
    return w / w_norm, w_norm


def first_order_a_merge(
    bias_T: np.ndarray, p: int, q: int, nv_axes: np.ndarray = NV_AXES_UNIT
) -> float:
    """Scalar ``a`` along ``w_hat`` at which the pair is first-order degenerate.

    Solves ``w . (bias + a w_hat) = 0`` -> ``a = -(w . bias) / |w|``.
    """
    w_hat, w_norm = merge_direction(p, q, nv_axes)
    w = w_hat * w_norm
    return float(-(w @ np.asarray(bias_T, dtype=float)) / w_norm)


def dwell_scalars(
    a_merge: float, delta_a: float, topology: str, approach_sign: int = 1
) -> tuple[float, float]:
    """Entry/exit scalars ``(a_in, a_out)`` for a dwell of the given topology.

    ``a_in = a_merge + approach_sign * delta_a``; ``a_out`` is the far side for
    ``cross`` and the entry side for ``bounce``.
    """
    if topology not in ("cross", "bounce"):
        raise ValueError(f"topology must be 'cross' or 'bounce', got {topology!r}")
    s = 1.0 if approach_sign >= 0 else -1.0
    a_in = a_merge + s * delta_a
    a_out = a_merge - s * delta_a if topology == "cross" else a_merge + s * delta_a
    return a_in, a_out


def build_dwell_trajectory(
    bias_T: np.ndarray,
    w_hat: np.ndarray,
    a_in: float,
    a_merge: float,
    a_out: float,
    pre_hold: int,
    ramp: int,
    dwell: int,
    post_hold: int,
) -> np.ndarray:
    """Hold - ramp-in - merged dwell - ramp-out - hold trajectory (T, 3), Tesla.

    Frame layout (``T = pre_hold + ramp + dwell + ramp + post_hold``):
    ``[0, pre_hold)`` held at ``a_in``; ``[pre_hold, pre_hold+ramp)`` linear
    ``a_in -> a_merge`` (reaching ``a_merge`` at the first dwell frame);
    ``[.., + dwell)`` held at ``a_merge`` (the merged dwell); ramp-out linear
    ``a_merge -> a_out``; final hold at ``a_out``. The external field is
    ``a(t) * w_hat`` added to the static bias.
    """
    if min(pre_hold, dwell, post_hold) < 0 or ramp < 1:
        raise ValueError("pre_hold/dwell/post_hold must be >= 0 and ramp >= 1")
    bias = np.asarray(bias_T, dtype=float).reshape(3)
    w_hat = np.asarray(w_hat, dtype=float).reshape(3)
    T = pre_hold + ramp + dwell + ramp + post_hold
    a = np.empty(T, dtype=float)

    t0 = pre_hold
    t1 = t0 + ramp
    t2 = t1 + dwell
    t3 = t2 + ramp
    a[:t0] = a_in
    # Ramp-in: a_in at frame t0, reaching a_merge exactly at the first dwell frame t1.
    k = np.arange(ramp)
    a[t0:t1] = a_in + (a_merge - a_in) * (k / ramp)
    a[t1:t2] = a_merge
    # Ramp-out: first step off a_merge at t2, reaching a_out at frame t3-1.
    a[t2:t3] = a_merge + (a_out - a_merge) * ((k + 1) / ramp)
    a[t3:] = a_out

    return bias[None, :] + a[:, None] * w_hat[None, :]


def diagonalized_centers(
    adapter: SimOSAdapter,
    B_lab_T: np.ndarray,
    axis_offsets_hz: np.ndarray | None = None,
    nv_axes: np.ndarray = NV_AXES_UNIT,
) -> np.ndarray:
    """The 8 diagonalized line centers (geometry-matrix order, Hz) at one field.

    Thin wrapper over ``render_multi_axis_frame`` that keeps only the centers;
    used for merge planning and isolation checks against the *real* labels.
    """
    _, _, res = render_multi_axis_frame(
        adapter, B_lab_T, nv_axes=nv_axes, axis_offsets_hz=axis_offsets_hz
    )
    return res


def refine_a_merge(
    adapter: SimOSAdapter,
    bias_T: np.ndarray,
    w_hat: np.ndarray,
    p: int,
    q: int,
    a0: float,
    a_span: float,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    n_coarse: int = 21,
    n_fine: int = 21,
) -> tuple[float, float]:
    """Find ``a`` minimizing the diagonalized ``|f_p - f_q|`` near ``a0``.

    Two-stage grid search (the second-order transverse shift moves the true
    degeneracy slightly off the first-order ``a0``). Returns
    ``(a_merge, min_sep_hz)``.
    """
    bias = np.asarray(bias_T, dtype=float).reshape(3)
    w_hat = np.asarray(w_hat, dtype=float).reshape(3)

    def sep(a: float) -> float:
        centers = diagonalized_centers(adapter, bias + a * w_hat, nv_axes=nv_axes)
        return abs(float(centers[p] - centers[q]))

    best_a, best_sep, span, center = a0, np.inf, a_span, a0
    for n in (n_coarse, n_fine):
        grid = np.linspace(center - span, center + span, n)
        seps = np.array([sep(float(a)) for a in grid])
        idx = int(np.argmin(seps))
        best_a, best_sep = float(grid[idx]), float(seps[idx])
        span = (grid[1] - grid[0]) * 1.5  # zoom into the winning cell
        center = best_a
    return best_a, best_sep


def plan_dwell_merge(
    adapter: SimOSAdapter,
    bias_T: np.ndarray,
    p: int,
    q: int,
    approach_linewidths: float,
    gamma_fwhm_hz: float,
    sep_min_linewidths: float = 2.0,
    min_axis_projection_T: float = 0.4e-3,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    n_probe: int = 11,
) -> dict | None:
    """Plan a viable merge template for target line pair ``(p, q)``.

    By NV C3v symmetry a cross-axis merge coalesces the target pair AND its
    mirror ``(p^1, q^1)`` (the other transition of each axis) simultaneously, at
    the two reflected frequencies -- both are the same ``|B.n_i| = |B.n_j|``
    degeneracy (also the cross-relaxation resonance condition). A single-pair
    cross-axis merge is physically impossible in the noiseless L=8 model, so the
    coalescing set is the quartet ``{p, q, p^1, q^1}`` and the guard protects the
    four spectator lines.

    The ramp approaches from ``approach_linewidths * Gamma`` of separation
    (``delta_a`` from ``|w|``). Returns ``None`` if a spectator comes within
    ``sep_min_linewidths * Gamma`` of anything, if the two merge frequencies are
    not resolved, or if a projection drops below ``min_axis_projection_T``,
    anywhere over ``a in [a_merge - delta_a, a_merge + delta_a]``. Otherwise
    returns ``{"p", "q", "p_mirror", "q_mirror", "w_hat", "w_norm", "a_merge",
    "delta_a", "min_sep_hz"}``.
    """
    if p // 2 == q // 2:
        return None  # same-axis pairs merge only at a projection zero
    w_hat, w_norm = merge_direction(p, q, nv_axes)
    delta_a = delta_a_for_separation(approach_linewidths, gamma_fwhm_hz, w_norm)
    a0 = first_order_a_merge(bias_T, p, q, nv_axes)
    a_merge, min_sep_hz = refine_a_merge(adapter, bias_T, w_hat, p, q, a0, delta_a, nv_axes)
    if min_sep_hz > 0.5 * gamma_fwhm_hz:
        return None  # cannot bring the pair within half a linewidth

    pm, qm = p ^ 1, q ^ 1  # NV-symmetry mirror pair (coalesces simultaneously)
    bias = np.asarray(bias_T, dtype=float).reshape(3)
    sep_min_hz = sep_min_linewidths * gamma_fwhm_hz
    # Probe the whole ramp range: only the target and its mirror pair may go
    # sub-threshold; the four spectator lines stay resolved from everything, and
    # no axis projection may enter the label-degenerate zone.
    for a in np.linspace(a_merge - delta_a, a_merge + delta_a, n_probe):
        B = bias + a * w_hat
        B_par, _ = project_field_onto_axes(B, nv_axes=nv_axes)
        if float(np.min(np.abs(B_par))) < min_axis_projection_T:
            return None
        centers = diagonalized_centers(adapter, B, nv_axes=nv_axes)
        for u in range(len(centers)):
            for v in range(u + 1, len(centers)):
                pair = {u, v}
                if pair == {p, q} or pair == {pm, qm}:
                    continue  # target + mirror pairs are allowed to merge
                if abs(centers[u] - centers[v]) < sep_min_hz:
                    return None
    # The two merge frequencies (target at f+, mirror at f-) must stay resolved.
    centers_m = diagonalized_centers(adapter, bias + a_merge * w_hat, nv_axes=nv_axes)
    if abs((centers_m[p] + centers_m[q]) - (centers_m[pm] + centers_m[qm])) * 0.5 < sep_min_hz:
        return None
    return {
        "p": int(p),
        "q": int(q),
        "p_mirror": int(pm),
        "q_mirror": int(qm),
        "w_hat": w_hat,
        "w_norm": float(w_norm),
        "a_merge": float(a_merge),
        "delta_a": float(delta_a),
        "min_sep_hz": float(min_sep_hz),
    }


def enumerate_dwell_templates(
    adapter: SimOSAdapter,
    bias_T: np.ndarray,
    approach_linewidths: float,
    gamma_fwhm_hz: float,
    sep_min_linewidths: float = 2.0,
    min_axis_projection_T: float = 0.4e-3,
    nv_axes: np.ndarray = NV_AXES_UNIT,
) -> list[dict]:
    """All viable merge templates at this bias, ascending by |a_merge|.

    Cross-axis line pairs are planned via ``plan_dwell_merge``; the survivors
    coalesce the target pair (and its NV-symmetry mirror) while keeping the four
    spectator lines resolved and every projection out of the degenerate zone
    over the ramp range. Mirror-duplicate templates (``(p,q)`` and its mirror
    describe the same event) are de-duplicated.
    """
    n_lines = 2 * len(nv_axes)
    templates: list[dict] = []
    seen_events: set[frozenset] = set()
    for p in range(n_lines):
        for q in range(p + 1, n_lines):
            # A merge event = {target pair, mirror pair}; skip its duplicate.
            event = frozenset({frozenset({p, q}), frozenset({p ^ 1, q ^ 1})})
            if event in seen_events:
                continue
            plan = plan_dwell_merge(
                adapter,
                bias_T,
                p,
                q,
                approach_linewidths,
                gamma_fwhm_hz,
                sep_min_linewidths=sep_min_linewidths,
                min_axis_projection_T=min_axis_projection_T,
                nv_axes=nv_axes,
            )
            if plan is not None:
                seen_events.add(event)
                templates.append(plan)
    templates.sort(key=lambda d: abs(d["a_merge"]))
    return templates


def delta_a_for_separation(sep_linewidths: float, gamma_fwhm_hz: float, w_norm: float) -> float:
    """External-field amplitude (Tesla) giving a first-order pair separation of
    ``sep_linewidths * Gamma`` along a direction with ``|w| = w_norm``."""
    return sep_linewidths * gamma_fwhm_hz / (GAMMA_HZ_PER_T * w_norm)
