"""Increment-5 dwell-lineage eval — boundary curves + physics-cue exploitation (zero-retrain).

Runs the 3 wave-2 baseline-seed checkpoints (plus CV-KF and NLS references) over the seed-paired
dwell-sweep datasets ``sequence_dwell_v1`` (cues OFF) and ``sequence_dwell_v1_cues`` (per-axis
strain offsets + 3.8 ppm NV-NV cross-relaxation), scored by the shared ``sequence_metrics_row``
path and aggregated per **(dwell D, exit topology) bucket** (24 seqs each; D ∈ {8..192},
cross/bounce). ``b_est`` is untouched by every decode — field metrics are asserted identical
across decodes per seed/rung, and the *cross-dataset* field delta (does the CR dip hurt the
model?) is read from the per-sequence arrays downstream.

Noise ladder: the dwell manifests carry no ``line_depths`` (eval-only); budgets and detector
thresholds reuse the **v1 manifest's** faintest-line depths — same contrast ladder by design
(stated in the output). CR marker threshold = 3x the deepest v1 line (between a 2-line stack
~0.7% and the 1.8% CR dip).

Learned decode variants:
  baseline, physics (A1), stack5 (A3), um2            on BOTH datasets
  cr_gate                                              both (no marker on cues-off -> == physics)
  stack5_strain, cr_gate_strain                        cues dataset only (offsets from manifest)

    python experiments/increment5_dwell_eval.py                       # full (~40 min)
    python experiments/increment5_dwell_eval.py --limit 12 --rungs clean --no-nls   # dry-run
"""

from __future__ import annotations

import argparse
import dataclasses
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
from odmr_vector_tracking.tracking.nls_baseline import NLSTracker  # noqa: E402
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

V1_DIR = _REPO_ROOT / "data" / "sequence_train_v1"
DWELL = {"off": _REPO_ROOT / "data" / "sequence_dwell_v1",
         "cues": _REPO_ROOT / "data" / "sequence_dwell_v1_cues"}
RUNS_DIR = _REPO_ROOT / "artifacts" / "increment2c"
NLS_RUNGS = ("clean", "snr30")  # NLS is the slow reference; ladder tail adds little here

DECODES_BOTH = ("baseline", "physics", "stack5", "um2", "cr_gate")
DECODES_CUES = ("stack5_strain", "cr_gate_strain")


def bucket_labels(h5path: Path) -> list[str]:
    with h5py.File(h5path, "r") as f:
        topo = f["test/exit_topology"][:]
        d = f["test/dwell_frames_target"][:]
    return [f"D{int(dd)}/{'cross' if tt == 0 else 'bounce'}" for dd, tt in zip(d, topo)]


def decode_one(kind: str, s: dict, spectra_n: np.ndarray, freqs: np.ndarray,
               cap_hz: float, lw_hz: float, cr_thresh: float,
               offsets: np.ndarray | None) -> np.ndarray:
    sc, cd, be, tk = s["scores"], s["cand_hz"], s["b_est"], s["track_hz"]
    if kind == "baseline":
        return tk
    if kind == "physics":
        return rd.physics_anchored_decode(be, cd, cap_hz)
    if kind == "stack5":
        return rd.stacked_decode(sc, be, cd, cap_hz, lw_hz, lag=5)
    if kind == "stack5_strain":
        return rd.stacked_decode(sc, be, cd, cap_hz, lw_hz, lag=5, axis_offsets_hz=offsets)
    if kind == "um2":
        return rd.unresolved_merge_decode(sc, be, cd, cap_hz, lw_hz, r_cells=2.0)
    if kind == "cr_gate":
        return rd.cr_gated_decode(spectra_n, freqs, be, cd, cap_hz, lw_hz, cr_thresh)
    if kind == "cr_gate_strain":
        return rd.cr_gated_decode(spectra_n, freqs, be, cd, cap_hz, lw_hz, cr_thresh,
                                  axis_offsets_hz=offsets)
    raise ValueError(kind)


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-5 dwell eval (boundary + cues)")
    ap.add_argument("--out", type=Path,
                    default=_REPO_ROOT / "artifacts" / "noise_matrix" / "matrix_5_dwell.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rungs", nargs="*", default=None)
    ap.add_argument("--no-nls", action="store_true")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | device {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))

    # ladder sized on the v1 manifest (dwell manifests are eval-only, no line_depths;
    # contrast ladder identical by construction)
    mv1 = validate_dataset_dir(V1_DIR)
    v1_depths = np.asarray(mv1["line_depths"], dtype=float)
    faintest = float(v1_depths.min())
    cr_thresh = 3.0 * float(v1_depths.max())
    seeds = list(ir.BASELINE_SEEDS)
    rungs = [(t, s) for t, s in nmr.SNR_RUNGS if args.rungs is None or t in args.rungs]
    budgets = {t: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for t, snr in rungs}

    results = {"noise_master_seed": nmr.NOISE_MASTER_SEED,
               "capture_radius_lw": nmr.CAPTURE_RADIUS_LW,
               "ladder_source": "sequence_train_v1 manifest line_depths (same contrast ladder)",
               "cr_depth_thresh": cr_thresh, "seeds": seeds, "datasets": {}}

    t0 = time.time()
    for dsname, dsdir in DWELL.items():
        m = validate_dataset_dir(dsdir)
        lw_hz = float(m["linewidth_Hz"])
        cap_hz = nmr.CAPTURE_RADIUS_LW * lw_hz
        offsets = (np.asarray(m["axis_offsets_hz"], dtype=float)
                   if m.get("axis_offsets_hz") is not None else None)
        clean = SequenceDatasetLoader(dsdir).load_split("test")
        buckets = bucket_labels(dsdir / "dataset.h5")
        if args.limit:
            clean = dataclasses.replace(clean, spectra=clean.spectra[:args.limit])
            buckets = buckets[:args.limit]
        T = clean.spectra.shape[1]
        pred_axis = np.broadcast_to(LINE_AXIS_8, (T, 8))
        decodes = DECODES_BOTH + (DECODES_CUES if offsets is not None else ())
        dsout = results["datasets"].setdefault(
            dsname, {"dir": dsdir.name, "axis_offsets_hz": m.get("axis_offsets_hz"),
                     "nv_density_ppm": m.get("nv_density_ppm"), "cells": {}})

        for tag, photons in budgets.items():
            ds = nmr.noisy_copy(clean, photons)
            cells = dsout["cells"].setdefault(tag, {})
            # learned, per seed
            for seed in seeds:
                seqs, _ = ir.run_ckpt_outputs(RUNS_DIR / seed / "best.pt", ds, device)
                field_ref = None
                for kind in decodes:
                    rows = []
                    for n, s in enumerate(seqs):
                        tr = decode_one(kind, s, ds.spectra[n], np.asarray(ds.frequencies),
                                        cap_hz, lw_hz, cr_thresh, offsets)
                        rows.append(nmr._row(tr, pred_axis, s["b_est"], ds, n, m))
                    agg = nmr.aggregate(rows, buckets)
                    if field_ref is None:
                        field_ref = {b: (agg[b]["lock_loss"][0], agg[b]["ae_post_all"]) for b in agg}
                    else:  # b_est untouched -> field metrics identical across decodes
                        for b in agg:
                            assert agg[b]["lock_loss"][0] == field_ref[b][0], \
                                f"lock drift {dsname}/{seed}/{tag}/{b}/{kind}"
                            assert np.allclose(np.nan_to_num(agg[b]["ae_post_all"], nan=-1),
                                               np.nan_to_num(field_ref[b][1], nan=-1)), \
                                f"ae_post drift {dsname}/{seed}/{tag}/{b}/{kind}"
                    cells.setdefault(f"decode:{kind}", {})[seed] = agg
                print(f"[{dsname:>4}|{tag:>5}|{seed:<28}] {len(seqs)} seqs "
                      f"{time.time()-t0:.0f}s", flush=True)
            # classical references
            kf_rows = []
            for n in range(ds.spectra.shape[0]):
                trk = KFHungarianTracker(
                    ds.frequencies, linewidth_Hz=m["linewidth_Hz"],
                    peak_min_depth=nmr.detector_depth(ds.spectra[n],
                                                      {**m, "line_depths": v1_depths.tolist()},
                                                      photons))
                res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
                kf_rows.append(nmr._row(res.tracked_freqs.astype(np.float64), res.pred_axis,
                                        res.B_est, ds, n, m))
            cells["kf"] = nmr.aggregate(kf_rows, buckets)
            print(f"[{dsname:>4}|{tag:>5}|{'kf':<28}] {time.time()-t0:.0f}s", flush=True)
            if not args.no_nls and tag in NLS_RUNGS:
                nls_rows = []
                for n in range(ds.spectra.shape[0]):
                    trk = NLSTracker(
                        ds.frequencies,
                        linewidth_Hz=float(m.get("linewidth_rendered_Hz", m["linewidth_Hz"])),
                        line_depths=v1_depths.tolist())
                    res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
                    nls_rows.append(nmr._row(res.tracked_freqs.astype(np.float64),
                                             res.pred_axis, res.B_est, ds, n, m))
                cells["nls"] = nmr.aggregate(nls_rows, buckets)
                print(f"[{dsname:>4}|{tag:>5}|{'nls':<28}] {time.time()-t0:.0f}s", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=1)
    print(f"[matrix] saved {args.out} ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
