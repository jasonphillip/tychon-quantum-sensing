"""Increment-2a corrected report: learned tracker vs HONEST classical baselines (v0).

RE-BASELINE (2026-07-01): the originally published Increment-1 bar was retracted — the
classical detector's default absolute threshold (0.03) exceeded the real data's ~0.4% dip
depth, so it returned zero peaks on every frame and the "baseline" being beaten had never
received a measurement. This report scores every tracker with a data-scaled detection
threshold (:func:`auto_peak_min_depth`) and shared conventions
(:mod:`odmr_vector_tracking.evaluation.rows`): nan-aware angular error (undefined = lost),
capture-radius identity attribution, per-opportunity ID switches, no dynamic-range row.

Trackers compared on the real test split:
- **honest PID** — the Increment-1 lock-in+PID with the fixed detector (GT t=0 init).
- **CV-KF + Hungarian** — the competent classical baseline (GT t=0 init).
- **oracle association** — true-label assignment of detected peaks + splitting→BLUE
  (estimation floor; GT everywhere by construction).
- **learned variants** — every checkpoint under ``artifacts/increment2a/`` (cold spectra
  acquisition — NO ground-truth initialization; a strictly harder condition, stated in each
  caption).

Run from the repo root:  ``python experiments/increment2a_report.py``
"""

from __future__ import annotations

import argparse
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
from odmr_vector_tracking.evaluation.rows import sequence_metrics_row, summarize_rows
from odmr_vector_tracking.tracking.classical import ClassicalTracker, auto_peak_min_depth
from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker
from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.vector.blue import blue_invert_field
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8

CAPTURE_RADIUS_LW = 3.0  # identity attribution radius, in linewidths

GT_INIT_CAPTION = "GT t=0 initialization (well-resolved acquisition assumption)"
COLD_CAPTION = "cold spectra acquisition - NO ground-truth initialization (harder condition)"


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


def analyze_pid(ds: SequenceDataset, m: dict) -> tuple[list[dict], float]:
    """Honest PID rows + mean pre-crossing locked fraction (must be ~1 or the run is void)."""
    rows, locked_pre = [], []
    for n in range(ds.spectra.shape[0]):
        depth = auto_peak_min_depth(ds.spectra[n], line_depths=m.get("line_depths"))
        trk = ClassicalTracker(
            ds.frequencies, linewidth_Hz=m["linewidth_Hz"], peak_min_depth=depth
        )
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        cf = np.where(ds.collision_mask[n])[0]
        if cf.size:
            locked_pre.append(float(res.locked[: cf.min()].mean()) if cf.min() > 0 else 1.0)
        r = _seq_row(res.tracked_freqs, res.pred_axis, res.B_est, ds, n, m)
        if r is not None:
            rows.append(r)
    return rows, float(np.mean(locked_pre)) if locked_pre else float("nan")


def analyze_kf(ds: SequenceDataset, m: dict) -> list[dict]:
    rows = []
    for n in range(ds.spectra.shape[0]):
        depth = auto_peak_min_depth(ds.spectra[n], line_depths=m.get("line_depths"))
        trk = KFHungarianTracker(
            ds.frequencies, linewidth_Hz=m["linewidth_Hz"], peak_min_depth=depth
        )
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        r = _seq_row(res.tracked_freqs, res.pred_axis, res.B_est, ds, n, m)
        if r is not None:
            rows.append(r)
    return rows


def analyze_oracle_association(ds: SequenceDataset, m: dict) -> list[dict]:
    """Ablation: TRUE-label association of detected peaks + splitting→BLUE (estimation floor).

    With the fixed detector this is meaningful: real peaks, perfect association. Whatever
    error remains is measurement/estimation error — comparing trackers against this row
    decomposes association failure from estimation quality.
    """
    rows = []
    for n in range(ds.spectra.shape[0]):
        depth = auto_peak_min_depth(ds.spectra[n], line_depths=m.get("line_depths"))
        trk = ClassicalTracker(
            ds.frequencies, linewidth_Hz=m["linewidth_Hz"], peak_min_depth=depth
        )
        T, L = ds.resonance_freqs[n].shape
        tracked = np.empty((T, L), dtype=np.float64)
        for t in range(T):
            peaks = trk._find_peaks(ds.spectra[n][t])
            for line in range(L):
                gt = float(ds.resonance_freqs[n][t, line])
                if peaks.size:
                    j = int(np.argmin(np.abs(peaks - gt)))
                    near = float(peaks[j])
                    tracked[t, line] = near if abs(near - gt) <= trk.capture_range else gt
                else:
                    tracked[t, line] = gt
        B_est = np.stack([blue_invert_field(tracked[t]).b_hat for t in range(T)])
        pred_axis = np.broadcast_to(LINE_AXIS_8, tracked.shape)
        r = _seq_row(tracked, pred_axis, B_est, ds, n, m)
        if r is not None:
            rows.append(r)
    return rows


def analyze_learned(
    ds: SequenceDataset, m: dict, ckpt_path: Path, device: torch.device
) -> tuple[list[dict], list[dict], dict]:
    """Evaluate one checkpoint → (primary rows, splitting-BLUE cross-check rows, meta)."""
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    cfg = LearnedTrackerConfig(**ck["model_cfg"])
    meta = ck["meta"]
    trk = build_tracker(cfg, core=meta["core"], association=meta["association"]).to(device)
    trk.load_state_dict(ck["model_state"])
    trk.eval()

    f0, f1 = meta["freq_range_Hz"]
    with torch.no_grad():
        out = trk(torch.from_numpy(ds.spectra).float().to(device))
    tracked_hz = out.tracked_freqs.cpu().numpy() * (f1 - f0) + f0   # (N, T, L)
    b_est = out.b_est.cpu().numpy()                                  # (N, T, 3)

    rows, xrows = [], []
    for n in range(ds.spectra.shape[0]):
        pred_axis = np.broadcast_to(LINE_AXIS_8, tracked_hz[n].shape)
        r = _seq_row(tracked_hz[n], pred_axis, b_est[n], ds, n, m)
        if r is not None:
            rows.append(r)
        # Cross-check: classical splitting->BLUE decode of the learned tracked centers.
        B_x = np.stack(
            [blue_invert_field(tracked_hz[n, t]).b_hat for t in range(tracked_hz.shape[1])]
        )
        rx = _seq_row(tracked_hz[n], pred_axis, B_x, ds, n, m)
        if rx is not None:
            xrows.append(rx)
    return rows, xrows, meta


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Increment-2a corrected report: learned vs honest classical baselines"
    )
    ap.add_argument("--dataset", type=Path,
                    default=_REPO_ROOT / "data" / "sequence_sanity_v0")
    ap.add_argument("--runs", type=Path, default=_REPO_ROOT / "artifacts" / "increment2a")
    ap.add_argument("--split", type=str, default="test")
    args = ap.parse_args()

    if not (args.dataset / "manifest.json").exists():
        print(f"real dataset not found at {args.dataset}")
        return 1
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[env] torch {torch.__version__} | eval device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))

    m = validate_dataset_dir(args.dataset)
    ld = SequenceDatasetLoader(args.dataset)
    ds = ld.load_split(args.split)
    bias_mag = float(np.linalg.norm(ld.bias))
    print(f"[data] {args.dataset.name} split='{args.split}' | bias |B| = {bias_mag*1e3:.2f} mT, "
          f"Gamma = {m['linewidth_Hz']/1e6:.2f} MHz, k = {m['collision_threshold_linewidths']}, "
          f"T = {m['n_timesteps']}, F = {m['n_freq_points']}")
    print(f"[conventions] data-scaled detector (auto_peak_min_depth), capture radius "
          f"{CAPTURE_RADIUS_LW:.0f}*Gamma, nan-aware error, per-opportunity ID switches. "
          f"The pre-2026-07-01 published bar is RETRACTED (detector artifact).")

    pid_rows, locked_pre = analyze_pid(ds, m)
    print(f"[detector check] honest-PID mean pre-crossing locked fraction: {locked_pre:.4f}")
    assert locked_pre > 0.9, (
        f"pre-crossing locked fraction {locked_pre:.3f} <= 0.9 — the detector is not seeing "
        f"the data's peaks; results would be the retracted-bar artifact all over again"
    )
    summarize_rows(pid_rows, "HONEST PID (fixed detector) — corrected Increment-1 baseline",
                   GT_INIT_CAPTION)
    summarize_rows(analyze_kf(ds, m), "CV-KF + HUNGARIAN (competent classical baseline)",
                   GT_INIT_CAPTION)
    summarize_rows(analyze_oracle_association(ds, m),
                   "ORACLE association (true-label assignment of detected peaks) — estimation floor",
                   "ground truth by construction")

    ckpts = sorted(
        p / "best.pt"
        for p in args.runs.iterdir()
        if p.is_dir() and (p / "best.pt").exists() and not p.name.endswith("_overfit1")
    ) if args.runs.is_dir() else []
    if not ckpts:
        print(f"\nno trained checkpoints under {args.runs} — run increment2a_train.py first")
        return 1
    for ck in ckpts:
        rows, xrows, meta = analyze_learned(ds, m, ck, device)
        label = f"LEARNED tracker [core={meta['core']}, assoc={meta['association']}]"
        summarize_rows(rows, label, COLD_CAPTION)
        summarize_rows(xrows, label + " — splitting→BLUE decode of tracked centers (cross-check)",
                       COLD_CAPTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
