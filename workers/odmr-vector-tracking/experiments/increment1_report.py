"""Increment-1 report (CORRECTED): honest classical baseline on real data + fixture cross-check.

RETRACTION (2026-07-01): the originally published Increment-1 numbers (16/16 loss, association
1.0→0.0, "ID-switch 0.811", 43° peak error, DR ≈ 5 mT) are an instrument artifact and are
retracted. The detector's default absolute threshold (``peak_min_depth=0.03``) exceeds the
real data's ~0.4% dip depth, so ``_find_peaks`` returned zero peaks on every real frame and
the tracker never left its ground-truth initialization — those numbers scored a frozen
tracker against moving lines (fingerprint: in-collision accuracy == out-of-collision
accuracy). This report uses a data-scaled threshold (:func:`auto_peak_min_depth`), asserts
the tracker is actually locked pre-crossing, and scores with the shared nan-aware
conventions of :mod:`odmr_vector_tracking.evaluation.rows`.

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
from odmr_vector_tracking.evaluation.rows import sequence_metrics_row, summarize_rows
from odmr_vector_tracking.tracking.classical import ClassicalTracker, auto_peak_min_depth

CAPTURE_RADIUS_LW = 3.0


def analyze(dataset_dir: str, split: str, label: str) -> None:
    m = validate_dataset_dir(dataset_dir)
    ld = SequenceDatasetLoader(dataset_dir)
    ds = ld.load_split(split)
    gamma, dt = m["linewidth_Hz"], m["dt_s"]
    bias_mag = float(np.linalg.norm(ld.bias))

    rows, locked_pre = [], []
    for n in range(ds.spectra.shape[0]):
        depth = auto_peak_min_depth(ds.spectra[n], line_depths=m.get("line_depths"))
        trk = ClassicalTracker(ds.frequencies, linewidth_Hz=gamma, peak_min_depth=depth)
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        cf = np.where(ds.collision_mask[n])[0]
        if cf.size and cf.min() > 0:
            locked_pre.append(float(res.locked[: cf.min()].mean()))
        r = sequence_metrics_row(
            res.tracked_freqs, res.pred_axis, res.B_est,
            resonance_freqs=ds.resonance_freqs[n],
            line_axis=ds.line_axis[n],
            line_collision=ds.line_collision[n],
            collision_mask=ds.collision_mask[n],
            B_true=ds.B_true[n],
            dt_s=dt,
            capture_radius_hz=CAPTURE_RADIUS_LW * gamma,
        )
        if r is not None:
            rows.append(r)

    mean_locked = float(np.mean(locked_pre)) if locked_pre else float("nan")
    print(f"\n[{label}] scenario: bias |B| = {bias_mag*1e3:.2f} mT, "
          f"Gamma = {gamma/1e6:.2f} MHz, k = {m['collision_threshold_linewidths']}, "
          f"T = {m['n_timesteps']}, F = {m['n_freq_points']}")
    print(f"[{label}] detector check: mean pre-crossing locked fraction = {mean_locked:.4f}")
    assert mean_locked > 0.9, (
        f"pre-crossing locked fraction {mean_locked:.3f} <= 0.9 — the detector is not seeing "
        f"the data's peaks (the retracted-bar failure mode); threshold scaling is broken"
    )
    summarize_rows(
        rows,
        f"HONEST classical lock-in+PID baseline — {label}",
        "GT t=0 initialization (well-resolved acquisition assumption); data-scaled detector",
    )


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
