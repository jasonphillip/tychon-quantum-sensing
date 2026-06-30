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


# --- association ground-truth helpers ---------------------------------------------------

def physical_line_index(tracked_freqs: np.ndarray, resonance_freqs: np.ndarray) -> np.ndarray:
    """Nearest ground-truth line index for each lock at each frame.

    ``tracked_freqs`` ``(T, L)`` (lock centers) → for each (t, lock) the index of the closest
    ground-truth resonance in ``resonance_freqs`` ``(T, Lgt)``. This is the *physical* line the
    lock is actually sitting on, regardless of the identity it claims.
    """
    tracked = np.asarray(tracked_freqs, dtype=np.float64)
    gt = np.asarray(resonance_freqs, dtype=np.float64)
    # (T, L, Lgt) distances → argmin over gt.
    d = np.abs(tracked[:, :, None] - gt[:, None, :])
    return np.argmin(d, axis=2)


def resolve_true_axis(
    tracked_freqs: np.ndarray, resonance_freqs: np.ndarray, line_axis: np.ndarray
) -> np.ndarray:
    """Ground-truth NV axis each lock is *physically* on, ``(T, L)``.

    Combines :func:`physical_line_index` with the per-frame ``line_axis`` labels ``(T, Lgt)``.
    Compare against the tracker's claimed ``pred_axis`` to score association.
    """
    phys = physical_line_index(tracked_freqs, resonance_freqs)  # (T, L)
    line_axis = np.asarray(line_axis)
    return np.take_along_axis(line_axis, phys, axis=1)


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
    """Identity-switch statistics from per-frame physical-line assignments.

    An ID switch is a lock changing which physical line it sits on between consecutive frames
    (the MOT ``IDSW`` analogue). A perfect tracker keeps each lock on one line → zero switches;
    a crossing swap registers a switch.

    Parameters
    ----------
    physical_assignment
        ``(T, L)`` int — output of :func:`physical_line_index`.

    Returns
    -------
    dict
        ``{"count", "rate"}`` — total switches and switches per (lock, frame-transition).
    """
    pa = np.asarray(physical_assignment)
    T, L = pa.shape
    if T < 2:
        return {"count": 0.0, "rate": 0.0}
    switches = int((pa[1:] != pa[:-1]).sum())
    return {"count": float(switches), "rate": float(switches) / float(L * (T - 1))}


# --- recovery + dynamic range -----------------------------------------------------------

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
    err = np.asarray(error, dtype=np.float64)
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

    A loss of lock is ``error[t] > threshold``. It is *irrecoverable* if the error stays above
    threshold for the next ``recovery_window`` frames (``None`` → to the end of the sequence).
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
    err = np.asarray(error, dtype=np.float64)
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
