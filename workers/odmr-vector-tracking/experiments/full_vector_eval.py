"""Full-vector field-cone evaluation with paired, sequence-blocked comparisons.

Uses the same fixed noise realization and learned tracker inference as increment6_fieldcone.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "experiments"))

import identity_redecode as ir  # noqa: E402
import increment6_fieldcone as fc6  # noqa: E402
import noise_matrix_report as nmr  # noqa: E402
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.data.contract import validate_dataset_dir  # noqa: E402
from odmr_vector_tracking.evaluation.metrics import wilson_ci  # noqa: E402
from odmr_vector_tracking.evaluation.rows import fieldcone_metrics_row  # noqa: E402

METRICS = ("rmse_T", "ae_mean_deg", "lock_frac", "lost")


def _number(row: dict, metric: str) -> float:
    """Read numeric metrics from in-memory rows or CSV rows."""
    value = row[metric]
    if metric == "lost" and isinstance(value, str):
        return float(value.lower() in ("true", "1"))
    return float(value)


def paired_differences(first: list[dict], second: list[dict],
                       draws: int = 10_000, seed: int = 0) -> dict:
    """Second-minus-first means and 95% paired bootstrap CIs by sequence index.

    Each draw resamples matched sequences. The same sampled indices apply to both
    checkpoints, preserving each sequence as the comparison block.
    """
    a = {int(row["seq_index"]): row for row in first}
    b = {int(row["seq_index"]): row for row in second}
    if len(a) != len(first) or len(b) != len(second):
        raise ValueError("duplicate seq_index in paired rows")
    common = sorted(a.keys() & b.keys())
    if not common:
        raise ValueError("no matched seq_index values")
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(common), size=(draws, len(common)))
    result = {}
    for metric in METRICS:
        delta = np.array([_number(b[i], metric) - _number(a[i], metric)
                          for i in common], dtype=np.float64)
        valid = np.isfinite(delta)
        if not valid.all():
            delta = delta[valid]
            metric_samples = rng.integers(0, len(delta), size=(draws, len(delta))) if len(delta) else None
        else:
            metric_samples = samples
        if len(delta):
            lo, hi = np.percentile(delta[metric_samples].mean(axis=1), [2.5, 97.5])
            result[metric] = {"mean_diff": float(delta.mean()), "ci95": [float(lo), float(hi)],
                              "n": int(len(delta))}
        else:
            result[metric] = {"mean_diff": float("nan"), "ci95": [float("nan")] * 2,
                              "n": 0}
    return result


def _summary(rows: list[dict]) -> dict:
    """Aggregate per-sequence scores without weighting longer sequences more."""
    out = {"n_sequences": len(rows),
           "n_valid_sequences": sum(int(row["n_valid_frames"]) > 0 for row in rows)}
    for metric in ("rmse_T", "ae_mean_deg", "mag_err_mean_T"):
        values = np.asarray([row[metric] for row in rows], dtype=float)
        valid = values[np.isfinite(values)]
        out[metric] = {"mean": float(valid.mean()) if valid.size else float("nan"),
                       "p90": float(np.percentile(valid, 90)) if valid.size else float("nan"),
                       "n_valid_sequences": int(valid.size)}
    out["lock_frac_mean"] = float(np.mean([row["lock_frac"] for row in rows])) if rows else float("nan")
    lost = sum(bool(row["lost"]) for row in rows)
    out["lost"] = {"count": lost, "wilson_ci": list(wilson_ci(lost, len(rows)))}
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["seq_index", "bucket_class"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Full-vector field-cone checkpoint evaluation")
    ap.add_argument("--ckpt", type=Path, action="append", required=True)
    ap.add_argument("--label", action="append", required=True)
    ap.add_argument("--dataset", type=Path, default=fc6.FIELDCONE)
    ap.add_argument("--rungs", default="clean,snr30")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if len(args.ckpt) != len(args.label) or len(set(args.label)) != len(args.label):
        ap.error("provide one unique --label per --ckpt")
    if any(not label or Path(label).name != label for label in args.label):
        ap.error("labels must be single path components")
    rungs = [r.strip() for r in args.rungs.split(",") if r.strip()]
    valid_rungs = dict(fc6.RUNGS)
    if not rungs or len(set(rungs)) != len(rungs) or any(r not in valid_rungs for r in rungs):
        ap.error("--rungs must be a comma-separated subset of clean,snr30")

    manifest = validate_dataset_dir(args.dataset)
    clean = SequenceDatasetLoader(args.dataset).load_split("test")
    with h5py.File(args.dataset / "dataset.h5", "r") as fh:
        buckets = fh["test/bucket_class"][:]
    if len(buckets) != clean.spectra.shape[0]:
        raise ValueError("bucket_class count differs from test sequence count")
    v1_depths = validate_dataset_dir(fc6.V1_DIR)["line_depths"]
    faintest = float(np.min(v1_depths))
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {"dataset": str(args.dataset), "rungs": rungs,
               "noise_master_seed": nmr.NOISE_MASTER_SEED, "cells": {}}
    tables: dict[str, dict[str, list[dict]]] = {rung: {} for rung in rungs}
    for rung in rungs:
        snr = valid_rungs[rung]
        photons = None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr))
        ds = nmr.noisy_copy(clean, photons)
        for ckpt, label in zip(args.ckpt, args.label):
            sequences, _ = ir.run_ckpt_outputs(ckpt, ds, device)
            if len(sequences) != len(buckets):
                raise ValueError("tracker output count differs from test sequence count")
            rows = []
            for i, sequence in enumerate(sequences):
                row = {"seq_index": i, "bucket_class": int(buckets[i])}
                row.update(fieldcone_metrics_row(ds.B_true[i], sequence["b_est"],
                                                 dt_s=float(manifest["dt_s"])))
                rows.append(row)
            _write_csv(args.out / f"{label}_{rung}_per_sequence.csv", rows)
            summary["cells"].setdefault(label, {})[rung] = _summary(rows)
            tables[rung][label] = rows
            print(f"[{label}/{rung}] {len(rows)} sequences", flush=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=True) + "\n")
    if len(args.label) == 2:
        first, second = args.label
        paired = {"first": first, "second": second,
                  "rungs": {r: paired_differences(tables[r][first], tables[r][second]) for r in rungs}}
        (args.out / "paired.json").write_text(json.dumps(paired, indent=2, allow_nan=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
