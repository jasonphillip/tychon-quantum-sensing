"""Increment-7 per-arm eval — dwell coverage split + field-cone, for one arm's checkpoints.

Produces the two eval artifacts the increment-7 verdict compares against the (already-computed)
v6 baselines. The v1 standing-eval re-decode matrix is produced separately by
`identity_redecode.py --runs-dir ... --seeds ... --out artifacts/increment7/<arm>/redecode.json`.

Reuses the increment-6 harness verbatim (`identity_redecode.run_ckpt_outputs`, `noise_matrix_report`
helpers, `redecode` decoders, the field-cone `lock_stats`) so an arm's numbers are directly
comparable to `coverage_split_v6.json` / `fieldcone_v6.json` (identical fixed-seed noise).

    python experiments/increment7_eval.py --arm 7a \
        --runs-dir artifacts/increment7/runs/7a \
        --seeds fov_gated_linear_snr10 fov_gated_linear_snr10_s20260711 fov_gated_linear_snr10_s20260721
"""

from __future__ import annotations

import argparse
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
import increment6_fieldcone as fc6  # noqa: E402  (lock_stats)
import noise_matrix_report as nmr  # noqa: E402
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.data.contract import validate_dataset_dir  # noqa: E402
from odmr_vector_tracking.tracking import redecode as rd  # noqa: E402
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

DWELL = _REPO_ROOT / "data" / "sequence_dwell_v1"
FIELDCONE = _REPO_ROOT / "data" / "sequence_eval_fieldcone_v1"
V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
IN_COVERAGE_TEMPLATES = (0, 1)
RUNGS = (("clean", None), ("snr30", 30.0))


def dwell_split(runs_dir: Path, seeds: list[str], device: torch.device) -> dict:
    """Arm dwell coverage split (baseline + A3), same populations/format as coverage_split_v6."""
    m = validate_dataset_dir(DWELL)
    lw = float(m["linewidth_Hz"])
    cap = nmr.CAPTURE_RADIUS_LW * lw
    v1_depths = np.asarray(validate_dataset_dir(V1_DIR)["line_depths"])
    faintest = float(v1_depths.min())
    clean = SequenceDatasetLoader(DWELL).load_split("test")
    with h5py.File(DWELL / "dataset.h5", "r") as f:
        tmpl = f["test/template_idx"][:]
        topo = f["test/exit_topology"][:]
    labels = [f"{'cov' if t in IN_COVERAGE_TEMPLATES else 'offcone'}/"
              f"{'cross' if x == 0 else 'bounce'}" for t, x in zip(tmpl, topo)]
    pops = sorted(set(labels))
    T = clean.spectra.shape[1]
    pred_axis = np.broadcast_to(LINE_AXIS_8, (T, 8))
    budgets = {tag: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for tag, snr in RUNGS}
    out: dict = {"populations": pops, "budgets": budgets, "seeds": list(seeds), "cells": {}}
    t0 = time.time()
    for tag, photons in budgets.items():
        ds = nmr.noisy_copy(clean, photons)
        cells = out["cells"].setdefault(tag, {})
        for seed in seeds:
            seqs, _ = ir.run_ckpt_outputs(runs_dir / seed / "best.pt", ds, device)
            for kind in ("baseline", "stack5"):
                rows = [nmr._row(ir.decode_tracked(kind, s, cap, lw), pred_axis,
                                 s["b_est"], ds, n, m) for n, s in enumerate(seqs)]
                agg = nmr.aggregate(rows, labels)
                cells.setdefault(f"decode:{kind}", {})[seed] = {
                    p: {"idsw_opp": agg[p]["idsw_opp"][:2],
                        "lock_loss": agg[p]["lock_loss"][:2]} for p in pops}
            print(f"[dwell:{tag}] {seed} done ({time.time()-t0:.0f}s)", flush=True)
    return out


def fieldcone(runs_dir: Path, seeds: list[str], device: torch.device) -> dict:
    """Arm field-cone lock/acquisition per bucket, same format as fieldcone_v6."""
    m = validate_dataset_dir(FIELDCONE)
    v1_depths = np.asarray(validate_dataset_dir(V1_DIR)["line_depths"])
    faintest = float(v1_depths.min())
    clean = SequenceDatasetLoader(FIELDCONE).load_split("test")
    with h5py.File(FIELDCONE / "dataset.h5", "r") as f:
        per_seq = {k: f[f"test/{k}"][:].tolist()
                   for k in ("bucket_class", "target_angle_deg", "target_B_mT")}
    budgets = {tag: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for tag, snr in RUNGS}
    out: dict = {**per_seq, "budgets": budgets, "seeds": list(seeds), "cells": {}}
    t0 = time.time()
    for tag, photons in budgets.items():
        ds = nmr.noisy_copy(clean, photons)
        cells = out["cells"].setdefault(tag, {})
        for seed in seeds:
            seqs, _ = ir.run_ckpt_outputs(runs_dir / seed / "best.pt", ds, device)
            stats = [fc6.lock_stats(ds.B_true[n], s["b_est"]) for n, s in enumerate(seqs)]
            cells[seed] = {k + "_all": [s[k] for s in stats]
                           for k in ("lost", "loss_index", "acq_index", "never_locked", "ae_med")}
            print(f"[fieldcone:{tag}] {seed} done ({time.time()-t0:.0f}s)", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-7 per-arm eval (dwell + fieldcone)")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--runs-dir", type=Path, required=True)
    ap.add_argument("--seeds", nargs="+", required=True)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | device {device} | arm {args.arm}")
    out_dir = _REPO_ROOT / "artifacts" / "increment7" / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)

    dw = dwell_split(args.runs_dir, args.seeds, device)
    (out_dir / "dwell.json").write_text(json.dumps(dw, indent=1))
    print(f"[eval] wrote {out_dir / 'dwell.json'}")

    fc = fieldcone(args.runs_dir, args.seeds, device)
    (out_dir / "fieldcone.json").write_text(json.dumps(fc, indent=1))
    print(f"[eval] wrote {out_dir / 'fieldcone.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
