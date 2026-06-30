"""Increment-1 headline report: classical baseline on real nv-sensor-sim data + fixture cross-check.

Reproduces the Increment-1 result — the Γ/2-limited classical baseline loses per-axis lock at
inter-axis crossings — and cross-checks that the synthetic fixtures fail by the same mechanism.

Run from the repo root:  ``python experiments/increment1_report.py``

The real dataset is a gitignored local artifact; symlink it where the loader expects:
    ln -sfn <nv-sensor-sim>/artifacts/datasets/sequence_sanity_v0 data/sequence_sanity_v0
or set ODMR_VT_REAL_DATASET to its directory. If neither is present, only the fixture (always
generatable) is reported.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))  # for tests.fixtures

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

LOSS_DEG = 5.0  # vector lock deemed "lost" above this angular error


def analyze(dataset_dir: str, split: str, label: str) -> None:
    m = validate_dataset_dir(dataset_dir)
    ld = SequenceDatasetLoader(dataset_dir)
    ds = ld.load_split(split)
    gamma, dt = m["linewidth_Hz"], m["dt_s"]
    bias_mag = float(np.linalg.norm(ld.bias))
    trk = ClassicalTracker(ds.frequencies, linewidth_Hz=gamma)

    rows = []
    for n in range(ds.spectra.shape[0]):
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        ta = resolve_true_axis(res.tracked_freqs, ds.resonance_freqs[n], ds.line_axis[n])
        ae = np.nan_to_num(vector_angular_error(ds.B_true[n], res.B_est), nan=0.0)
        cf = np.where(ds.collision_mask[n])[0]
        if cf.size == 0:
            continue
        first, last = int(cf.min()), int(cf.max())
        acc = association_accuracy(res.pred_axis, ta, line_collision=ds.line_collision[n])
        lc = ds.line_collision[n].astype(bool)
        rows.append(dict(
            bmin=float(np.linalg.norm(ds.B_true[n], axis=1).min()),
            bmax=float(np.linalg.norm(ds.B_true[n], axis=1).max()),
            pre=association_accuracy(res.pred_axis[:first], ta[:first])["overall"],
            post=association_accuracy(res.pred_axis[last + 1:], ta[last + 1:])["overall"],
            in_coll=acc["in_collision"], out_coll=acc["out_collision"],
            dr=dynamic_range(ds.B_true[n], ae, threshold=LOSS_DEG)["dynamic_range_T"],
            lost=dynamic_range(ds.B_true[n], ae, threshold=LOSS_DEG)["never_lost"] == 0.0,
            rt=recovery_time(ae, dt_s=dt, threshold=LOSS_DEG, onset_index=first),
            idsw=id_switch_rate(physical_line_index(res.tracked_freqs, ds.resonance_freqs[n]))["count"],
            ae_pre=float(ae[:first].mean()), ae_peak=float(ae.max()),
            ae_post=float(ae[last + 1:].mean()),
            incoll_err=float((res.pred_axis != ta)[lc].mean()) if lc.any() else float("nan"),
        ))

    N = len(rows)
    lost = sum(r["lost"] for r in rows)
    never_recover = sum(1 for r in rows if r["rt"] == float("inf"))
    med = lambda k: float(np.median([r[k] for r in rows]))
    print(f"\n===== {label}  (split='{split}', {N} sequences w/ crossing) =====")
    print(f"  scenario          : bias |B| = {bias_mag*1e3:.2f} mT, Gamma = {gamma/1e6:.2f} MHz, "
          f"k = {m['collision_threshold_linewidths']}, T = {m['n_timesteps']}, F = {m['n_freq_points']}")
    print(f"  |B| range         : {med('bmin')*1e3:.2f}..{med('bmax')*1e3:.2f} mT (median)")
    print(f"  assoc accuracy    : pre {med('pre'):.3f} -> post {med('post'):.3f} (median)")
    print(f"  in-collision assoc: {med('in_coll'):.3f}   (out-of-collision {med('out_coll'):.3f})")
    print(f"  ID-switches/seq   : {med('idsw'):.0f} (median) | in-collision ID-switch err {med('incoll_err'):.3f}")
    print(f"  LOSES LOCK        : {lost}/{N} ({100*lost//N if N else 0}%)")
    print(f"  dynamic range     : median {med('dr')*1e3:.2f} mT before irrecoverable loss (at {bias_mag*1e3:.1f} mT bias)")
    print(f"  vector ang err    : pre {med('ae_pre'):.2f} -> peak {med('ae_peak'):.1f} -> post {med('ae_post'):.1f} deg (median)")
    print(f"  recovery time     : never recovers in {never_recover}/{N}")


def main() -> int:
    real = os.environ.get("ODMR_VT_REAL_DATASET") or str(_REPO_ROOT / "data" / "sequence_sanity_v0")
    if (Path(real) / "manifest.json").exists():
        analyze(real, "test", f"REAL nv-sensor-sim data ({Path(real).name})")
    else:
        print(f"[skip real data] not found at {real} "
              f"(symlink it or set ODMR_VT_REAL_DATASET)")

    from tests.fixtures.synthetic import write_synthetic_h5
    tmp = tempfile.mkdtemp()
    write_synthetic_h5(tmp, {"train": 4, "val": 2, "test": 4})
    analyze(tmp, "test", "SYNTHETIC FIXTURE (cross-check)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
