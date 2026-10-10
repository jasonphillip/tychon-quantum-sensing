"""Shared per-sequence metric rows — ONE scoring path for every tracker.

Every evaluated tracker (honest PID, CV-KF, oracle, learned variants) reduces to the same
three arrays per sequence — claimed line centers ``tracked_hz (T, L)``, claimed identities
``pred_axis (T, L)``, and a vector estimate ``B_est (T, 3)`` — and is scored by
:func:`sequence_metrics_row` with identical conventions. This is what makes cross-tracker
tables apples-to-apples (and what the format-parity unit test pins).

Conventions (2026-07-01 re-baseline):
- **nan-aware angular error**: frames where the angle is undefined (near-zero estimate) count
  as *lost* for lock/recovery purposes and are excluded from means — they are never graded as
  perfect (the retracted pipeline's ``nan_to_num(..., 0.0)`` flattered cold starts).
- **capture radius**: a lock farther than ``capture_radius_hz`` from every true line is
  unassigned → misassociated, and excluded from raw switch counting (fragmentation, not a
  switch).
- **per-opportunity ID switches**: identity compared across each crossing event with
  pre/post windows — the discriminative through-crossing statistic; the raw frame-to-frame
  count is retained as a diagnostic only (it saturates with benign in-merge flicker).
- **no dynamic range**: DR is unmeasurable on v0/v1 (|B| spans ~4.7–5.8 mT; a never-losing
  tracker saturates at the dataset bound). DR claims wait for a dedicated amplitude-ladder
  lineage.
"""

from __future__ import annotations

import numpy as np

from odmr_vector_tracking.evaluation.metrics import (
    _nonfinite_as_lost,
    association_accuracy,
    crossing_events,
    full_vector_lock,
    full_vector_lock_stats,
    id_switch_rate,
    id_switches_per_opportunity,
    physical_line_index,
    magnitude_error,
    recovery_time,
    resolve_true_axis,
    vector_angular_error,
    vector_bias,
    vector_rmse,
)

LOSS_DEG = 5.0  # vector lock deemed "lost" above this angular error


def fieldcone_metrics_row(
    B_true: np.ndarray,
    B_est: np.ndarray,
    *,
    dt_s: float,
    mag_tol_frac: float = 0.05,
    angle_tol_deg: float = 5.0,
) -> dict:
    """Score one field-cone sequence in Tesla and degrees.

    ``dt_s`` is the dataset frame interval; indices and frame counts stay in frames.
    Undefined angular errors are excluded from means and count as unlocked.
    """
    ae = vector_angular_error(B_true, B_est)
    mag_err = magnitude_error(B_true, B_est)
    bias = vector_bias(B_true, B_est)
    lock = full_vector_lock(B_true, B_est, mag_tol_frac, angle_tol_deg)
    finite_ae = ae[np.isfinite(ae)]
    finite_mag = mag_err[np.isfinite(mag_err)]
    return {
        "rmse_T": vector_rmse(B_true, B_est),
        "mag_err_mean_T": float(finite_mag.mean()) if finite_mag.size else float("nan"),
        "mag_err_p90_T": float(np.percentile(np.abs(finite_mag), 90)) if finite_mag.size else float("nan"),
        "bias_x_T": float(bias[0]),
        "bias_y_T": float(bias[1]),
        "bias_z_T": float(bias[2]),
        "ae_mean_deg": float(finite_ae.mean()) if finite_ae.size else float("nan"),
        "ae_p90_deg": float(np.percentile(finite_ae, 90)) if finite_ae.size else float("nan"),
        **full_vector_lock_stats(lock),
        "n_frames": int(np.asarray(B_true).shape[0]),
    }


def sequence_metrics_row(
    tracked_hz: np.ndarray,
    pred_axis: np.ndarray,
    B_est: np.ndarray,
    *,
    resonance_freqs: np.ndarray,
    line_axis: np.ndarray,
    line_collision: np.ndarray,
    collision_mask: np.ndarray,
    B_true: np.ndarray,
    dt_s: float,
    capture_radius_hz: float,
    loss_deg: float = LOSS_DEG,
    idsw_window: int = 5,
) -> dict | None:
    """Score one sequence; ``None`` if it contains no crossing event.

    All tracker outputs must already be in Hz / lab-frame Tesla (denormalization is the
    caller's job — asserted equivalent across output formats by the parity unit test).
    """
    events = crossing_events(collision_mask)
    if not events:
        return None
    first, last = events[0][0], events[-1][1]

    ta = resolve_true_axis(tracked_hz, resonance_freqs, line_axis, capture_radius_hz)
    phys = physical_line_index(tracked_hz, resonance_freqs, capture_radius_hz)

    ae = vector_angular_error(B_true, B_est)          # nan where undefined
    ae_lock = _nonfinite_as_lost(ae)                   # undefined counts as LOST

    acc = association_accuracy(pred_axis, ta, line_collision=line_collision)
    lc = np.asarray(line_collision, dtype=bool)
    raw_sw = id_switch_rate(phys)
    opp = id_switches_per_opportunity(phys, events, window=idsw_window)

    over = ae_lock > loss_deg
    lost = False
    loss_index = -1
    for t in range(len(over)):
        if over[t] and bool(np.all(over[t:])):
            lost, loss_index = True, t
            break

    def _nanmean(x: np.ndarray) -> float:
        return float(np.nanmean(x)) if np.isfinite(x).any() else float("nan")

    return dict(
        n_events=len(events),
        pre=association_accuracy(pred_axis[:first], ta[:first])["overall"] if first > 0
        else float("nan"),
        post=association_accuracy(pred_axis[last + 1:], ta[last + 1:])["overall"]
        if last + 1 < tracked_hz.shape[0] else float("nan"),
        in_coll=acc["in_collision"],
        out_coll=acc["out_collision"],
        misassoc_in_coll=float((pred_axis != ta)[lc].mean()) if lc.any() else float("nan"),
        # pooled counts for binomial CIs across sequences
        in_coll_n=int(lc.sum()),
        in_coll_wrong=int((pred_axis != ta)[lc].sum()) if lc.any() else 0,
        idsw_raw=raw_sw["count"],
        unassigned_frac=raw_sw["unassigned_frac"],
        idsw_opp_switches=opp["switches"],
        idsw_opp_n=opp["opportunities"],
        idsw_opp_rate=opp["rate"],
        lost=lost,
        loss_index=loss_index,
        rt=recovery_time(ae_lock, dt_s=dt_s, threshold=loss_deg, onset_index=first),
        ae_pre=_nanmean(ae[:first]),
        ae_peak=float(np.nanmax(ae)) if np.isfinite(ae).any() else float("nan"),
        ae_post=_nanmean(ae[last + 1:]),
        ae_undefined_frac=float(np.isnan(ae).mean()),
    )


def summarize_rows(rows: list[dict], label: str, caption: str = "") -> None:
    """Print the standard metric block over per-sequence rows (median aggregation).

    No dynamic-range line by design — see the module docstring.
    """
    N = len(rows)
    if N == 0:
        print(f"\n===== {label} ===== (no sequences with crossings)")
        return
    lost = sum(r["lost"] for r in rows)
    never_recover = sum(1 for r in rows if r["rt"] == float("inf"))
    sw = sum(r["idsw_opp_switches"] for r in rows)
    op = sum(r["idsw_opp_n"] for r in rows)
    med = lambda k: float(np.nanmedian([r[k] for r in rows]))  # noqa: E731
    print(f"\n===== {label}  ({N} sequences w/ crossing) =====")
    if caption:
        print(f"  [{caption}]")
    print(f"  assoc accuracy    : pre {med('pre'):.3f} -> post {med('post'):.3f} (median)")
    print(f"  in-collision assoc: {med('in_coll'):.3f}   (out-of-collision {med('out_coll'):.3f})")
    print(f"  in-coll misassoc  : {med('misassoc_in_coll'):.3f} (median fraction)")
    print(f"  ID-sw/opportunity : {sw:.0f}/{op:.0f} pooled = {sw/op if op else float('nan'):.3f} "
          f"| raw frame-to-frame {med('idsw_raw'):.0f}/seq (diagnostic; flicker-saturating)")
    print(f"  LOSES LOCK        : {lost}/{N} ({100*lost//N if N else 0}%)  "
          f"[>|{LOSS_DEG:.0f}deg| irrecoverable; undefined error counts as lost]")
    print(f"  vector ang err    : pre {med('ae_pre'):.2f} -> peak {med('ae_peak'):.1f} "
          f"-> post {med('ae_post'):.1f} deg (median, nan-aware)")
    print(f"  recovery time     : never recovers in {never_recover}/{N}")
    print("  (dynamic range omitted: unmeasurable on this lineage — |B| span saturates; "
          "DR waits for an amplitude-ladder dataset)")
