"""Zero-retrain identity re-decoders for the learned tracker (increment-2c lever A).

These operate ENTIRELY post-hoc on a trained checkpoint's inference outputs. The field
estimate ``b_est`` is never modified, so the vector/lock claim is invariant *by construction*:
``sequence_metrics_row`` reads the FIELD metrics (angular error, loss-of-lock) only from
``B_est``, and reads IDENTITY (misassoc, ID-switch/opportunity) from the per-slot claimed line
center ``tracked_hz (T, 8)``. Each decoder here re-derives that ``tracked_hz`` — the signal
that carries identity into the metric — without touching ``b_est``. Slot ``l`` always claims
axis ``LINE_AXIS_8[l]``; identity is whether slot ``l``'s decoded center stays on its physical
line through a crossing.

Non-circularity (see ``docs/design/04_identity_gap_solution_survey.md`` §scoping): ``b_est``
comes from ``state_to_proj``→BLUE and never consumes the assignment (``learned.py:543``, ``585``),
so decoding identity *from* ``b_est`` (A1/A3) is not circular.

Decoders
--------
- :func:`smoothed_exclusive_decode` (A2) — fixed-lag temporal smoothing of the saved
  ``(T, 8, K)`` association scores, then per-frame exclusive one-to-one assignment. A mean-field
  FHMM decode: the emission for each slot is averaged over a ``±lag`` window (deferring the
  commit so identity can resolve a few frames after the crossing) and per-frame exclusivity is a
  Hungarian assignment. ``lag`` is the added decision latency in frames; ``lag=0`` reduces to an
  instantaneous exclusive commit on the raw scores (the reference the deferral is measured against).
- :func:`physics_anchored_decode` (A1) — predict all 8 line centers from ``b_est`` via the known
  Zeeman forward map, then assign candidates one-to-one to those predictions; a slot with no
  candidate inside the capture radius falls back to its physics-predicted center. No scores used.
- :func:`stacked_decode` (A3) — A2's smoothed scores biased by A1's physics prior, with the same
  physics fallback. Combines the temporal smoothing with the physics anchor.

All decoders take one sequence (numpy) and return ``tracked_hz (T, 8)`` in Hz.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from odmr_vector_tracking.vector.geometry import (
    GAMMA_E_HZ_PER_T,
    LINE_AXIS_8,
    LINE_SIGN_8,
    NV_AXES_UNIT,
    ZFS_D_HZ,
    common_mode_shift,
)

N_LINES = 8


def predicted_line_positions(
    b_est_T3: np.ndarray, axis_offsets_hz: np.ndarray | None = None
) -> np.ndarray:
    """Batched Zeeman forward map: ``b_est (T, 3)`` Tesla → 8 line centers ``(T, 8)`` Hz.

    Vectorized :func:`geometry.resonance_frequencies_diagonalized` over time — the same
    first-order + common-mode geometry the BLUE decoder inverts (deliberately NOT a richer
    Hamiltonian: the prediction must be consistent with the tracker's own field model).

    ``axis_offsets_hz`` (4,) — optional per-axis static strain/E-field ZFS offsets (dwell-lineage
    manifest key). A common-mode per-orientation shift: BOTH transitions of axis ``i`` move by
    ``offsets[i]`` (the split is preserved, so the splitting-based field decode is blind to it;
    the *center* prediction is not — that is the identity cue).
    """
    B = np.asarray(b_est_T3, dtype=np.float64).reshape(-1, 3)              # (T, 3)
    B_par = B @ NV_AXES_UNIT.T                                             # (T, 4) signed B·n_i
    B_perp = np.linalg.norm(
        B[:, None, :] - B_par[:, :, None] * NV_AXES_UNIT[None, :, :], axis=2
    )                                                                     # (T, 4)
    first = GAMMA_E_HZ_PER_T * LINE_SIGN_8.astype(np.float64)[None, :] * B_par[:, LINE_AXIS_8]
    cm = common_mode_shift(B_perp)[:, LINE_AXIS_8]                         # (T, 8)
    out = ZFS_D_HZ + first + cm
    if axis_offsets_hz is not None:
        out = out + np.asarray(axis_offsets_hz, dtype=np.float64)[LINE_AXIS_8][None, :]
    return out


def _boxsum_time(x: np.ndarray, lag: int) -> np.ndarray:
    """Sum ``x`` over a ``[t-lag, t+lag]`` window along axis 0 (edge-clipped). ``lag<=0`` → x."""
    if lag <= 0:
        return x
    T = x.shape[0]
    cum = np.concatenate([np.zeros((1, *x.shape[1:]), dtype=x.dtype), np.cumsum(x, axis=0)])
    lo = np.clip(np.arange(T) - lag, 0, T)
    hi = np.clip(np.arange(T) + lag + 1, 0, T)
    return cum[hi] - cum[lo]


def _assign_tracks(cost_LK: np.ndarray) -> np.ndarray:
    """Exclusive one-to-one assignment of 8 slots to K candidates minimizing cost. ``→ (8,)``.

    ``K >= 8`` so every slot gets a distinct candidate (rectangular Hungarian).
    """
    rows, cols = linear_sum_assignment(cost_LK)
    out = np.full(cost_LK.shape[0], -1, dtype=np.int64)
    out[rows] = cols
    return out


def smoothed_exclusive_decode(
    scores: np.ndarray, cand_pos_hz: np.ndarray, lag: int = 5
) -> np.ndarray:
    """A2 — fixed-lag smoothed, per-frame exclusive decode of the association scores.

    Parameters
    ----------
    scores : ``(T, 8, K)`` association logits (slot × candidate) per frame.
    cand_pos_hz : ``(T, K)`` candidate centers in Hz.
    lag : half-window; the added decision latency in frames. ``0`` = instantaneous exclusive commit.

    Returns ``tracked_hz (T, 8)`` in Hz.
    """
    S = _boxsum_time(np.asarray(scores, dtype=np.float64), lag)           # (T, 8, K)
    T = S.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        assign = _assign_tracks(-S[t])                                    # maximize score
        out[t] = cand_pos_hz[t, assign]
    return out


def physics_anchored_decode(
    b_est_T3: np.ndarray,
    cand_pos_hz: np.ndarray,
    capture_radius_hz: float,
    axis_offsets_hz: np.ndarray | None = None,
) -> np.ndarray:
    """A1 — assign candidates to the 8 physics-predicted line centers from ``b_est``.

    A slot whose nearest assigned candidate is beyond ``capture_radius_hz`` falls back to its
    physics-predicted center (the mechanism by which a good field estimate keeps identity through
    a crossing even when the detector misses the faint line). Uses no association scores → the
    decode cannot borrow the very assignment it is meant to replace. ``axis_offsets_hz`` makes
    the prediction strain-aware (dwell lineage).
    """
    pred = predicted_line_positions(b_est_T3, axis_offsets_hz)           # (T, 8) Hz
    T = pred.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        cost = np.abs(pred[t][:, None] - cand_pos_hz[t][None, :])        # (8, K)
        assign = _assign_tracks(cost)
        chosen = cand_pos_hz[t, assign]
        far = np.abs(chosen - pred[t]) > capture_radius_hz
        out[t] = np.where(far, pred[t], chosen)
    return out


def stacked_decode(
    scores: np.ndarray,
    b_est_T3: np.ndarray,
    cand_pos_hz: np.ndarray,
    capture_radius_hz: float,
    linewidth_hz: float,
    lag: int = 5,
    mu: float = 1.0,
    axis_offsets_hz: np.ndarray | None = None,
) -> np.ndarray:
    """A3 — A2 smoothed scores biased toward A1's physics prediction, with physics fallback.

    Per-frame exclusive assignment on ``-S_smooth + mu·|cand − pred|/linewidth``: the physics
    prior (``mu`` in units of one score-point per linewidth of position error) breaks ties the
    scores leave ambiguous at a crossing; the temporal smoothing defers the commit. A slot whose
    assigned candidate lands beyond the capture radius falls back to its physics center.
    ``axis_offsets_hz`` makes the physics prior strain-aware (dwell lineage).
    """
    S = _boxsum_time(np.asarray(scores, dtype=np.float64), lag)          # (T, 8, K)
    pred = predicted_line_positions(b_est_T3, axis_offsets_hz)           # (T, 8) Hz
    T = S.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        pos_cost = np.abs(cand_pos_hz[t][None, :] - pred[t][:, None]) / linewidth_hz
        assign = _assign_tracks(-S[t] + mu * pos_cost)                   # (8,)
        chosen = cand_pos_hz[t, assign]
        far = np.abs(chosen - pred[t]) > capture_radius_hz
        out[t] = np.where(far, pred[t], chosen)
    return out


# ==========================================================================================
# Increment-4 coalescence-aware overlay decoders (D-BP / D-OV / D-UM / D-JV).
#
# The held-family identity gap is track coalescence — a structural property of marginal-style
# trackers. The verified-literature fix is to treat identity as a decode-side OVERLAY that never
# feeds back into the state estimate (Set-JPDA, Svensson 2011; unresolved-measurement MHT, Koch &
# van Keuk 1997; BP-reduces-coalescence, Kropfreiter 2023). All four decoders below are
# zero-retrain and field-safe by construction: they rewrite only ``tracked_hz``; ``b_est`` is
# never modified, and D-BP/D-JV never even read it.
# ==========================================================================================


def association_marginals(
    scores: np.ndarray, gate_m: int = 5, slot_miss: float = 0.05, iters: int = 40
) -> np.ndarray:
    """D-BP core — per-frame one-to-one association marginals via loopy sum-product.

    Williams–Lau belief propagation for the data-association permanent (the ``JPDAwithLBP``
    reference; Kropfreiter 2308.06326): each slot associates to one candidate or misses
    (weight ``slot_miss``); each candidate is claimed by at most one slot (clutter weight 1).
    Exact on tree-structured gated graphs, a close approximation otherwise — far cheaper than an
    exact permanent and the method the literature actually deploys.

    Parameters
    ----------
    scores : ``(..., L, K)`` association logits.
    gate_m : keep only each slot's top-``gate_m`` candidates (M≤5 per the dispatch); the rest get
        zero weight (top-M gating).
    slot_miss : missed-detection weight (relative to the row-max candidate weight of 1).
    iters : LBP message-passing sweeps.

    Returns ``(..., L, K)`` marginals ``p[l, k]`` (each slot's row + its miss mass sums to 1).
    """
    S = np.asarray(scores, dtype=np.float64)
    lead, L, K = S.shape[:-2], S.shape[-2], S.shape[-1]
    S2 = S.reshape(-1, L, K)
    w = np.exp(S2 - S2.max(axis=-1, keepdims=True))          # row-max candidate -> weight 1
    if gate_m < K:
        drop = np.argsort(S2, axis=-1)[..., : K - gate_m]     # lowest (K-m) per row
        np.put_along_axis(w, drop, 0.0, axis=-1)
    nu = np.ones_like(w)                                      # nu[b, l, k] == message k -> l
    for _ in range(iters):
        wn = w * nu
        denom_mu = slot_miss + wn.sum(axis=-1, keepdims=True) - wn         # exclude k
        mu = np.divide(w, denom_mu, out=np.zeros_like(w), where=denom_mu > 0)
        wm = w * mu
        denom_nu = 1.0 + wm.sum(axis=-2, keepdims=True) - wm              # exclude l
        nu = np.divide(1.0, denom_nu, out=np.ones_like(w), where=denom_nu > 0)
    wn = w * nu
    p = wn / (slot_miss + wn.sum(axis=-1, keepdims=True))     # marginal; miss = slot_miss / Z
    return p.reshape(*lead, L, K)


def bp_marginal_decode(
    scores: np.ndarray, cand_pos_hz: np.ndarray, lag: int = 5,
    gate_m: int = 5, slot_miss: float = 0.05,
) -> np.ndarray:
    """D-BP — temporally-accumulated marginal-association decode.

    Per-frame association marginals (:func:`association_marginals`) are box-summed over a ``±lag``
    window and read out with a per-frame exclusive (Hungarian) assignment on the *accumulated*
    marginals — never a hard per-frame argmax. Uses only scores + candidate positions (the
    positions carry no identity into the association), so the decode is non-circular by
    construction. ``lag`` is the added decision latency in frames.
    """
    p = association_marginals(scores, gate_m=gate_m, slot_miss=slot_miss)  # (T, 8, K)
    A = _boxsum_time(p, lag)
    cand = np.asarray(cand_pos_hz, dtype=np.float64)
    T = A.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        out[t] = cand[t, _assign_tracks(-A[t])]              # maximize accumulated marginal
    return out


def sinkhorn_doubly_stochastic(mat: np.ndarray, iters: int = 60, eps: float = 1e-12) -> np.ndarray:
    """Row/column alternating normalization to the nearest doubly-stochastic matrix.

    Decode-time only (the 2c Sinkhorn *training-loss* elimination is a different mechanism — a
    doubly-stochastic identity belief here is a soft permutation, not a training objective).
    """
    Q = np.clip(np.asarray(mat, dtype=np.float64), eps, None)
    for _ in range(iters):
        Q = Q / Q.sum(axis=1, keepdims=True)
        Q = Q / Q.sum(axis=0, keepdims=True)
    return Q


def identity_overlay_decode(
    scores: np.ndarray, b_est_T3: np.ndarray, cand_pos_hz: np.ndarray, track_hz: np.ndarray,
    linewidth_hz: float, lag: int = 5, gate_m: int = 5, slot_miss: float = 0.05,
    sinkhorn_iters: int = 40,
) -> np.ndarray:
    """D-OV — Set-JPDA-style identity overlay (Svensson SPIE 2011).

    Positions stay label-free: the returned centers are always a *permutation* of the deployed
    ``track_hz`` slots — the overlay only re-labels which slot carries which physical line. An
    8×8 identity belief (slot × line) is accumulated from the D-BP marginals mapped onto the
    physics-predicted line centers (Gaussian in linewidths), box-summed over ``±lag`` and
    renormalized doubly-stochastic each frame (belief *spreads* during a merge and
    *re-concentrates* after, using evidence from both sides). ``b_est`` is read only as the
    physics prior for the belief — never modified.
    """
    p = association_marginals(scores, gate_m=gate_m, slot_miss=slot_miss)   # (T, 8slot, K)
    pred = predicted_line_positions(b_est_T3)                              # (T, 8line)
    cand = np.asarray(cand_pos_hz, dtype=np.float64)
    track = np.asarray(track_hz, dtype=np.float64)
    d = (cand[:, None, :] - pred[:, :, None]) / linewidth_hz               # (T, line, K)
    kern = np.exp(-0.5 * d * d)
    evidence = np.einsum("tlk,tjk->tlj", p, kern)                          # (T, slot, line)
    S = _boxsum_time(np.log(np.clip(evidence, 1e-12, None)), lag)
    T = track.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        Q = sinkhorn_doubly_stochastic(np.exp(S[t] - S[t].max()), iters=sinkhorn_iters)
        slots, lines = linear_sum_assignment(-Q)             # one-to-one slot<->line
        slot_for_line = np.empty(N_LINES, dtype=np.int64)
        slot_for_line[lines] = slots
        out[t] = track[t, slot_for_line]                     # line j read from its carrying slot
    return out


def _components(adj: np.ndarray) -> list[list[int]]:
    """Connected components of a boolean adjacency matrix (with self-loops)."""
    n = adj.shape[0]
    seen = np.zeros(n, dtype=bool)
    comps: list[list[int]] = []
    for i in range(n):
        if seen[i]:
            continue
        stack, comp = [i], []
        seen[i] = True
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in range(n):
                if adj[u, v] and not seen[v]:
                    seen[v] = True
                    stack.append(v)
        comps.append(comp)
    return comps


def unresolved_merge_decode(
    scores: np.ndarray, b_est_T3: np.ndarray, cand_pos_hz: np.ndarray,
    capture_radius_hz: float, linewidth_hz: float, r_cells: float = 1.0,
) -> np.ndarray:
    """D-UM — unresolved-measurement merged hypotheses (Koch & van Keuk 1997).

    When two lines' physics-predicted centers fall within a resolution radius ``r_cells`` × one
    linewidth, they are *unresolved*: the merged hypothesis carries identity through the dwell
    (both lines hold their physics-predicted centers) instead of a forced exclusive pick that
    would swap them. Resolved (well-separated) lines are assigned exclusively to the nearest
    candidate with the usual capture-radius physics fallback. Sweeping ``r_cells`` ∈ {0.5, 1, 2}
    trades how aggressively the decoder declares a merge. ``scores`` is accepted for a composed
    call but the standalone decode is physics-anchored.
    """
    pred = predicted_line_positions(b_est_T3)
    cand = np.asarray(cand_pos_hz, dtype=np.float64)
    r_hz = r_cells * linewidth_hz
    T = pred.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        sep = np.abs(pred[t][:, None] - pred[t][None, :])
        comps = _components(sep < r_hz)
        res = np.array(pred[t], dtype=np.float64)            # default: physics identity
        singles = [c[0] for c in comps if len(c) == 1]
        if singles:
            cost = np.abs(cand[t][None, :] - pred[t][singles][:, None])   # (S, K)
            rows, cols = linear_sum_assignment(cost)
            for r_i, c_i in zip(rows, cols):
                line = singles[r_i]
                chosen = cand[t, c_i]
                res[line] = chosen if abs(chosen - pred[t, line]) <= capture_radius_hz \
                    else pred[t, line]
        out[t] = res
    return out


def _frame_beam(scores_LK: np.ndarray, beam: int, merged: bool) -> list[tuple[np.ndarray, float]]:
    """Beam of joint assignments for one frame: the Hungarian matching + pairwise-swap alternatives.

    The Hungarian (greedy) matching is always element 0 with the minimal frame cost — this is what
    makes the lag-0 / no-penalty limit reduce to greedy. Pairwise swaps are the identity-swap
    hypotheses that matter at a crossing; ``merged`` additionally admits states where two slots
    share a candidate (the D-UM composition).
    """
    L = scores_LK.shape[0]
    base = _assign_tracks(-scores_LK)

    def fcost(a):
        return float(-scores_LK[np.arange(L), a].sum())

    seen = {tuple(base)}
    cands: list[tuple[np.ndarray, float]] = [(base, fcost(base))]
    for i in range(L):
        for j in range(i + 1, L):
            a = base.copy()
            a[i], a[j] = a[j], a[i]
            key = tuple(a)
            if key not in seen:
                seen.add(key)
                cands.append((a, fcost(a)))
            if merged:                                       # slot j joins slot i's candidate
                a2 = base.copy()
                a2[j] = base[i]
                k2 = tuple(a2)
                if k2 not in seen:
                    seen.add(k2)
                    cands.append((a2, fcost(a2)))
    cands.sort(key=lambda x: x[1])
    return cands[:beam]


def joint_viterbi_decode(
    scores: np.ndarray, cand_pos_hz: np.ndarray, lag: int = 5, penalty: float = 1.0,
    linewidth_hz: float | None = None, beam: int = 16, merged: bool = False,
) -> np.ndarray:
    """D-JV — joint fixed-lag Viterbi over the gated joint-assignment space.

    Generalizes the per-slot ``smooth`` decode to a *joint* one: each state is a whole-frame
    assignment (from :func:`_frame_beam`), the frame cost is the negative total association score,
    and the transition penalty discourages a slot jumping lines (per-slot candidate movement in
    linewidths, scaled by ``penalty``). Fixed-lag ``lag`` defers each frame's commit by ``lag``
    frames. Its lag-0, ``penalty=0`` limit reproduces ``greedy`` (the Hungarian matching is beam
    element 0 with minimal frame cost). ``merged=True`` admits D-UM shared-candidate states.
    """
    S = np.asarray(scores, dtype=np.float64)
    cand = np.asarray(cand_pos_hz, dtype=np.float64)
    T, L, _ = S.shape
    lw = 1.0 if linewidth_hz is None else float(linewidth_hz)
    beams = [_frame_beam(S[t], beam, merged) for t in range(T)]
    V: list[np.ndarray] = [np.array([fc for _, fc in beams[0]])]
    BP: list[list[int]] = [[-1] * len(beams[0])]
    for t in range(1, T):
        cur, prev = beams[t], beams[t - 1]
        Vt = np.empty(len(cur))
        bpt = [0] * len(cur)
        for ci, (ac, fc) in enumerate(cur):
            if penalty > 0:
                trans = penalty * np.abs(cand[t, ac][None, :] -
                                         cand[t - 1, np.array([ap for ap, _ in prev])]).sum(axis=1) / lw
                costs = V[t - 1] + trans
            else:
                costs = V[t - 1]
            bi = int(np.argmin(costs))
            Vt[ci], bpt[ci] = fc + costs[bi], bi
        V.append(Vt)
        BP.append(bpt)
    out = np.empty((T, L), dtype=np.float64)
    for t in range(T):
        te = min(T - 1, t + lag)
        si = int(np.argmin(V[te]))
        for tt in range(te, t, -1):
            si = BP[tt][si]
        out[t] = cand[t, beams[t][si][0]]
    return out


# ==========================================================================================
# Increment-5 physics-cue decodes (dwell lineage: sequence_dwell_v1_cues).
#
# The NV-NV cross-relaxation PL dip fires exactly at the inter-orientation degeneracy
# |B·n_i| = |B·n_j| (Espinós/Budker resonance condition) — i.e. it is a physical MERGE MARKER
# in the raw spectrum, far deeper (~1.8% at 3.8 ppm) than the ODMR lines themselves (≤0.36%).
# The gated decode reads the marker from the spectrum and holds physics identity for the
# marked (unresolved) lines only — D-UM with the unresolved set given by measurement instead
# of a prediction-separation radius. Zero-retrain; ``b_est`` untouched.
# ==========================================================================================


def cr_dwell_marker(
    spectra: np.ndarray, frequencies: np.ndarray, depth_thresh: float
) -> tuple[np.ndarray, list[list[float]]]:
    """Detect cross-relaxation dwell markers in raw spectra.

    Per frame, any contiguous frequency run where the PL depth ``1 - spectrum`` exceeds
    ``depth_thresh`` is one marker; its frequency is the run's deepest point. The threshold sits
    between the deepest possible line stack (two merged lines, ≲0.8%) and the CR dip (~1.8% at
    the 3.8 ppm calibration): a plain line merge does NOT fire the marker, the CR feature does.

    Returns ``(marked (T,) bool, dip_freqs)`` — ``dip_freqs[t]`` lists the marker frequencies
    (Hz) of frame ``t`` (empty when unmarked; the mirror degeneracy yields a second entry).
    """
    S = np.asarray(spectra, dtype=np.float64)
    F = np.asarray(frequencies, dtype=np.float64)
    depth = 1.0 - S                                          # (T, F)
    over = depth > float(depth_thresh)
    T = S.shape[0]
    marked = over.any(axis=1)
    dip_freqs: list[list[float]] = []
    for t in range(T):
        if not marked[t]:
            dip_freqs.append([])
            continue
        idx = np.where(over[t])[0]
        breaks = np.where(np.diff(idx) > 1)[0]
        starts = np.concatenate([[0], breaks + 1])
        ends = np.concatenate([breaks, [idx.size - 1]])
        freqs = []
        for s0, e0 in zip(starts, ends):
            run = idx[s0:e0 + 1]
            freqs.append(float(F[run[np.argmax(depth[t, run])]]))
        dip_freqs.append(freqs)
    return marked, dip_freqs


def cr_gated_decode(
    spectra: np.ndarray,
    frequencies: np.ndarray,
    b_est_T3: np.ndarray,
    cand_pos_hz: np.ndarray,
    capture_radius_hz: float,
    linewidth_hz: float,
    depth_thresh: float,
    axis_offsets_hz: np.ndarray | None = None,
    r_match_lw: float = 2.0,
) -> np.ndarray:
    """CR-marker-gated decode: hold physics identity for the lines the marker says are merged.

    Frames with a CR marker: every line whose physics-predicted center lies within
    ``r_match_lw`` linewidths of a marker frequency is *unresolved* — it holds its (optionally
    strain-aware) physics-predicted center through the dwell instead of a forced exclusive pick.
    All other lines (and all unmarked frames) get the exclusive nearest-candidate assignment
    with the usual capture-radius physics fallback (A1 semantics). No association scores used.
    """
    pred = predicted_line_positions(b_est_T3, axis_offsets_hz)           # (T, 8)
    cand = np.asarray(cand_pos_hz, dtype=np.float64)
    marked, dip_freqs = cr_dwell_marker(spectra, frequencies, depth_thresh)
    r_hz = r_match_lw * linewidth_hz
    T = pred.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        held = np.zeros(N_LINES, dtype=bool)
        if marked[t]:
            for fd in dip_freqs[t]:
                held |= np.abs(pred[t] - fd) < r_hz
        res = np.array(pred[t], dtype=np.float64)                        # held lines keep physics
        free = np.where(~held)[0]
        if free.size:
            cost = np.abs(cand[t][None, :] - pred[t][free][:, None])     # (n_free, K)
            rows, cols = linear_sum_assignment(cost)
            for r_i, c_i in zip(rows, cols):
                line = free[r_i]
                chosen = cand[t, c_i]
                res[line] = chosen if abs(chosen - pred[t, line]) <= capture_radius_hz \
                    else pred[t, line]
        out[t] = res
    return out
