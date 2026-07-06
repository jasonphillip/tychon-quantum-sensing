"""Increment-4 overlay-decoder matrix — zero-retrain, standing eval (v1 test).

Runs the 3 wave-2 baseline-seed checkpoints through the SAME noise-matrix harness as increment 2c
(``noise_matrix_report``: identical fixed-seed shot noise, family split, capture radius,
``sequence_metrics_row`` scoring) and applies the coalescence-aware overlay decoders
(``tracking.redecode``) to the saved inference outputs. ``b_est`` is untouched, so every decode
variant shares the baseline's FIELD metrics exactly — the script ASSERTS this each rung/seed.

Decode variants scored per rung x family x seed:
  baseline                         deployed per-slot readout (parity with matrix_2c_redecode)
  bp5, bp15                        D-BP marginal-association, latency 5 / 15 frames
  ov_inst, ov5, ov15, ov_eos       D-OV Set-JPDA identity overlay, {instantaneous, 5, 15, EOS}
  um0.5, um1, um2                  D-UM unresolved-measurement hypotheses, r in {0.5, 1, 2} cells
  jv5, jv15                        D-JV joint fixed-lag Viterbi, latency 5 / 15 frames
  jv15_um                          best composition: D-UM merged states inside D-JV (lag 15)

Writes artifacts/noise_matrix/matrix_4_overlay.json. Verdict: experiments/increment4_verdict.py.

    python experiments/increment4_overlay.py                                   # full (~10 min)
    python experiments/increment4_overlay.py --limit 8 --rungs clean           # dry-run
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

import identity_redecode as ir  # noqa: E402
import noise_matrix_report as nmr  # noqa: E402
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.data.contract import validate_dataset_dir  # noqa: E402
from odmr_vector_tracking.tracking import redecode as rd  # noqa: E402
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
DEFAULT_RUNS_DIR = _REPO_ROOT / "artifacts" / "increment2c"

# latency (frames) each decoder adds — a >15-frame latency is a stated deployment caveat.
LATENCY = {"baseline": 0, "bp5": 5, "bp15": 15, "ov_inst": 0, "ov5": 5, "ov15": 15,
           "ov_eos": None, "um0.5": 0, "um1": 0, "um2": 0, "jv5": 5, "jv15": 15, "jv15_um": 15}
DECODES = tuple(LATENCY.keys())
JV_PENALTY = 1.0  # score-points per linewidth of per-slot movement (single reasonable setting)


def decode_overlay(kind: str, s: dict, cap_hz: float, lw_hz: float, T: int) -> np.ndarray:
    """Return ``tracked_hz (T, 8)`` for one sequence under an overlay-decode variant."""
    sc, cd, be, tk = s["scores"], s["cand_hz"], s["b_est"], s["track_hz"]
    if kind == "baseline":
        return tk
    if kind == "bp5":
        return rd.bp_marginal_decode(sc, cd, lag=5)
    if kind == "bp15":
        return rd.bp_marginal_decode(sc, cd, lag=15)
    if kind == "ov_inst":
        return rd.identity_overlay_decode(sc, be, cd, tk, lw_hz, lag=0)
    if kind == "ov5":
        return rd.identity_overlay_decode(sc, be, cd, tk, lw_hz, lag=5)
    if kind == "ov15":
        return rd.identity_overlay_decode(sc, be, cd, tk, lw_hz, lag=15)
    if kind == "ov_eos":
        return rd.identity_overlay_decode(sc, be, cd, tk, lw_hz, lag=T)  # whole-sequence belief
    if kind == "um0.5":
        return rd.unresolved_merge_decode(sc, be, cd, cap_hz, lw_hz, r_cells=0.5)
    if kind == "um1":
        return rd.unresolved_merge_decode(sc, be, cd, cap_hz, lw_hz, r_cells=1.0)
    if kind == "um2":
        return rd.unresolved_merge_decode(sc, be, cd, cap_hz, lw_hz, r_cells=2.0)
    if kind == "jv5":
        return rd.joint_viterbi_decode(sc, cd, lag=5, penalty=JV_PENALTY, linewidth_hz=lw_hz)
    if kind == "jv15":
        return rd.joint_viterbi_decode(sc, cd, lag=15, penalty=JV_PENALTY, linewidth_hz=lw_hz)
    if kind == "jv15_um":
        return rd.joint_viterbi_decode(sc, cd, lag=15, penalty=JV_PENALTY, linewidth_hz=lw_hz,
                                       merged=True)
    raise ValueError(kind)


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-4 overlay-decoder matrix (zero-retrain)")
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", type=Path,
                    default=_REPO_ROOT / "artifacts" / "noise_matrix" / "matrix_4_overlay.json")
    ap.add_argument("--limit", type=int, default=0, help="cap sequences (dry-run)")
    ap.add_argument("--rungs", nargs="*", default=None, help="subset of rung tags (dry-run)")
    ap.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    ap.add_argument("--seeds", nargs="*", default=None)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | device {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))

    m = validate_dataset_dir(V1_DIR)
    linewidth_hz = float(m["linewidth_Hz"])
    cap_hz = nmr.CAPTURE_RADIUS_LW * linewidth_hz
    ld = SequenceDatasetLoader(V1_DIR)
    clean = ld.load_split(args.split)
    faintest = float(np.min(np.asarray(m["line_depths"])))
    with open(V1_DIR / "manifest.json") as fh:
        fams = json.load(fh)["sequence_stats"][args.split]["trajectory_family_per_sequence"]
    if args.limit:
        clean = dataclasses.replace(clean, spectra=clean.spectra[:args.limit])
        fams = fams[:args.limit]

    rungs = [(t, s) for t, s in nmr.SNR_RUNGS if args.rungs is None or t in args.rungs]
    seeds = list(args.seeds) if args.seeds else list(ir.BASELINE_SEEDS)
    budgets = {t: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for t, snr in rungs}
    T = clean.spectra.shape[1]
    pred_axis = np.broadcast_to(LINE_AXIS_8, (T, 8))
    results = {"noise_master_seed": nmr.NOISE_MASTER_SEED, "capture_radius_lw": nmr.CAPTURE_RADIUS_LW,
               "latency_frames": LATENCY, "jv_penalty": JV_PENALTY, "seeds": list(seeds),
               "decodes": list(DECODES), "cells": {}}

    t0 = time.time()
    for tag, photons in budgets.items():
        ds = nmr.noisy_copy(clean, photons)
        cells = results["cells"].setdefault(tag, {})
        for seed in seeds:
            seqs, _ = ir.run_ckpt_outputs(args.runs_dir / seed / "best.pt", ds, device)
            field_ref = None
            for kind in DECODES:
                rows = [nmr._row(decode_overlay(kind, s, cap_hz, linewidth_hz, T),
                                 pred_axis, s["b_est"], ds, n, m) for n, s in enumerate(seqs)]
                agg = nmr.aggregate(rows, fams)
                if field_ref is None:
                    field_ref = {f: (agg[f]["lock_loss"][0], agg[f]["ae_post_all"]) for f in agg}
                else:  # b_est untouched -> field metrics byte-identical across decodes
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
