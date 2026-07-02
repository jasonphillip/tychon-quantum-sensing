"""Increment-2b report: per-family evaluation on sequence_train_v1 with binomial CIs.

Evaluates honest PID, CV-KF + Hungarian, and every learned checkpoint under
``artifacts/increment2b/`` on the v1 test split (128 seqs × T=256), broken down by
trajectory family (``held`` hold-ramp-hold / ``reversal`` / ``ou``) from the manifest's
``sequence_stats``. All trackers share the conventions of
:mod:`odmr_vector_tracking.evaluation.rows` (data-scaled detector via manifest
``line_depths``, capture-radius attribution, nan-aware error, per-opportunity ID switches).

The decisive discrimination lives on the REVERSAL family: a field reversal inside or near a
collision dwell breaks the constant-velocity coast assumption, so in-collision association
and ID-switches-per-opportunity there separate trackers that v0 (kinematically trivial linear
ramps) cannot.

95% Wilson CIs: in-collision misassociation and ID switches are pooled over (frame, line) /
(event, lock) counts across a family — entries within a sequence are correlated, so treat the
intervals as indicative rather than exact. Lock-loss is per-sequence (independent).

Run from the repo root:  ``python experiments/increment2b_report.py``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.data.contract import validate_dataset_dir
from odmr_vector_tracking.data.loaders import SequenceDataset
from odmr_vector_tracking.evaluation.metrics import wilson_ci
from odmr_vector_tracking.evaluation.rows import sequence_metrics_row, summarize_rows
from odmr_vector_tracking.tracking.classical import ClassicalTracker, auto_peak_min_depth
from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker
from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8

CAPTURE_RADIUS_LW = 3.0
GT_INIT_CAPTION = "GT t=0 initialization"
COLD_CAPTION = "cold spectra acquisition - NO ground-truth initialization (harder condition)"
FAMILIES = ("held", "reversal", "ou")


def _seq_row(tracked_hz, pred_axis, B_est, ds: SequenceDataset, n: int, m: dict):
    return sequence_metrics_row(
        tracked_hz, pred_axis, B_est,
        resonance_freqs=ds.resonance_freqs[n],
        line_axis=ds.line_axis[n],
        line_collision=ds.line_collision[n],
        collision_mask=ds.collision_mask[n],
        B_true=ds.B_true[n],
        dt_s=float(m["dt_s"]),
        capture_radius_hz=CAPTURE_RADIUS_LW * float(m["linewidth_Hz"]),
    )


def rows_classical(ds: SequenceDataset, m: dict, kind: str) -> list[dict | None]:
    """Per-sequence rows (None where no crossing) for 'pid' or 'kf'."""
    out: list[dict | None] = []
    for n in range(ds.spectra.shape[0]):
        depth = auto_peak_min_depth(ds.spectra[n], line_depths=m.get("line_depths"))
        if kind == "pid":
            trk = ClassicalTracker(
                ds.frequencies, linewidth_Hz=m["linewidth_Hz"], peak_min_depth=depth
            )
        else:
            trk = KFHungarianTracker(
                ds.frequencies, linewidth_Hz=m["linewidth_Hz"], peak_min_depth=depth
            )
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        out.append(_seq_row(res.tracked_freqs, res.pred_axis, res.B_est, ds, n, m))
    return out


def rows_learned(
    ds: SequenceDataset, m: dict, ckpt_path: Path, device: torch.device
) -> tuple[list[dict | None], dict]:
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    cfg = LearnedTrackerConfig(**ck["model_cfg"])
    meta = ck["meta"]
    trk = build_tracker(cfg, core=meta["core"], association=meta["association"]).to(device)
    trk.load_state_dict(ck["model_state"])
    trk.eval()
    f0, f1 = meta["freq_range_Hz"]
    outs = []
    with torch.no_grad():
        for lo in range(0, ds.spectra.shape[0], 32):  # chunked eval keeps memory flat
            batch = torch.from_numpy(ds.spectra[lo:lo + 32]).float().to(device)
            outs.append(trk(batch))
    tracked_hz = np.concatenate(
        [o.tracked_freqs.cpu().numpy() for o in outs]) * (f1 - f0) + f0
    b_est = np.concatenate([o.b_est.cpu().numpy() for o in outs])
    rows: list[dict | None] = []
    for n in range(ds.spectra.shape[0]):
        pred_axis = np.broadcast_to(LINE_AXIS_8, tracked_hz[n].shape)
        rows.append(_seq_row(tracked_hz[n], pred_axis, b_est[n], ds, n, m))
    return rows, meta


def family_report(
    label: str, caption: str, rows: list[dict | None], families: list[str]
) -> dict:
    """Print per-family blocks + pooled CI lines; return the decisive numbers per family."""
    decisive: dict = {}
    print(f"\n################ {label} ################")
    for fam in FAMILIES:
        fam_rows = [r for r, f in zip(rows, families) if f == fam and r is not None]
        n_total = sum(1 for f in families if f == fam)
        summarize_rows(
            fam_rows,
            f"{label} — family: {fam} ({len(fam_rows)}/{n_total} seqs w/ crossing)",
            caption,
        )
        if not fam_rows:
            continue
        mis = sum(r["in_coll_wrong"] for r in fam_rows)
        n_ic = sum(r["in_coll_n"] for r in fam_rows)
        sw = sum(r["idsw_opp_switches"] for r in fam_rows)
        op = sum(r["idsw_opp_n"] for r in fam_rows)
        lost = sum(r["lost"] for r in fam_rows)
        ci_mis = wilson_ci(mis, n_ic)
        ci_sw = wilson_ci(sw, op)
        ci_lost = wilson_ci(lost, len(fam_rows))
        print(f"  [CI95] in-coll misassoc {mis}/{n_ic} = "
              f"{mis / n_ic if n_ic else float('nan'):.3f} ({ci_mis[0]:.3f}-{ci_mis[1]:.3f}) | "
              f"ID-sw/opp {sw:.0f}/{op:.0f} = {sw / op if op else float('nan'):.3f} "
              f"({ci_sw[0]:.3f}-{ci_sw[1]:.3f}) | "
              f"lock-loss {lost}/{len(fam_rows)} ({ci_lost[0]:.2f}-{ci_lost[1]:.2f})")
        decisive[fam] = {
            "in_coll_misassoc": (mis, n_ic, ci_mis),
            "idsw_per_opp": (sw, op, ci_sw),
            "lock_loss": (lost, len(fam_rows), ci_lost),
        }
    return decisive


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-2b per-family v1 report")
    ap.add_argument("--dataset", type=Path, default=_REPO_ROOT / "data" / "sequence_train_v1")
    ap.add_argument("--runs", type=Path, default=_REPO_ROOT / "artifacts" / "increment2b")
    ap.add_argument("--split", type=str, default="test")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | eval device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))
    m = validate_dataset_dir(args.dataset)
    with open(args.dataset / "manifest.json") as fh:
        stats = json.load(fh)["sequence_stats"][args.split]
    families = list(stats["trajectory_family_per_sequence"])
    n_rev_in_dwell = stats.get("n_reversals_inside_collision_dwell")
    ld = SequenceDatasetLoader(args.dataset)
    ds = ld.load_split(args.split)
    print(f"[data] {args.dataset.name} split='{args.split}': {ds.spectra.shape[0]} seqs x "
          f"T={m['n_timesteps']} | families: "
          + ", ".join(f"{fam}={families.count(fam)}" for fam in FAMILIES)
          + f" | reversals inside collision dwell: {n_rev_in_dwell}")
    print(f"[conventions] detector scaled from manifest line_depths; capture radius "
          f"{CAPTURE_RADIUS_LW:.0f}*Gamma; nan-aware error; per-opportunity ID switches; "
          f"CIs are 95% Wilson (pooled counts — indicative, entries within a sequence "
          f"correlate). v0 remains the frozen sanity lineage.")

    family_report("HONEST PID (fixed detector)", GT_INIT_CAPTION,
                  rows_classical(ds, m, "pid"), families)
    family_report("CV-KF + HUNGARIAN", GT_INIT_CAPTION,
                  rows_classical(ds, m, "kf"), families)

    ckpts = sorted(
        p / "best.pt"
        for p in args.runs.iterdir()
        if p.is_dir() and (p / "best.pt").exists() and not p.name.endswith("_overfit1")
    ) if args.runs.is_dir() else []
    if not ckpts:
        print(f"\nno trained checkpoints under {args.runs} — train on v1 first")
        return 1
    for ck in ckpts:
        rows, meta = rows_learned(ds, m, ck, device)
        family_report(
            f"LEARNED [core={meta['core']}, assoc={meta['association']}]",
            COLD_CAPTION, rows, families,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
