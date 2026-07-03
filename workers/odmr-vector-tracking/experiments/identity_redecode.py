"""Zero-retrain identity re-decode matrix (increment-2c lever A).

Runs the three baseline-seed v2 checkpoints through the SAME noise-matrix harness
(``noise_matrix_report``: identical fixed-seed shot noise, family split, capture radius, and
``sequence_metrics_row`` scoring) and, for each, applies the post-hoc identity decoders in
``tracking.redecode`` to the saved inference outputs. The field estimate ``b_est`` is untouched,
so every decode variant shares the baseline's FIELD metrics exactly — the script ASSERTS this,
which is the honesty guarantee: a re-decode cannot inflate the vector/lock claim.

Decode variants scored per rung × family × seed:
  baseline  – the deployed per-slot readout ``track_pos`` (== the plain gated column of
              ``matrix_2c_final.json``; cross-checked)
  greedy    – instantaneous exclusive assignment on the raw scores (lag 0) — the reference the
              deferred decode is measured against
  smooth5   – A2 fixed-lag smoothed exclusive decode, latency 5 frames
  smooth15  – A2, latency 15 frames
  physics   – A1 physics-anchored decode from ``b_est`` (no scores)
  stack5    – A3 smoothed scores + physics prior + physics fallback, latency 5 frames

Writes the matrix and a survival verdict (CI-disjoint vs the baseline decode, per seed +
pooled) to ``artifacts/noise_matrix/``. Standing eval only (v1 test) — no training.

    python experiments/identity_redecode.py            # full: 3 seeds × 4 rungs
    python experiments/identity_redecode.py --limit 10 --rungs clean --seeds v2_gated_linear_snr10  # dry-run
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "experiments"))

import noise_matrix_report as nmr  # noqa: E402  (shared harness: noisy_copy, aggregate, ...)
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.data.contract import validate_dataset_dir  # noqa: E402
from odmr_vector_tracking.tracking import redecode as rd  # noqa: E402
from odmr_vector_tracking.tracking.learned import (  # noqa: E402
    build_tracker, config_from_checkpoint, load_tracker_state,
)
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
DEFAULT_RUNS_DIR = _REPO_ROOT / "artifacts" / "increment2c"
BASELINE_SEEDS = ("v2_gated_linear_snr10", "v2_gated_linear_snr10_s20260711",
                  "v2_gated_linear_snr10_s20260721")
LAT5, LAT15 = 5, 15


def run_ckpt_outputs(ckpt: Path, ds, device: torch.device) -> tuple[list[dict], dict]:
    """Run a learned checkpoint over every sequence; return per-seq numpy outputs (Hz) + meta."""
    ck = torch.load(ckpt, map_location=device, weights_only=False)
    cfg = config_from_checkpoint(ck["model_cfg"], ck["model_state"])
    meta = ck["meta"]
    trk = build_tracker(cfg, core=meta["core"], association=meta["association"]).to(device)
    load_tracker_state(trk, ck["model_state"])
    trk.eval()
    f0, f1 = meta["freq_range_Hz"]
    span = f1 - f0
    seqs: list[dict] = []
    with torch.no_grad():
        for lo in range(0, ds.spectra.shape[0], 32):
            o = trk(torch.from_numpy(ds.spectra[lo:lo + 32]).float().to(device))
            b_est = o.b_est.cpu().numpy()
            scores = o.scores.cpu().numpy()
            cand = o.cand_pos.cpu().numpy() * span + f0
            track = o.tracked_freqs.cpu().numpy() * span + f0
            for i in range(b_est.shape[0]):
                seqs.append({"b_est": b_est[i], "scores": scores[i],
                             "cand_hz": cand[i], "track_hz": track[i]})
    return seqs, meta


def decode_tracked(kind: str, s: dict, capture_radius_hz: float, linewidth_hz: float) -> np.ndarray:
    """Return ``tracked_hz (T, 8)`` for one sequence under a decode variant."""
    if kind == "baseline":
        return s["track_hz"]
    if kind == "greedy":
        return rd.smoothed_exclusive_decode(s["scores"], s["cand_hz"], lag=0)
    if kind == "smooth5":
        return rd.smoothed_exclusive_decode(s["scores"], s["cand_hz"], lag=LAT5)
    if kind == "smooth15":
        return rd.smoothed_exclusive_decode(s["scores"], s["cand_hz"], lag=LAT15)
    if kind == "physics":
        return rd.physics_anchored_decode(s["b_est"], s["cand_hz"], capture_radius_hz)
    if kind == "stack5":
        return rd.stacked_decode(s["scores"], s["b_est"], s["cand_hz"],
                                 capture_radius_hz, linewidth_hz, lag=LAT5)
    raise ValueError(kind)


DECODES = ("baseline", "greedy", "smooth5", "smooth15", "physics", "stack5")


def main() -> int:
    ap = argparse.ArgumentParser(description="Zero-retrain identity re-decode matrix (2c lever A)")
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", type=Path,
                    default=_REPO_ROOT / "artifacts" / "noise_matrix" / "matrix_2c_redecode.json")
    ap.add_argument("--limit", type=int, default=0, help="cap sequences (dry-run)")
    ap.add_argument("--rungs", nargs="*", default=None, help="subset of rung tags (dry-run)")
    ap.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR,
                    help="checkpoint dir (default artifacts/increment2c)")
    ap.add_argument("--seeds", nargs="*", default=None,
                    help="run-dir names to score (default: the wave-2 baselines)")
    args = ap.parse_args()
    runs_dir = args.runs_dir

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | device {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))

    m = validate_dataset_dir(V1_DIR)
    linewidth_hz = float(m["linewidth_Hz"])
    capture_radius_hz = nmr.CAPTURE_RADIUS_LW * linewidth_hz
    ld = SequenceDatasetLoader(V1_DIR)
    clean = ld.load_split(args.split)
    faintest = float(np.min(np.asarray(m["line_depths"])))
    with open(V1_DIR / "manifest.json") as fh:
        fams = json.load(fh)["sequence_stats"][args.split]["trajectory_family_per_sequence"]
    if args.limit:
        clean = dataclasses.replace(clean, spectra=clean.spectra[:args.limit])
        fams = fams[:args.limit]

    rungs = [(t, s) for t, s in nmr.SNR_RUNGS if args.rungs is None or t in args.rungs]
    seeds = list(args.seeds) if args.seeds else list(BASELINE_SEEDS)
    budgets = {t: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for t, snr in rungs}

    pred_axis = np.broadcast_to(LINE_AXIS_8, (clean.spectra.shape[1], 8))
    results = {"noise_master_seed": nmr.NOISE_MASTER_SEED, "capture_radius_lw": nmr.CAPTURE_RADIUS_LW,
               "latency_frames": {"smooth5": LAT5, "smooth15": LAT15, "stack5": LAT5},
               "seeds": list(seeds), "cells": {}}

    t0 = time.time()
    for tag, photons in budgets.items():
        ds = nmr.noisy_copy(clean, photons)
        cells = results["cells"].setdefault(tag, {})
        # Classical references (pid/kf/nls) are NOT recomputed here — they are identical to
        # matrix_2c_final.json and the survival rule compares decode-vs-learned-baseline. The
        # KF identity crown is pulled from the final matrix when reporting.
        # learned decode variants, per seed
        for seed in seeds:
            seqs, _ = run_ckpt_outputs(runs_dir / seed / "best.pt", ds, device)
            field_ref = None
            for kind in DECODES:
                rows = []
                for n, s in enumerate(seqs):
                    tracked = decode_tracked(kind, s, capture_radius_hz, linewidth_hz)
                    rows.append(nmr._row(tracked, pred_axis, s["b_est"], ds, n, m))
                agg = nmr.aggregate(rows, fams)
                # FIELD invariance: b_est untouched → lock_loss / ae_post identical across decodes
                if field_ref is None:
                    field_ref = {f: (agg[f]["lock_loss"][0], agg[f]["ae_post_all"]) for f in agg}
                else:
                    for f in agg:
                        assert agg[f]["lock_loss"][0] == field_ref[f][0], f"lock drift {seed}/{tag}/{f}/{kind}"
                        assert np.allclose(np.nan_to_num(agg[f]["ae_post_all"], nan=-1),
                                           np.nan_to_num(field_ref[f][1], nan=-1)), \
                            f"ae_post drift {seed}/{tag}/{f}/{kind}"
                cells.setdefault(f"decode:{kind}", {})[seed] = agg
            print(f"[{tag:>5} | {seed:<28}] {len(seqs)} seqs, {time.time()-t0:.0f}s elapsed")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=1)
    print(f"[matrix] saved {args.out} ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
