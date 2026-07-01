"""Reviewer stress test: textbook CV-Kalman + Hungarian (GNN) tracker on the team's own
Increment-1 dataset and metrics. NOT part of the repo — evidence for a skeptical review.

State per line: [f, fdot]. Predict-coast when unassigned (merged peaks at crossings).
Global nearest neighbor via scipy linear_sum_assignment with gating.
Everything else (peak detector, metrics, BLUE inversion) reuses the repo's own code
so the comparison is apples-to-apples with experiments/increment1_report.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

REPO = Path.home() / "projects/odmr-vector-tracking"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.data.contract import validate_dataset_dir
from odmr_vector_tracking.evaluation.metrics import (
    association_accuracy,
    dynamic_range,
    id_switch_rate,
    physical_line_index,
    recovery_time,
    resolve_true_axis,
    vector_angular_error,
)
from odmr_vector_tracking.tracking.classical import ClassicalTracker
from odmr_vector_tracking.vector.blue import blue_invert_field

LOSS_DEG = 5.0


class KFHungarianTracker:
    """Per-line constant-velocity Kalman + global Hungarian assignment (textbook GNN)."""

    def __init__(self, frequencies, linewidth_Hz, q_accel_frac=0.05, gate_lw=8.0):
        self.freqs = np.asarray(frequencies, float)
        self.lw = float(linewidth_Hz)
        # peak detector: reuse the repo's own, for fairness
        self._peaks = ClassicalTracker(frequencies, linewidth_Hz=linewidth_Hz)._find_peaks
        # CV model per frame
        self.F = np.array([[1.0, 1.0], [0.0, 1.0]])
        # process noise: random-accel; sigma_a as fraction of linewidth per frame^2
        sa = q_accel_frac * self.lw
        self.Q = sa**2 * np.array([[0.25, 0.5], [0.5, 1.0]])
        # measurement noise: sub-bin refined peak center; conservative = linewidth/5
        self.R = (self.lw / 5.0) ** 2
        self.gate = gate_lw * self.lw
        self.H = np.array([[1.0, 0.0]])

    def run(self, spectra, init_freqs):
        spectra = np.asarray(spectra, float)
        T = spectra.shape[0]
        L = len(init_freqs)
        x = np.zeros((L, 2))
        x[:, 0] = init_freqs
        P = np.tile(np.diag([self.R, (0.5 * self.lw) ** 2]), (L, 1, 1))
        tracked = np.empty((T, L))
        locked = np.zeros((T, L), bool)
        for t in range(T):
            # predict
            for i in range(L):
                x[i] = self.F @ x[i]
                P[i] = self.F @ P[i] @ self.F.T + self.Q
            peaks = self._peaks(spectra[t])
            M = len(peaks)
            if M:
                # gated cost matrix on innovation
                cost = np.abs(x[:, 0][:, None] - peaks[None, :])
                BIG = 1e18
                cost_g = np.where(cost <= self.gate, cost, BIG)
                # pad to square so unassigned tracks coast
                n = max(L, M)
                sq = np.full((n, n), BIG * 10)
                sq[:L, :M] = cost_g
                ri, ci = linear_sum_assignment(sq)
                for i, j in zip(ri, ci):
                    if i < L and j < M and sq[i, j] < BIG:
                        # KF update
                        z = peaks[j]
                        S = P[i][0, 0] + self.R
                        K = P[i] @ self.H.T / S  # (2,1)
                        innov = z - x[i][0]
                        x[i] = x[i] + (K[:, 0] * innov)
                        P[i] = (np.eye(2) - K @ self.H) @ P[i]
                        locked[t, i] = True
            tracked[t] = x[:, 0]
        B_est = np.empty((T, 3))
        for t in range(T):
            B_est[t] = blue_invert_field(tracked[t]).b_hat
        return tracked.astype(np.float32), locked, B_est.astype(np.float32)


def analyze(dataset_dir, split, label, tracker_factory):
    m = validate_dataset_dir(dataset_dir)
    ld = SequenceDatasetLoader(dataset_dir)
    ds = ld.load_split(split)
    gamma, dt = m["linewidth_Hz"], m["dt_s"]
    rows = []
    for n in range(ds.spectra.shape[0]):
        trk = tracker_factory(ds.frequencies, gamma)
        tracked, locked, B_est = trk(ds.spectra[n], ds.resonance_freqs[n, 0])
        # identity bookkeeping identical to increment1_report
        from odmr_vector_tracking.tracking.classical import LINE_AXIS_8

        pred_axis = np.broadcast_to(LINE_AXIS_8, tracked.shape).astype(np.int8)
        ta = resolve_true_axis(tracked, ds.resonance_freqs[n], ds.line_axis[n])
        ae = np.nan_to_num(vector_angular_error(ds.B_true[n], B_est), nan=0.0)
        cf = np.where(ds.collision_mask[n])[0]
        if cf.size == 0:
            continue
        first, last = int(cf.min()), int(cf.max())
        acc = association_accuracy(pred_axis, ta, line_collision=ds.line_collision[n])
        lc = ds.line_collision[n].astype(bool)
        dr = dynamic_range(ds.B_true[n], ae, threshold=LOSS_DEG)
        rows.append(dict(
            pre=association_accuracy(pred_axis[:first], ta[:first])["overall"],
            post=association_accuracy(pred_axis[last + 1:], ta[last + 1:])["overall"],
            in_coll=acc["in_collision"], out_coll=acc["out_collision"],
            dr=dr["dynamic_range_T"], lost=dr["never_lost"] == 0.0,
            rt=recovery_time(ae, dt_s=dt, threshold=LOSS_DEG, onset_index=first),
            idsw=id_switch_rate(physical_line_index(tracked, ds.resonance_freqs[n]))["count"],
            ae_pre=float(ae[:first].mean()), ae_peak=float(ae.max()),
            ae_post=float(ae[last + 1:].mean()),
            incoll_err=float((pred_axis != ta)[lc].mean()) if lc.any() else float("nan"),
        ))
    N = len(rows)
    lost = sum(r["lost"] for r in rows)
    nr = sum(1 for r in rows if r["rt"] == float("inf"))
    med = lambda k: float(np.median([r[k] for r in rows]))
    print(f"\n===== {label} (split='{split}', {N} seq) =====")
    print(f"  assoc accuracy    : pre {med('pre'):.3f} -> post {med('post'):.3f} (median)")
    print(f"  in-collision assoc: {med('in_coll'):.3f} (out {med('out_coll'):.3f})")
    print(f"  ID-switches/seq   : {med('idsw'):.0f} (median) | in-collision ID-switch err {med('incoll_err'):.3f}")
    print(f"  LOSES LOCK (>5deg irrecoverable): {lost}/{N}")
    print(f"  dynamic range     : median {med('dr')*1e3:.2f} mT")
    print(f"  vector ang err    : pre {med('ae_pre'):.2f} -> peak {med('ae_peak'):.1f} -> post {med('ae_post'):.1f} deg")
    print(f"  never recovers    : {nr}/{N}")


def main():
    real = str(REPO / "data" / "sequence_sanity_v0")

    def kf_factory(freqs, gamma):
        t = KFHungarianTracker(freqs, gamma)
        return lambda spectra, init: t.run(spectra, init)

    analyze(real, "test", "CV-KALMAN + HUNGARIAN (textbook GNN, ~60 lines)", kf_factory)

    # also rerun their baseline through the same harness as sanity check
    def their_factory(freqs, gamma):
        t = ClassicalTracker(freqs, linewidth_Hz=gamma)

        def run(spectra, init):
            r = t.run(spectra, init_freqs=init)
            return r.tracked_freqs, r.locked, r.B_est

        return run

    analyze(real, "test", "REPO BASELINE via same harness (sanity)", their_factory)


if __name__ == "__main__":
    main()
