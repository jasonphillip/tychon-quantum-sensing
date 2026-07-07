"""Increment-6 tri-eval 2 (PRIMARY) — dwell coverage split, v6 vs v2 checkpoints.

Re-runs the increment-5 coverage-split logic (`increment5_coverage_split.py`) on the
coverage-retrained v6 checkpoints alongside the deployed v2 checkpoints, at the clean AND
snr30 rungs (fixed-seed shot noise, identical for every tracker — `noise_matrix_report`
conventions). Populations are the increment-5 ones: templates 0/1 = `cov` (in the v1/v2
training envelope), templates 2/3 = `offcone` (41/53 deg off-bias — the measured v2
acquisition failure), split by exit topology.

Beyond increment-5, every aggregate cell retains the PER-SEQUENCE idsw counts
(`idsw_opp_switches_all` / `idsw_opp_n_all`) so identity can be conditioned on lock survival
downstream (2c house rule as patched by dispatch-6 §1 — the increment-5 artifact only stored
pooled idsw, which forced a re-run to condition).

Success/failure is NOT decided here — `increment6_verdict.py` (committed pre-hoc) reads the
artifact. b_est purity: asserted per sequence (decodes must not touch the field estimate).

    python experiments/increment6_coverage_split.py

Writes `artifacts/increment6/coverage_split_v6.json`.
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
from odmr_vector_tracking.tracking import redecode as rd  # noqa: E402
from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker  # noqa: E402
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

DWELL = _REPO_ROOT / "data" / "sequence_dwell_v1"
V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
OUT = _REPO_ROOT / "artifacts" / "increment6" / "coverage_split_v6.json"
IN_COVERAGE_TEMPLATES = (0, 1)
RUNGS = (("clean", None), ("snr30", 30.0))
GENS = {
    "v2": {"dir": _REPO_ROOT / "artifacts" / "increment2c", "seeds": ir.BASELINE_SEEDS},
    "v6": {"dir": _REPO_ROOT / "artifacts" / "increment6" / "runs",
           "seeds": ("v3_gated_linear_snr10", "v3_gated_linear_snr10_s20260711",
                     "v3_gated_linear_snr10_s20260721")},
}


def aggregate_with_idsw(rows: list[dict | None], families: list[str]) -> dict[str, dict]:
    """nmr.aggregate + per-sequence idsw counts (for downstream lock-conditioning)."""
    out = nmr.aggregate(rows, families)
    for fam in out:
        fr = [r for r, f in zip(rows, families) if f == fam and r is not None]
        out[fam]["idsw_opp_switches_all"] = [float(r["idsw_opp_switches"]) for r in fr]
        out[fam]["idsw_opp_n_all"] = [int(r["idsw_opp_n"]) for r in fr]
    return out


def main() -> int:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    m = validate_dataset_dir(DWELL)
    lw = float(m["linewidth_Hz"])
    cap = nmr.CAPTURE_RADIUS_LW * lw
    faintest = float(np.min(np.asarray(m["line_depths"])))
    v1_depths = validate_dataset_dir(V1_DIR)["line_depths"]
    clean = SequenceDatasetLoader(DWELL).load_split("test")
    with h5py.File(DWELL / "dataset.h5", "r") as f:
        tmpl = f["test/template_idx"][:]
        topo = f["test/exit_topology"][:]
    labels = [f"{'cov' if t in IN_COVERAGE_TEMPLATES else 'offcone'}/"
              f"{'cross' if x == 0 else 'bounce'}" for t, x in zip(tmpl, topo)]
    T = clean.spectra.shape[1]
    pred_axis = np.broadcast_to(LINE_AXIS_8, (T, 8))

    budgets = {tag: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for tag, snr in RUNGS}
    results: dict = {"populations": sorted(set(labels)),
                     "noise_master_seed": nmr.NOISE_MASTER_SEED,
                     "budgets": budgets,
                     "gens": {g: list(v["seeds"]) for g, v in GENS.items()},
                     "cells": {}}
    t0 = time.time()
    for tag, photons in budgets.items():
        ds = nmr.noisy_copy(clean, photons)
        cells = results["cells"].setdefault(tag, {})
        for gen, spec in GENS.items():
            for seed in spec["seeds"]:
                ckpt = spec["dir"] / seed / "best.pt"
                seqs, _ = ir.run_ckpt_outputs(ckpt, ds, device)
                for kind in ("baseline", "stack5"):
                    rows = []
                    for n, s in enumerate(seqs):
                        b_ref = s["b_est"].copy()
                        tr = s["track_hz"] if kind == "baseline" else \
                            rd.stacked_decode(s["scores"], s["b_est"], s["cand_hz"],
                                              cap, lw, lag=5)
                        assert np.array_equal(s["b_est"], b_ref), \
                            f"b_est purity violated: {kind} touched the field estimate"
                        rows.append(nmr._row(tr, pred_axis, s["b_est"], ds, n, m))
                    cells.setdefault(f"decode:{kind}", {})[seed] = \
                        aggregate_with_idsw(rows, labels)
                print(f"[{tag}] {gen}/{seed} done ({time.time() - t0:.0f}s)", flush=True)
        kf_rows = []
        for n in range(ds.spectra.shape[0]):
            trk = KFHungarianTracker(ds.frequencies, linewidth_Hz=m["linewidth_Hz"],
                                     peak_min_depth=nmr.detector_depth(
                                         ds.spectra[n], {**m, "line_depths": v1_depths},
                                         photons))
            res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
            kf_rows.append(nmr._row(res.tracked_freqs.astype(np.float64), res.pred_axis,
                                    res.B_est, ds, n, m))
        cells["kf"] = aggregate_with_idsw(kf_rows, labels)
        print(f"[{tag}] kf done ({time.time() - t0:.0f}s)", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1))

    print("\nrung  | pop            | gen | lock-loss (pooled)   | idsw/opp")
    for tag in results["cells"]:
        for pop in sorted(set(labels)):
            for gen, spec in GENS.items():
                k = n = sw = op = 0
                for seed in spec["seeds"]:
                    v = results["cells"][tag]["decode:baseline"][seed][pop]
                    k += v["lock_loss"][0]; n += v["lock_loss"][1]
                    sw += v["idsw_opp"][0]; op += v["idsw_opp"][1]
                print(f"{tag:<6}| {pop:<15}| {gen}  | {k}/{n:<18} | {sw / op:.3f}")
            v = results["cells"][tag]["kf"][pop]
            print(f"{tag:<6}| {pop:<15}| kf  | {v['lock_loss'][0]}/{v['lock_loss'][1]:<18} "
                  f"| {v['idsw_opp'][0] / v['idsw_opp'][1]:.3f}")
    print(f"\n[coverage-v6] wrote {OUT} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
