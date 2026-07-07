"""Increment-5 coverage split — dwell-boundary metrics conditioned on training-envelope coverage.

The pooled dwell matrix mixes two deterministic subpopulations: templates 0/1 (merge pairs
(0,6)/(2,4)) keep |B| ~ 4.9-5.0 mT within 6-15 deg of the bias direction — inside the v1/v2
training envelope (max ~18 deg off-bias) — while templates 2/3 (pairs (0,2)/(4,6)) require
41/53 deg off-bias at 3.9/3.3 mT to force their cross-axis degeneracy, far outside anything the
tracker was trained on. The learned field lock fails on templates 2/3 for every sequence, every
seed, every dwell (a training-coverage gap, not noise). This script re-scores the cues-OFF clean
rung split by that coverage population so the identity boundary can be read without the
off-cone field-loss confound.

    python experiments/increment5_coverage_split.py
"""

from __future__ import annotations

import json
import sys
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
from odmr_vector_tracking.tracking import redecode as rd  # noqa: E402
from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker  # noqa: E402
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

DWELL = _REPO_ROOT / "data" / "sequence_dwell_v1"
V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
OUT = _REPO_ROOT / "artifacts" / "increment5" / "coverage_split.json"
IN_COVERAGE_TEMPLATES = (0, 1)  # <=15 deg off-bias at ~4.9-5.0 mT; 2/3 are 41/53 deg off-cone


def main() -> int:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    m = validate_dataset_dir(DWELL)
    lw = float(m["linewidth_Hz"])
    cap = nmr.CAPTURE_RADIUS_LW * lw
    v1_depths = validate_dataset_dir(V1_DIR)["line_depths"]
    ds = SequenceDatasetLoader(DWELL).load_split("test")
    with h5py.File(DWELL / "dataset.h5", "r") as f:
        tmpl = f["test/template_idx"][:]
        topo = f["test/exit_topology"][:]
    labels = [f"{'cov' if t in IN_COVERAGE_TEMPLATES else 'offcone'}/"
              f"{'cross' if x == 0 else 'bounce'}" for t, x in zip(tmpl, topo)]
    T = ds.spectra.shape[1]
    pred_axis = np.broadcast_to(LINE_AXIS_8, (T, 8))

    results: dict = {"populations": sorted(set(labels)), "clean_rung_only": True, "cells": {}}
    for seed in ir.BASELINE_SEEDS:
        seqs, _ = ir.run_ckpt_outputs(_REPO_ROOT / "artifacts/increment2c" / seed / "best.pt",
                                      ds, device)
        for kind in ("baseline", "stack5"):
            rows = []
            for n, s in enumerate(seqs):
                tr = s["track_hz"] if kind == "baseline" else \
                    rd.stacked_decode(s["scores"], s["b_est"], s["cand_hz"], cap, lw, lag=5)
                rows.append(nmr._row(tr, pred_axis, s["b_est"], ds, n, m))
            results["cells"].setdefault(f"decode:{kind}", {})[seed] = nmr.aggregate(rows, labels)
        print(f"[learned {seed}] done")
    kf_rows = []
    for n in range(ds.spectra.shape[0]):
        trk = KFHungarianTracker(ds.frequencies, linewidth_Hz=m["linewidth_Hz"],
                                 peak_min_depth=nmr.detector_depth(
                                     ds.spectra[n], {**m, "line_depths": v1_depths}, None))
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        kf_rows.append(nmr._row(res.tracked_freqs.astype(np.float64), res.pred_axis,
                                res.B_est, ds, n, m))
    results["cells"]["kf"] = nmr.aggregate(kf_rows, labels)
    print("[kf] done")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1))

    def pooled(dec, pop, key):
        c = results["cells"][dec]
        if dec == "kf":
            v = c[pop][key]
            return v[0], v[1]
        k = sum(c[s][pop][key][0] for s in ir.BASELINE_SEEDS)
        n = sum(c[s][pop][key][1] for s in ir.BASELINE_SEEDS)
        return k, n

    print("\npop        | decode   | misassoc | idsw/opp | lock-loss")
    for pop in sorted(set(labels)):
        for dec in ("decode:baseline", "decode:stack5", "kf"):
            mm = pooled(dec, pop, "misassoc")
            ii = pooled(dec, pop, "idsw_opp")
            ll = pooled(dec, pop, "lock_loss")
            print(f"{pop:<11}| {dec.removeprefix('decode:'):<9}| "
                  f"{mm[0]/mm[1]:.3f}    | {ii[0]/ii[1]:.3f}    | {ll[0]}/{ll[1]}")
    print(f"\n[coverage] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
