"""Increment-6 tri-eval 3 — field-cone boundary: lock/acquisition vs (off-bias angle x |B|).

Scores the v6 (coverage-retrained) and v2 (deployed) checkpoints plus CV-KF over
`sequence_eval_fieldcone_v1` (120 held-out sequences on an (angle x |B|) ladder spanning and
EXCEEDING the v3 training envelope: bucket_class 0 = the exact (0,2)/(4,6) failure
geometries, 1 = in-envelope control, 2 = beyond-envelope probes at theta 66-70 deg /
|B| 2.0-2.5 mT), at the clean and snr30 rungs (fixed-seed noise, `noise_matrix_report`
conventions).

Most field-cone sequences have NO line crossings by design (this eval measures field
ACQUISITION and HOLD, not identity), so `sequence_metrics_row` does not apply. Field-lock
metrics are computed directly with the standing conventions from `evaluation/rows.py`:
nan angular error counts as lost; a sequence is `lost` iff from some frame onward the error
never returns below LOSS_DEG (irrecoverable). Cold-start acquisition is additionally
reported as the first frame with error <= LOSS_DEG (-1 = never acquires). Learned trackers
cold-acquire; CV-KF keeps its GT t=0 init (standing convention) and is a REFERENCE for
hold-under-geometry, not a cold-acquisition comparator.

Verdicts are NOT decided here — `increment6_verdict.py` (committed pre-hoc) reads the
artifact. Writes `artifacts/increment6/fieldcone_v6.json`.

    python experiments/increment6_fieldcone.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "experiments"))

import identity_redecode as ir  # noqa: E402
import noise_matrix_report as nmr  # noqa: E402
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.data.contract import validate_dataset_dir  # noqa: E402
from odmr_vector_tracking.evaluation.metrics import vector_angular_error  # noqa: E402
from odmr_vector_tracking.evaluation.rows import LOSS_DEG  # noqa: E402
from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker  # noqa: E402

FIELDCONE = _REPO_ROOT / "data" / "sequence_eval_fieldcone_v1"
V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
OUT = _REPO_ROOT / "artifacts" / "increment6" / "fieldcone_v6.json"
RUNGS = (("clean", None), ("snr30", 30.0))
GENS = {
    "v2": {"dir": _REPO_ROOT / "artifacts" / "increment2c", "seeds": ir.BASELINE_SEEDS},
    "v6": {"dir": _REPO_ROOT / "artifacts" / "increment6" / "runs",
           "seeds": ("v3_gated_linear_snr10", "v3_gated_linear_snr10_s20260711",
                     "v3_gated_linear_snr10_s20260721")},
}
BUCKET_NAMES = {0: "failure", 1: "control", 2: "beyond"}


def lock_stats(B_true: np.ndarray, b_est: np.ndarray) -> dict:
    """Standing lock conventions (rows.py): nan = lost; irrecoverable >LOSS_DEG = lost.

    Adds cold-start acquisition: first frame with error <= LOSS_DEG (-1 if never).
    """
    ae = vector_angular_error(B_true, b_est)
    ae_lock = np.where(np.isnan(ae), np.inf, ae)
    over = ae_lock > LOSS_DEG
    lost, loss_index = False, -1
    for t in range(len(over)):
        if over[t] and bool(np.all(over[t:])):
            lost, loss_index = True, t
            break
    under = np.flatnonzero(~over)
    acq_index = int(under[0]) if under.size else -1
    return {
        "lost": int(lost),
        "loss_index": int(loss_index),
        "acq_index": acq_index,
        "never_locked": int(under.size == 0),
        "ae_med": float(np.nanmedian(ae)) if np.isfinite(ae).any() else float("nan"),
    }


def main() -> int:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    m = validate_dataset_dir(FIELDCONE)
    faintest = float(np.min(np.asarray(m["line_depths"])))
    v1_depths = validate_dataset_dir(V1_DIR)["line_depths"]
    clean = SequenceDatasetLoader(FIELDCONE).load_split("test")
    with h5py.File(FIELDCONE / "dataset.h5", "r") as f:
        per_seq = {k: f[f"test/{k}"][:].tolist()
                   for k in ("bucket_class", "target_angle_deg", "target_B_mT",
                             "realized_max_offbias_angle_deg", "realized_min_B_T")}

    budgets = {tag: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for tag, snr in RUNGS}
    results: dict = {**per_seq, "noise_master_seed": nmr.NOISE_MASTER_SEED,
                     "budgets": budgets, "loss_deg": LOSS_DEG,
                     "gens": {g: list(v["seeds"]) for g, v in GENS.items()},
                     "cells": {}}
    t0 = time.time()
    for tag, photons in budgets.items():
        ds = nmr.noisy_copy(clean, photons)
        cells = results["cells"].setdefault(tag, {})
        for gen, spec in GENS.items():
            for seed in spec["seeds"]:
                seqs, _ = ir.run_ckpt_outputs(spec["dir"] / seed / "best.pt", ds, device)
                stats = [lock_stats(ds.B_true[n], s["b_est"]) for n, s in enumerate(seqs)]
                cells[seed] = {k + "_all": [s[k] for s in stats]
                               for k in ("lost", "loss_index", "acq_index", "never_locked",
                                         "ae_med")}
                print(f"[{tag}] {gen}/{seed} done ({time.time() - t0:.0f}s)", flush=True)
        kf_stats = []
        for n in range(ds.spectra.shape[0]):
            trk = KFHungarianTracker(ds.frequencies, linewidth_Hz=m["linewidth_Hz"],
                                     peak_min_depth=nmr.detector_depth(
                                         ds.spectra[n], {**m, "line_depths": v1_depths},
                                         photons))
            res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
            kf_stats.append(lock_stats(ds.B_true[n], res.B_est))
        cells["kf"] = {k + "_all": [s[k] for s in kf_stats]
                       for k in ("lost", "loss_index", "acq_index", "never_locked", "ae_med")}
        print(f"[{tag}] kf done ({time.time() - t0:.0f}s)", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1))

    bc = np.asarray(per_seq["bucket_class"])
    print("\nrung  | bucket  | v2 lost (pooled) | v6 lost (pooled) | kf (ref)")
    for tag in results["cells"]:
        for cls in (0, 1, 2):
            idx = np.flatnonzero(bc == cls)
            def lost_of(names):
                return sum(sum(results["cells"][tag][s]["lost_all"][i] for i in idx)
                           for s in names), len(idx) * len(names)
            a = lost_of(GENS["v2"]["seeds"])
            b = lost_of(GENS["v6"]["seeds"])
            kf = sum(results["cells"][tag]["kf"]["lost_all"][i] for i in idx)
            print(f"{tag:<6}| {BUCKET_NAMES[cls]:<8}| {a[0]}/{a[1]:<15} | "
                  f"{b[0]}/{b[1]:<15} | {kf}/{len(idx)}")
    print(f"\n[fieldcone] wrote {OUT} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
