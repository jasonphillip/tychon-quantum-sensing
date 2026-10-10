"""Increment-8 per-arm eval — dwell coverage split + field-cone + deployment-neutrality check.

Produces the eval artifacts the increment-8 verdict compares against the (also locally-computed)
`baseline-env` arm. The v1 standing-eval re-decode matrix is produced separately by
`identity_redecode.py --runs-dir ... --seeds ... --out artifacts/increment8/<arm>/redecode.json`.

Reuses the increment-6/7 harness verbatim (`identity_redecode.run_ckpt_outputs`,
`noise_matrix_report` helpers, `redecode` decoders, the field-cone `lock_stats`) so an arm's
numbers are directly comparable across arms (identical fixed-seed noise). LOCAL on spark2 only —
the eval sets never leave the machine.

    python experiments/increment8_eval.py --arm bc \
        --runs-dir artifacts/increment8/runs/bc \
        --seeds bc_s20260701 bc_s20260711 bc_s20260721 bc_s20260731 bc_s20260741
"""

from __future__ import annotations

import argparse
import csv
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
from odmr_vector_tracking.evaluation.metrics import vector_angular_error  # noqa: E402
from odmr_vector_tracking.evaluation.rows import LOSS_DEG  # noqa: E402
from odmr_vector_tracking.tracking.learned import (  # noqa: E402
    build_tracker, config_from_checkpoint, load_tracker_state,
)
from odmr_vector_tracking.validation.ops_guard import check_model_ops  # noqa: E402
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

DWELL = _REPO_ROOT / "data" / "sequence_dwell_v1"
FIELDCONE = _REPO_ROOT / "data" / "sequence_eval_fieldcone_v1"
V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
IN_COVERAGE_TEMPLATES = (0, 1)
RUNGS = (("clean", None), ("snr30", 30.0))
STUDENT_PARAMS = 175790


def _angular_row(B_true: np.ndarray, B_est: np.ndarray) -> dict:
    ae = vector_angular_error(B_true, B_est)
    valid = ae[np.isfinite(ae)]
    return {"angular_error_mean": float(valid.mean()) if valid.size else float("nan"),
            "angular_error_p90": float(np.percentile(valid, 90)) if valid.size else float("nan"),
            "lock_fraction": float(np.mean(np.isfinite(ae) & (ae <= LOSS_DEG)))}


def write_sequence_csv(path: Path, rows: list[dict]) -> None:
    """Write per-sequence observations."""
    columns = ["seq_index", "bucket_class", "rung", "seed", "decode"]
    columns += sorted({key for row in rows for key in row} - set(columns))
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def dwell_split(runs_dir: Path, seeds: list[str], device: torch.device,
                sequence_rows: list[dict] | None = None) -> dict:
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
            angular = [_angular_row(ds.B_true[n], s["b_est"])
                       for n, s in enumerate(seqs)]
            for kind in ("baseline", "stack5"):
                rows = [nmr._row(ir.decode_tracked(kind, s, cap, lw), pred_axis,
                                 s["b_est"], ds, n, m) for n, s in enumerate(seqs)]
                if sequence_rows is not None:
                    for n, row in enumerate(rows):
                        sequence_rows.append({
                            "seq_index": n, "bucket_class": labels[n], "rung": tag,
                            "seed": seed, "decode": kind,
                            **angular[n],
                            "acq_index": fc6.lock_stats(ds.B_true[n],
                                                         seqs[n]["b_est"])["acq_index"],
                            **(row or {}),
                        })
                agg = nmr.aggregate(rows, labels)
                cells.setdefault(f"decode:{kind}", {})[seed] = {
                    p: {"idsw_opp": agg[p]["idsw_opp"][:2],
                        "lock_loss": agg[p]["lock_loss"][:2],
                        "lock_fraction": float(np.mean([
                            angular[n]["lock_fraction"] for n, label in enumerate(labels)
                            if label == p])),
                        "lock_fraction_all": [angular[n]["lock_fraction"]
                                              for n, label in enumerate(labels) if label == p]}
                    for p in pops}
            print(f"[dwell:{tag}] {seed} done ({time.time()-t0:.0f}s)", flush=True)
    return out


def fieldcone(runs_dir: Path, seeds: list[str], device: torch.device,
              sequence_rows: list[dict] | None = None) -> dict:
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
            angular = [_angular_row(ds.B_true[n], s["b_est"])
                       for n, s in enumerate(seqs)]
            if sequence_rows is not None:
                for n, stat in enumerate(stats):
                    sequence_rows.append({
                        "seq_index": n, "bucket_class": per_seq["bucket_class"][n],
                        "rung": tag, "seed": seed, "decode": "fieldcone",
                        "target_angle_deg": per_seq["target_angle_deg"][n],
                        "target_B_mT": per_seq["target_B_mT"][n],
                        **angular[n], **stat,
                    })
            cells[seed] = {k + "_all": [s[k] for s in stats]
                           for k in ("lost", "loss_index", "acq_index", "never_locked", "ae_med")}
            cells[seed]["lock_fraction_all"] = [row["lock_fraction"] for row in angular]
            cells[seed]["lock_fraction"] = float(np.mean(cells[seed]["lock_fraction_all"]))
            print(f"[fieldcone:{tag}] {seed} done ({time.time()-t0:.0f}s)", flush=True)
    return out


def deploy_check(runs_dir: Path, seeds: list[str]) -> dict:
    """Deployment-neutrality assertion: every candidate ckpt has 175,790 params and its V250
    extractor passes the ops-guard (architecture-determined — the training levers never touch it)."""
    out: dict = {"seeds": list(seeds), "param_counts": {}, "ops_guard": {}}
    for seed in seeds:
        ck = torch.load(runs_dir / seed / "best.pt", map_location="cpu", weights_only=False)
        cfg = config_from_checkpoint(ck["model_cfg"], ck["model_state"])
        trk = build_tracker(cfg, core=ck["meta"]["core"], association=ck["meta"]["association"])
        load_tracker_state(trk, ck["model_state"])
        out["param_counts"][seed] = sum(p.numel() for p in trk.parameters() if p.requires_grad)
        rep = check_model_ops(trk.extractor, input_shape=(1, cfg.n_freq))
        out["ops_guard"][seed] = {"compatible": bool(rep.is_compatible),
                                  "disallowed": list(rep.disallowed)}
    out["all_params_175790"] = all(v == STUDENT_PARAMS for v in out["param_counts"].values())
    out["all_ops_compatible"] = all(v["compatible"] for v in out["ops_guard"].values())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-8 per-arm eval (dwell + fieldcone + deploy)")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--runs-dir", type=Path, required=True)
    ap.add_argument("--seeds", nargs="+", required=True)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | device {device} | arm {args.arm}")
    out_dir = _REPO_ROOT / "artifacts" / "increment8" / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)

    dep = deploy_check(args.runs_dir, args.seeds)
    (out_dir / "deploy.json").write_text(json.dumps(dep, indent=1))
    print(f"[eval] deploy: params==175790 all={dep['all_params_175790']} "
          f"ops-compatible all={dep['all_ops_compatible']} -> {out_dir / 'deploy.json'}")

    dwell_rows: list[dict] = []
    dw = dwell_split(args.runs_dir, args.seeds, device, dwell_rows)
    (out_dir / "dwell.json").write_text(json.dumps(dw, indent=1))
    write_sequence_csv(out_dir / "dwell_per_sequence.csv", dwell_rows)
    print(f"[eval] wrote {out_dir / 'dwell.json'}")

    fieldcone_rows: list[dict] = []
    fc = fieldcone(args.runs_dir, args.seeds, device, fieldcone_rows)
    (out_dir / "fieldcone.json").write_text(json.dumps(fc, indent=1))
    write_sequence_csv(out_dir / "fieldcone_per_sequence.csv", fieldcone_rows)
    print(f"[eval] wrote {out_dir / 'fieldcone.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
