"""Tracker evaluation metrics — pure functions.

The four headline metrics from the design dossier (``docs/design/02_approach_and_testbed.md``),
plus the helpers that turn a tracker's claimed identities into a scorable comparison against
ground truth:

- :func:`vector_angular_error` — per-frame angle between estimated and true B.
- :func:`association_accuracy` / :func:`id_switch_rate` — identity tracking, scored especially on
  ``line_collision``-flagged frames (the hard regime).
- :func:`recovery_time` — time from a disturbance until error returns below threshold.
- :func:`dynamic_range` — max |B| before *irrecoverable* loss of lock (report relative to bias,
  never as an absolute record — honest-ceiling guardrail).

All functions are pure (numpy in, scalars/arrays out) and unit-tested on hand-built inputs with
known answers; they do not depend on any dataset existing.
"""

from __future__ import annotations

import numpy as np

INF = float("inf")


# --- vector error -----------------------------------------------------------------------

def vector_angular_error(
    B_true: np.ndarray, B_est: np.ndarray, eps_T: float = 1e-12
) -> np.ndarray:
    """Per-frame angular error (degrees) between estimated and true B-field.

    Parameters
    ----------
    B_true, B_est
        ``(T, 3)`` lab-frame field arrays (Tesla).
    eps_T
        Magnitude floor; frames where either vector is below ``eps_T`` return ``nan`` (angle
        undefined for a near-zero field).

    Returns
    -------
    np.ndarray
        ``(T,)`` angular error in degrees (``nan`` where undefined).
    """
    B_true = np.asarray(B_true, dtype=np.float64)
    B_est = np.asarray(B_est, dtype=np.float64)
    nt = np.linalg.norm(B_true, axis=1)
    ne = np.linalg.norm(B_est, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.einsum("ij,ij->i", B_true, B_est) / (nt * ne)
    ang = np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))
    ang[(nt < eps_T) | (ne < eps_T)] = np.nan
    return ang


def finite_frame_pairs(B_true: np.ndarray, B_est: np.ndarray) -> np.ndarray:
    """Frames where both field vectors have three finite components."""
    true = np.asarray(B_true, dtype=np.float64)
    est = np.asarray(B_est, dtype=np.float64)
    return np.isfinite(true).all(axis=1) & np.isfinite(est).all(axis=1)


def vector_rmse(B_true: np.ndarray, B_est: np.ndarray) -> float:
    """Root mean squared Euclidean field error (Tesla) over finite frame pairs."""
    valid = finite_frame_pairs(B_true, B_est)
    if not valid.any():
        return float("nan")
    delta = np.asarray(B_est, dtype=np.float64)[valid] - np.asarray(B_true, dtype=np.float64)[valid]
    return float(np.sqrt(np.mean(np.sum(delta**2, axis=1))))


def magnitude_error(B_true: np.ndarray, B_est: np.ndarray) -> np.ndarray:
    """Signed magnitude error (Tesla), with ``nan`` for nonfinite frame pairs."""
    valid = finite_frame_pairs(B_true, B_est)
    result = np.full(valid.shape, np.nan)
    result[valid] = (
        np.linalg.norm(np.asarray(B_est, dtype=np.float64)[valid], axis=1)
        - np.linalg.norm(np.asarray(B_true, dtype=np.float64)[valid], axis=1)
    )
    return result


def vector_bias(B_true: np.ndarray, B_est: np.ndarray) -> np.ndarray:
    """Mean signed estimate-minus-truth vector over finite frame pairs, in Tesla."""
    valid = finite_frame_pairs(B_true, B_est)
    if not valid.any():
        return np.full(3, np.nan)
    delta = np.asarray(B_est, dtype=np.float64)[valid] - np.asarray(B_true, dtype=np.float64)[valid]
    return np.mean(delta, axis=0)


def full_vector_lock(
    B_true: np.ndarray,
    B_est: np.ndarray,
    mag_tol_frac: float = 0.05,
    angle_tol_deg: float = 5.0,
    eps_T: float = 1e-12,
) -> np.ndarray:
    """Per-frame lock when magnitude and angular errors both meet their limits.

    A frame with a near-zero or nonfinite field is unlocked. Magnitude tolerance
    is a fraction of the true magnitude; angle tolerance is in degrees.
    """
    true_mag = np.linalg.norm(np.asarray(B_true, dtype=np.float64), axis=1)
    est_mag = np.linalg.norm(np.asarray(B_est, dtype=np.float64), axis=1)
    angle = vector_angular_error(B_true, B_est, eps_T=eps_T)
    return (
        np.isfinite(true_mag) & np.isfinite(est_mag) & np.isfinite(angle)
        & (true_mag >= eps_T) & (est_mag >= eps_T)
        & (np.abs(est_mag - true_mag) <= mag_tol_frac * true_mag)
        & (angle <= angle_tol_deg)
    )


def full_vector_lock_stats(lock: np.ndarray) -> dict[str, float | int | bool]:
    """Acquisition and irrecoverable loss from a per-frame lock mask.

    Loss starts at the first unlocked frame whose entire suffix is unlocked.
    A sequence that never acquires is lost from frame zero.
    """
    held = np.asarray(lock, dtype=bool)
    acquired = np.flatnonzero(held)
    acq_index = int(acquired[0]) if acquired.size else -1
    loss_index = -1
    if acq_index < 0:
        loss_index = 0 if held.size else -1
    else:
        unlocked = ~held
        suffix_unlocked = np.logical_and.accumulate(unlocked[::-1])[::-1]
        losses = np.flatnonzero(suffix_unlocked & (np.arange(held.size) > acq_index))
        if losses.size:
            loss_index = int(losses[0])
    return {
        "lock_frac": float(held.mean()) if held.size else 0.0,
        "acq_index": acq_index,
        "lost": acq_index < 0 or loss_index >= 0,
        "loss_index": loss_index,
    }


# --- association ground-truth helpers ---------------------------------------------------

def physical_line_index(
    tracked_freqs: np.ndarray,
    resonance_freqs: np.ndarray,
    capture_radius_hz: float | None = None,
) -> np.ndarray:
    """Nearest ground-truth line index for each lock at each frame.

    ``tracked_freqs`` ``(T, L)`` (lock centers) → for each (t, lock) the index of the closest
    ground-truth resonance in ``resonance_freqs`` ``(T, Lgt)``. This is the *physical* line the
    lock is actually sitting on, regardless of the identity it claims.

    ``capture_radius_hz``: if given, a lock farther than this from every ground-truth line is
    **unassigned** and gets index ``-1`` — a wandering/frozen lock is then "on no line" rather
    than silently attributed to whichever line happens to be least far away.
    """
    tracked = np.asarray(tracked_freqs, dtype=np.float64)
    gt = np.asarray(resonance_freqs, dtype=np.float64)
    # (T, L, Lgt) distances → argmin over gt.
    d = np.abs(tracked[:, :, None] - gt[:, None, :])
    idx = np.argmin(d, axis=2)
    if capture_radius_hz is not None:
        nearest = np.take_along_axis(d, idx[:, :, None], axis=2)[:, :, 0]
        idx = np.where(nearest <= float(capture_radius_hz), idx, -1)
    return idx


def resolve_true_axis(
    tracked_freqs: np.ndarray,
    resonance_freqs: np.ndarray,
    line_axis: np.ndarray,
    capture_radius_hz: float | None = None,
) -> np.ndarray:
    """Ground-truth NV axis each lock is *physically* on, ``(T, L)``.

    Combines :func:`physical_line_index` with the per-frame ``line_axis`` labels ``(T, Lgt)``.
    Compare against the tracker's claimed ``pred_axis`` to score association. With a
    ``capture_radius_hz``, unassigned locks get axis ``-1`` (never matches a claimed axis, so
    they score as misassociated — being on no line is not correct association).
    """
    phys = physical_line_index(tracked_freqs, resonance_freqs, capture_radius_hz)  # (T, L)
    line_axis = np.asarray(line_axis)
    ta = np.take_along_axis(line_axis, np.clip(phys, 0, None), axis=1)
    if capture_radius_hz is not None:
        ta = np.where(phys < 0, np.int8(-1), ta.astype(np.int8))
    return ta


# --- association metrics ----------------------------------------------------------------

def association_accuracy(
    pred_axis: np.ndarray,
    true_axis: np.ndarray,
    line_collision: np.ndarray | None = None,
) -> dict[str, float]:
    """Fraction of (frame, lock) entries whose claimed axis matches the physical axis.

    Parameters
    ----------
    pred_axis, true_axis
        ``(T, L)`` claimed vs physical NV-axis ids.
    line_collision
        Optional ``(T, L)`` bool. If given, also report accuracy split by whether each entry is
        in a labeled collision — ``in_collision`` is the hard-regime score the thesis targets.

    Returns
    -------
    dict
        ``{"overall", "in_collision", "out_collision"}`` (the latter two ``nan`` if no mask or
        an empty subset).
    """
    pred = np.asarray(pred_axis)
    true = np.asarray(true_axis)
    correct = pred == true
    out: dict[str, float] = {"overall": float(correct.mean())}
    if line_collision is not None:
        mask = np.asarray(line_collision, dtype=bool)
        out["in_collision"] = float(correct[mask].mean()) if mask.any() else float("nan")
        out["out_collision"] = (
            float(correct[~mask].mean()) if (~mask).any() else float("nan")
        )
    return out


def id_switch_rate(physical_assignment: np.ndarray) -> dict[str, float]:
    """Raw frame-to-frame identity-switch statistics from physical-line assignments.

    A switch is a lock changing which physical line it sits on between consecutive frames,
    counted only when **both** frames are assigned (index ≥ 0); transitions to/from the
    unassigned state (``-1``) are fragmentation, not identity switches, and are reported via
    ``unassigned_frac`` instead.

    Caveat: this raw count saturates with flicker while two lines dwell within a linewidth of
    each other (attribution is genuinely ambiguous mid-merge). For the discriminative
    through-crossing statistic, use :func:`id_switches_per_opportunity`, which compares
    identity across each crossing event with pre/post windows.

    Parameters
    ----------
    physical_assignment
        ``(T, L)`` int — output of :func:`physical_line_index`.

    Returns
    -------
    dict
        ``{"count", "rate", "unassigned_frac"}`` — switches, switches per valid
        (lock, frame-transition), and the fraction of (frame, lock) entries unassigned.
    """
    pa = np.asarray(physical_assignment)
    T = pa.shape[0]
    unassigned = float((pa < 0).mean()) if pa.size else 0.0
    if T < 2:
        return {"count": 0.0, "rate": 0.0, "unassigned_frac": unassigned}
    valid = (pa[1:] >= 0) & (pa[:-1] >= 0)
    switches = int(((pa[1:] != pa[:-1]) & valid).sum())
    denom = int(valid.sum())
    return {
        "count": float(switches),
        "rate": float(switches) / float(denom) if denom else 0.0,
        "unassigned_frac": unassigned,
    }


# --- crossing events + per-opportunity identity switches ---------------------------------

def crossing_events(collision_mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous collision runs as inclusive ``(first, last)`` frame spans.

    ``collision_mask`` is the per-frame ``(T,)`` bool from the v1 contract. Each run is one
    crossing *event* (an identity-switch opportunity for every lock).
    """
    cm = np.asarray(collision_mask, dtype=bool)
    if not cm.any():
        return []
    idx = np.where(cm)[0]
    breaks = np.where(np.diff(idx) > 1)[0]
    starts = np.concatenate([[idx[0]], idx[breaks + 1]])
    ends = np.concatenate([idx[breaks], [idx[-1]]])
    return [(int(s), int(e)) for s, e in zip(starts, ends)]


def _window_majority(pa_window: np.ndarray) -> int:
    """Majority assigned line over a ``(W,)`` window; ``-1`` if nothing assigned."""
    valid = pa_window[pa_window >= 0]
    if valid.size == 0:
        return -1
    return int(np.bincount(valid).argmax())


def id_switches_per_opportunity(
    physical_assignment: np.ndarray,
    events: list[tuple[int, int]],
    window: int = 5,
) -> dict[str, float]:
    """MOT-style identity switches per crossing opportunity.

    For each crossing event and each lock: the majority physical line in the ``window`` frames
    *before* the event vs the ``window`` frames *after* it. A switch is a changed (valid)
    majority — i.e., the lock came out of the crossing on a different physical line than it
    went in on. In-merge flicker inside the event does not count; an opportunity requires a
    valid majority on both sides (locks unassigned on either side are reported separately).

    Parameters
    ----------
    physical_assignment
        ``(T, L)`` int — output of :func:`physical_line_index` (``-1`` = unassigned).
    events
        Inclusive ``(first, last)`` spans from :func:`crossing_events`.
    window
        Frames per pre/post window (clipped at sequence bounds; an event with an empty pre or
        post window is not an opportunity).

    Returns
    -------
    dict
        ``{"switches", "opportunities", "rate", "undefined"}`` — ``rate`` = switches per
        opportunity (``nan`` if no opportunities); ``undefined`` counts (event, lock) pairs
        without valid majorities on both sides.
    """
    pa = np.asarray(physical_assignment)
    T, L = pa.shape
    switches = opportunities = undefined = 0
    for first, last in events:
        pre_lo, pre_hi = max(0, first - window), first
        post_lo, post_hi = last + 1, min(T, last + 1 + window)
        if pre_hi <= pre_lo or post_hi <= post_lo:
            continue  # event touches a sequence edge — no defined opportunity
        for lock in range(L):
            pre = _window_majority(pa[pre_lo:pre_hi, lock])
            post = _window_majority(pa[post_lo:post_hi, lock])
            if pre < 0 or post < 0:
                undefined += 1
                continue
            opportunities += 1
            if pre != post:
                switches += 1
    return {
        "switches": float(switches),
        "opportunities": float(opportunities),
        "rate": float(switches) / float(opportunities) if opportunities else float("nan"),
        "undefined": float(undefined),
    }


def wilson_ci(successes: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% default). ``(nan, nan)`` if n=0."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1.0 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = (z / denom) * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (float(center - half), float(center + half))


# --- recovery + dynamic range -----------------------------------------------------------

def _nonfinite_as_lost(err: np.ndarray) -> np.ndarray:
    """Treat undefined or infinite error as loss of lock."""
    return np.where(np.isfinite(err), err, np.inf)


def recovery_time(
    error: np.ndarray,
    dt_s: float,
    threshold: float,
    onset_index: int | None = None,
    hold: int = 1,
) -> float:
    """Time (s) from a disturbance until ``error`` returns below ``threshold`` and stays.

    Parameters
    ----------
    error
        ``(T,)`` per-frame error signal (e.g. angular error in degrees).
        Non-finite values count as lost.
    dt_s
        Frame interval (s).
    threshold
        Lock-recovered threshold (same units as ``error``).
    onset_index
        Frame the disturbance begins. ``None`` → the first frame where ``error`` exceeds
        ``threshold``. If ``error`` never exceeds the threshold, returns ``0.0`` (never lost).
    hold
        Number of consecutive below-threshold frames required to count as recovered.

    Returns
    -------
    float
        Recovery time in seconds, or ``inf`` if never recovered.
    """
    err = _nonfinite_as_lost(np.asarray(error, dtype=np.float64))
    T = err.shape[0]
    over = err > threshold
    if onset_index is None:
        if not over.any():
            return 0.0
        onset_index = int(np.argmax(over))

    for t in range(onset_index, T):
        if np.all(~over[t : t + hold]) and (t + hold) <= T:
            return float((t - onset_index) * dt_s)
    return INF


def dynamic_range(
    B_true: np.ndarray,
    error: np.ndarray,
    threshold: float,
    recovery_window: int | None = None,
) -> dict[str, float]:
    """Max |B| (Tesla) the tracker holds before *irrecoverable* loss of lock.

    A loss of lock is ``error[t] > threshold`` or a non-finite error. It is *irrecoverable* if
    the error stays above threshold for the next ``recovery_window`` frames (``None`` → to the
    end of the sequence).
    The dynamic range is the largest |B_true| over all frames strictly before the first
    irrecoverable loss.

    Report this **relative to the bias**, never as an absolute record (honest-ceiling guardrail
    from the design dossier).

    Parameters
    ----------
    B_true
        ``(T, 3)`` true field (Tesla).
    error
        ``(T,)`` per-frame error (e.g. angular error in degrees).
    threshold
        Loss-of-lock threshold (same units as ``error``).
    recovery_window
        Frames the error must stay above threshold to deem the loss irrecoverable.

    Returns
    -------
    dict
        ``{"dynamic_range_T", "loss_index", "never_lost"}``. ``loss_index`` is ``-1`` and
        ``never_lost`` is 1.0 when the tracker never irrecoverably loses lock (the returned
        range is then the max |B| over the whole sequence — a lower bound).
    """
    B_true = np.asarray(B_true, dtype=np.float64)
    err = _nonfinite_as_lost(np.asarray(error, dtype=np.float64))
    T = B_true.shape[0]
    mag = np.linalg.norm(B_true, axis=1)
    over = err > threshold

    loss_index = -1
    for t in range(T):
        if not over[t]:
            continue
        end = T if recovery_window is None else min(T, t + recovery_window)
        if np.all(over[t:end]):
            loss_index = t
            break

    if loss_index <= 0:
        # Never lost (or lost at the very first frame → no held range).
        return {
            "dynamic_range_T": float(mag.max()) if loss_index < 0 else 0.0,
            "loss_index": float(loss_index),
            "never_lost": 1.0 if loss_index < 0 else 0.0,
        }
    return {
        "dynamic_range_T": float(mag[:loss_index].max()),
        "loss_index": float(loss_index),
        "never_lost": 0.0,
    }
