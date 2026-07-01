"""Counterfactual check: textbook CV-Kalman + gating + coast-through-merge classical tracker
on sequence_sanity_v0 test split. Uses the repo's OWN peak detector and metrics.
Read-only on the repo; nothing written there.
"""
import sys
import numpy as np

sys.path.insert(0, "~/projects/odmr-vector-tracking/src")
sys.path.insert(0, "~/projects/odmr-vector-tracking")

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.tracking.classical import ClassicalTracker
from odmr_vector_tracking.vector.blue import blue_invert_field
from odmr_vector_tracking.evaluation.metrics import (
    association_accuracy, id_switch_rate, physical_line_index,
    resolve_true_axis, vector_angular_error, dynamic_range,
)

LOSS_DEG = 5.0


class CVKalmanTracker:
    """Per-line constant-velocity KF + gate + one-to-one assignment + coast-through-merge.

    Standard MTT baseline: state [f, v] per line; predict; gate measurements; one-to-one
    smallest-distance-first assignment (greedy GNN ~ Hungarian at these margins); tracks whose
    predicted positions are mutually unresolvable (< resolve_dist) are treated as occluded and
    COAST (no update) -- the textbook coast-through-occlusion rule.
    """

    def __init__(self, frequencies, linewidth_Hz, q_pos=None, q_vel=None, r_meas=None,
                 gate_Hz=None, resolve_bins=3):
        self.peakdet = ClassicalTracker(frequencies, linewidth_Hz=linewidth_Hz)
        self.df = self.peakdet.df
        G = linewidth_Hz
        self.gate = gate_Hz if gate_Hz is not None else 4.0 * G
        self.resolve_dist = resolve_bins * self.df  # NMS resolution of the shared peak detector
        # Noise tuning: generous defaults, not per-sequence tuned.
        self.q_pos = q_pos if q_pos is not None else (0.02 * G) ** 2
        self.q_vel = q_vel if q_vel is not None else (0.05 * G) ** 2
        self.r = r_meas if r_meas is not None else (0.1 * G) ** 2

    def run(self, spectra, init_freqs):
        T = spectra.shape[0]
        L = len(init_freqs)
        x = np.zeros((L, 2))
        x[:, 0] = init_freqs
        P = np.tile(np.diag([self.r, (0.5e6) ** 2]), (L, 1, 1))
        F = np.array([[1.0, 1.0], [0.0, 1.0]])   # dt = 1 frame
        Q = np.diag([self.q_pos, self.q_vel])
        H = np.array([[1.0, 0.0]])
        tracked = np.zeros((T, L))
        for t in range(T):
            # predict
            for i in range(L):
                x[i] = F @ x[i]
                P[i] = F @ P[i] @ F.T + Q
            peaks = self.peakdet._find_peaks(spectra[t])
            # occlusion: tracks predicted within the detector's resolution are unresolvable
            occluded = np.zeros(L, bool)
            for i in range(L):
                for j in range(i + 1, L):
                    if abs(x[i, 0] - x[j, 0]) < self.resolve_dist:
                        occluded[i] = occluded[j] = True
            # one-to-one gated assignment for non-occluded tracks
            if peaks.size:
                dist = np.abs(x[:, 0][:, None] - peaks[None, :])
                dist[dist > self.gate] = np.inf
                dist[occluded, :] = np.inf  # coast through the merge
                while np.isfinite(dist).any():
                    k = int(np.argmin(dist))
                    i, j = divmod(k, peaks.shape[0])
                    z = peaks[j]
                    # KF update for track i
                    S = (H @ P[i] @ H.T).item() + self.r
                    K = (P[i] @ H.T / S).ravel()
                    innov = z - x[i, 0]
                    x[i] = x[i] + K * innov
                    P[i] = (np.eye(2) - np.outer(K, H)) @ P[i]
                    dist[i, :] = np.inf
                    dist[:, j] = np.inf
            tracked[t] = x[:, 0]
        return tracked


def main():
    ld = SequenceDatasetLoader("~/projects/odmr-vector-tracking/data/sequence_sanity_v0")
    m = ld.manifest
    ds = ld.load_split("test")
    G, dt = m["linewidth_Hz"], m["dt_s"]
    rows = []
    for n in range(ds.n_sequences):
        trk = CVKalmanTracker(ds.frequencies, G)
        tracked = trk.run(ds.spectra[n].astype(np.float64), ds.resonance_freqs[n, 0].astype(np.float64))
        pred_axis = np.broadcast_to(np.array([0, 0, 1, 1, 2, 2, 3, 3], np.int8), tracked.shape)
        ta = resolve_true_axis(tracked, ds.resonance_freqs[n], ds.line_axis[n])
        B_est = np.stack([blue_invert_field(tracked[t]).b_hat for t in range(tracked.shape[0])])
        ae = np.nan_to_num(vector_angular_error(ds.B_true[n], B_est), nan=0.0)
        cf = np.where(ds.collision_mask[n])[0]
        first, last = int(cf.min()), int(cf.max())
        acc = association_accuracy(pred_axis, ta, line_collision=ds.line_collision[n])
        dr = dynamic_range(ds.B_true[n], ae, threshold=LOSS_DEG)
        rows.append(dict(
            pre=association_accuracy(pred_axis[:first], ta[:first])["overall"],
            post=association_accuracy(pred_axis[last + 1:], ta[last + 1:])["overall"],
            in_coll=acc["in_collision"],
            idsw=id_switch_rate(physical_line_index(tracked, ds.resonance_freqs[n]))["count"],
            lost=dr["never_lost"] == 0.0,
            drT=dr["dynamic_range_T"],
            ae_peak=float(ae.max()), ae_post=float(ae[last + 1:].mean()),
        ))
    med = lambda k: float(np.median([r[k] for r in rows]))
    lost = sum(r["lost"] for r in rows)
    print(f"CV-KF + gate + coast-through-merge on {len(rows)} test seqs:")
    print(f"  assoc pre {med('pre'):.3f} -> post {med('post'):.3f} (median)   in-coll {med('in_coll'):.3f}")
    print(f"  ID-switch count/seq median {med('idsw'):.0f}")
    print(f"  LOSES LOCK {lost}/{len(rows)}   DR median {med('drT')*1e3:.2f} mT")
    print(f"  ang err peak {med('ae_peak'):.1f} deg, post {med('ae_post'):.2f} deg (median)")
    print("  per-seq post acc:", [round(r['post'], 3) for r in rows])


if __name__ == "__main__":
    main()
