"""Shot-noise ladder matrix: every tracker x every budget x v0 + v1-per-family (Increment 2b).

The photon-budget ladder is sized against the FAINTEST line of each dataset's manifest:
``photons_for_dip_snr(min(line_depths), snr)`` for SNR_faintest ∈ {30, 10, 3}, plus the
noiseless rung. Noise realizations are **fixed-seed and identical for every tracker**
(seed = master + sequence index), applied with the upstream physics model
(`nv_sensor_sim.physics.shot_noise.apply_shot_noise`).

Tracker conventions (stated per dispatch):
- honest PID and CV-KF share the peak detector; under noise its depth threshold is raised to
  ``max(data-scaled threshold, 5 * sigma_baseline(N))`` — a 5-sigma false-peak guard over
  ~244k (bin, frame) tests/sequence. At SNR_faintest=3 this sits ABOVE the faintest lines'
  depth: they are genuinely undetectable there, and that is reported, not hidden. KF gate/R
  stay at their noiseless tuning (peak-center jitter stays below the measurement-noise prior
  down to SNR_faintest=10).
- NLS has no detection stage (fits the raw spectrum; noise enters the residual) — no tuning.
- Learned checkpoints are evaluated as-is on the same noisy arrays; both noiseless-trained
  and noise-augmented (``*_snr10``) models are included so the augmentation benefit is
  itself measured.

Classical trackers keep GT t=0 init; learned trackers cold-acquire (per-column convention).

Run from the repo root: ``python experiments/noise_matrix_report.py`` (~30 min).
Writes ``artifacts/noise_matrix/matrix.json`` and prints one compact CI line per cell.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from nv_sensor_sim.physics.shot_noise import (
    apply_shot_noise,
    photons_for_dip_snr,
    shot_noise_sigma,
)

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.data.contract import validate_dataset_dir
from odmr_vector_tracking.data.loaders import SequenceDataset
from odmr_vector_tracking.evaluation.metrics import wilson_ci
from odmr_vector_tracking.evaluation.rows import sequence_metrics_row
from odmr_vector_tracking.tracking.classical import ClassicalTracker, auto_peak_min_depth
from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker
from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.tracking.nls_baseline import NLSTracker
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8

CAPTURE_RADIUS_LW = 3.0
SNR_RUNGS: list[tuple[str, float | None]] = [
    ("clean", None), ("snr30", 30.0), ("snr10", 10.0), ("snr3", 3.0),
]
NOISE_MASTER_SEED = 20260702


def noisy_copy(ds: SequenceDataset, photons: float | None) -> SequenceDataset:
    """Fixed-seed noisy realization of a split (identical for every tracker)."""
    if photons is None:
        return ds
    spectra = np.stack([
        apply_shot_noise(ds.spectra[n], photons, seed=NOISE_MASTER_SEED + n)
        for n in range(ds.spectra.shape[0])
    ]).astype(np.float32)
    return dataclasses.replace(ds, spectra=spectra)


def detector_depth(seq_spectra: np.ndarray, m: dict, photons: float | None) -> float:
    base = auto_peak_min_depth(seq_spectra, line_depths=m.get("line_depths"))
    if photons is not None:
        base = max(base, 5.0 * float(shot_noise_sigma(np.array([1.0]), photons)[0]))
    return base


def _row(tracked_hz, pred_axis, B_est, ds: SequenceDataset, n: int, m: dict):
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


def rows_for_tracker(kind: str, ds: SequenceDataset, m: dict,
                     photons: float | None) -> list[dict | None]:
    rows: list[dict | None] = []
    for n in range(ds.spectra.shape[0]):
        if kind == "pid":
            trk = ClassicalTracker(
                ds.frequencies, linewidth_Hz=m["linewidth_Hz"],
                peak_min_depth=detector_depth(ds.spectra[n], m, photons),
            )
        elif kind == "kf":
            trk = KFHungarianTracker(
                ds.frequencies, linewidth_Hz=m["linewidth_Hz"],
                peak_min_depth=detector_depth(ds.spectra[n], m, photons),
            )
        else:  # nls
            trk = NLSTracker(
                ds.frequencies,
                linewidth_Hz=float(m.get("linewidth_rendered_Hz", m["linewidth_Hz"])),
                line_depths=m.get("line_depths"),
            )
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        rows.append(_row(res.tracked_freqs.astype(np.float64), res.pred_axis, res.B_est,
                         ds, n, m))
    return rows


def rows_for_ckpt(ckpt: Path, ds: SequenceDataset, m: dict,
                  device: torch.device) -> tuple[list[dict | None], str]:
    ck = torch.load(ckpt, map_location=device, weights_only=False)
    cfg = LearnedTrackerConfig(**ck["model_cfg"])
    meta = ck["meta"]
    trk = build_tracker(cfg, core=meta["core"], association=meta["association"]).to(device)
    trk.load_state_dict(ck["model_state"])
    trk.eval()
    f0, f1 = meta["freq_range_Hz"]
    outs = []
    with torch.no_grad():
        for lo in range(0, ds.spectra.shape[0], 32):
            outs.append(trk(torch.from_numpy(ds.spectra[lo:lo + 32]).float().to(device)))
    tracked = np.concatenate([o.tracked_freqs.cpu().numpy() for o in outs]) * (f1 - f0) + f0
    b_est = np.concatenate([o.b_est.cpu().numpy() for o in outs])
    rows: list[dict | None] = []
    for n in range(ds.spectra.shape[0]):
        pred_axis = np.broadcast_to(LINE_AXIS_8, tracked[n].shape)
        rows.append(_row(tracked[n], pred_axis, b_est[n], ds, n, m))
    aug = "" if meta.get("noise_photons") is None else "+aug"
    return rows, f"learned-{meta['core']}+{meta['association']}{aug}"


def aggregate(rows: list[dict | None], families: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fam in sorted(set(families)):
        fr = [r for r, f in zip(rows, families) if f == fam and r is not None]
        if not fr:
            continue
        mis = sum(r["in_coll_wrong"] for r in fr)
        n_ic = sum(r["in_coll_n"] for r in fr)
        sw = sum(r["idsw_opp_switches"] for r in fr)
        op = sum(r["idsw_opp_n"] for r in fr)
        lost = sum(r["lost"] for r in fr)
        out[fam] = {
            "n_seq": len(fr),
            "misassoc": [mis, n_ic, *wilson_ci(mis, n_ic)],
            "idsw_opp": [sw, op, *wilson_ci(sw, op)],
            "lock_loss": [lost, len(fr), *wilson_ci(lost, len(fr))],
            "ae_peak_med": float(np.nanmedian([r["ae_peak"] for r in fr])),
            "ae_post_med": float(np.nanmedian([r["ae_post"] for r in fr])),
        }
    return out


def print_cells(ds_name: str, rung: str, tracker: str, agg: dict[str, dict]) -> None:
    for fam, a in agg.items():
        mis = a["misassoc"]; sw = a["idsw_opp"]; ll = a["lock_loss"]
        mis_p = mis[0] / mis[1] if mis[1] else float("nan")
        sw_p = sw[0] / sw[1] if sw[1] else float("nan")
        print(f"[{ds_name}|{rung:>5}|{tracker:<28}|{fam:<8}] "
              f"misassoc {mis_p:.3f} ({mis[2]:.3f}-{mis[3]:.3f}) | "
              f"sw/opp {sw_p:.3f} ({sw[2]:.3f}-{sw[3]:.3f}) | "
              f"loss {ll[0]:.0f}/{ll[1]:.0f} | "
              f"ae peak/post {a['ae_peak_med']:.1f}/{a['ae_post_med']:.1f} deg")


def main() -> int:
    ap = argparse.ArgumentParser(description="Shot-noise ladder matrix (Increment 2b/2c)")
    ap.add_argument("--split", type=str, default="test")
    ap.add_argument("--out", type=Path,
                    default=_REPO_ROOT / "artifacts" / "noise_matrix" / "matrix.json")
    # Checkpoint-discovery overrides (eval semantics — dataset, split, ladder, seeds, metrics —
    # are unchanged; only WHICH trained checkpoints are scored moves). 2c trains on v2 but the
    # standing eval stays on the v1 test set: `--only v1 --v1-runs artifacts/increment2c`.
    ap.add_argument("--only", choices=("v0", "v1", "both"), default="both",
                    help="restrict the eval to one dataset (default both)")
    ap.add_argument("--v0-runs", type=Path, default=_REPO_ROOT / "artifacts" / "increment2a",
                    help="checkpoint dir discovered for the v0 eval")
    ap.add_argument("--v1-runs", type=Path, default=_REPO_ROOT / "artifacts" / "increment2b",
                    help="checkpoint dir discovered for the v1 eval (2c: artifacts/increment2c)")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | eval device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))

    all_datasets = [
        ("v0", _REPO_ROOT / "data" / "sequence_sanity_v0", args.v0_runs),
        ("v1", _REPO_ROOT / "data" / "sequence_train_v1", args.v1_runs),
    ]
    datasets = [d for d in all_datasets if args.only in ("both", d[0])]
    results: dict = {"noise_master_seed": NOISE_MASTER_SEED, "capture_radius_lw":
                     CAPTURE_RADIUS_LW, "datasets": {}}

    for ds_name, ds_dir, runs_dir in datasets:
        if not (ds_dir / "manifest.json").exists():
            print(f"[skip] {ds_name}: not found at {ds_dir}")
            continue
        m = validate_dataset_dir(ds_dir)
        ld = SequenceDatasetLoader(ds_dir)
        clean = ld.load_split(args.split)
        faintest = float(np.min(np.asarray(m["line_depths"])))
        try:
            with open(ds_dir / "manifest.json") as fh:
                fams = json.load(fh)["sequence_stats"][args.split][
                    "trajectory_family_per_sequence"]
        except KeyError:
            fams = ["all"] * clean.spectra.shape[0]
        ckpts = sorted(
            p / "best.pt" for p in runs_dir.iterdir()
            if p.is_dir() and (p / "best.pt").exists() and not p.name.endswith("_overfit1")
        ) if runs_dir.is_dir() else []

        budgets = {tag: (None if snr is None else float(photons_for_dip_snr(faintest, snr)))
                   for tag, snr in SNR_RUNGS}
        print(f"\n===== {ds_name} ({ds_dir.name}, split='{args.split}', faintest line depth "
              f"{faintest:.5f}) =====")
        print("  ladder photons/point: "
              + ", ".join(f"{t}={'-' if n is None else f'{n:.2e}'}"
                          for t, n in budgets.items()))
        results["datasets"][ds_name] = {"budgets": budgets, "cells": {}}

        for tag, photons in budgets.items():
            ds = noisy_copy(clean, photons)
            if photons is not None:
                thr = detector_depth(ds.spectra[0], m, photons)
                print(f"  [{tag}] detector depth threshold (seq 0): {thr:.5f} "
                      f"(faintest nominal {faintest:.5f}"
                      f"{' — faintest lines UNDETECTABLE' if thr > faintest else ''})")
            cells = results["datasets"][ds_name]["cells"].setdefault(tag, {})
            for kind in ("pid", "kf", "nls"):
                agg = aggregate(rows_for_tracker(kind, ds, m, photons), fams)
                cells[kind] = agg
                print_cells(ds_name, tag, kind, agg)
            for ckpt in ckpts:
                rows, label = rows_for_ckpt(ckpt, ds, m, device)
                # run-dir name disambiguates same-arch ckpts (e.g. _snr10 twins)
                label = f"{label}[{ckpt.parent.name}]"
                agg = aggregate(rows, fams)
                cells[label] = agg
                print_cells(ds_name, tag, label, agg)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=1)
    print(f"\n[matrix] saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
