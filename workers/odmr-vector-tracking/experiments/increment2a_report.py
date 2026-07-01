"""Increment-2a headline report: learned tracker vs the classical bar on sequence_sanity_v0.

Evaluates every trained checkpoint under ``artifacts/increment2a/`` (skipping ``*_overfit1``
gate runs) on the REAL test split with the *same* ``evaluation/metrics.py`` pipeline as
``increment1_report.py``, and re-runs the classical lock-in+PID baseline inline for a
side-by-side. Nothing here trains; run ``experiments/increment2a_train.py`` first.

Run from the repo root:  ``python experiments/increment2a_report.py``

Scoring parity notes:
- Learned claimed centers = the state-posterior ``tracked_freqs``; claimed identities are the
  canonical slot axes (``LINE_AXIS_8``), fixed from t=0 — same convention as the classical
  tracker's locks (which additionally get ground-truth initial centers; the learned tracker
  acquires from the spectra alone, a strictly harder condition).
- Primary vector estimate = the model's BLUE-decoded projection regression (``b_est``). A
  secondary cross-check row decodes the learned tracked centers through the *classical*
  splitting→BLUE path, isolating association quality from the regression head.
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
from odmr_vector_tracking.evaluation.metrics import (
    association_accuracy,
    dynamic_range,
    id_switch_rate,
    physical_line_index,
    recovery_time,
    resolve_true_axis,
    vector_angular_error,
)
from odmr_vector_tracking.tracking.classical import ClassicalTracker
from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.vector.blue import blue_invert_field
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8

LOSS_DEG = 5.0  # vector lock deemed "lost" above this angular error (same as Increment 1)


def _row(
    tracked_hz: np.ndarray,
    pred_axis: np.ndarray,
    B_est: np.ndarray,
    ds: SequenceDataset,
    n: int,
    dt: float,
) -> dict | None:
    """One sequence's metric row — identical logic to increment1_report.analyze."""
    ta = resolve_true_axis(tracked_hz, ds.resonance_freqs[n], ds.line_axis[n])
    ae = np.nan_to_num(vector_angular_error(ds.B_true[n], B_est), nan=0.0)
    cf = np.where(ds.collision_mask[n])[0]
    if cf.size == 0:
        return None
    first, last = int(cf.min()), int(cf.max())
    acc = association_accuracy(pred_axis, ta, line_collision=ds.line_collision[n])
    lc = ds.line_collision[n].astype(bool)
    dr = dynamic_range(ds.B_true[n], ae, threshold=LOSS_DEG)
    return dict(
        bmin=float(np.linalg.norm(ds.B_true[n], axis=1).min()),
        bmax=float(np.linalg.norm(ds.B_true[n], axis=1).max()),
        pre=association_accuracy(pred_axis[:first], ta[:first])["overall"],
        post=association_accuracy(pred_axis[last + 1:], ta[last + 1:])["overall"],
        in_coll=acc["in_collision"], out_coll=acc["out_collision"],
        dr=dr["dynamic_range_T"],
        lost=dr["never_lost"] == 0.0,
        rt=recovery_time(ae, dt_s=dt, threshold=LOSS_DEG, onset_index=first),
        idsw=id_switch_rate(physical_line_index(tracked_hz, ds.resonance_freqs[n]))["count"],
        ae_pre=float(ae[:first].mean()), ae_peak=float(ae.max()),
        ae_post=float(ae[last + 1:].mean()),
        incoll_err=float((pred_axis != ta)[lc].mean()) if lc.any() else float("nan"),
    )


def summarize(rows: list[dict], label: str, bias_mag: float) -> None:
    """Increment-1-style metric block over per-sequence rows."""
    N = len(rows)
    lost = sum(r["lost"] for r in rows)
    never_recover = sum(1 for r in rows if r["rt"] == float("inf"))
    med = lambda k: float(np.nanmedian([r[k] for r in rows]))  # noqa: E731
    print(f"\n===== {label}  ({N} sequences w/ crossing) =====")
    print(f"  |B| range         : {med('bmin')*1e3:.2f}..{med('bmax')*1e3:.2f} mT (median)")
    print(f"  assoc accuracy    : pre {med('pre'):.3f} -> post {med('post'):.3f} (median)")
    print(f"  in-collision assoc: {med('in_coll'):.3f}   (out-of-collision {med('out_coll'):.3f})")
    print(f"  ID-switches/seq   : {med('idsw'):.0f} (median) | in-collision ID-switch err {med('incoll_err'):.3f}")
    print(f"  LOSES LOCK        : {lost}/{N} ({100*lost//N if N else 0}%)")
    print(f"  dynamic range     : median {med('dr')*1e3:.2f} mT before irrecoverable loss (at {bias_mag*1e3:.1f} mT bias)")
    print(f"  vector ang err    : pre {med('ae_pre'):.2f} -> peak {med('ae_peak'):.1f} -> post {med('ae_post'):.1f} deg (median)")
    print(f"  recovery time     : never recovers in {never_recover}/{N}")


def analyze_classical(ds: SequenceDataset, m: dict) -> list[dict]:
    trk = ClassicalTracker(ds.frequencies, linewidth_Hz=m["linewidth_Hz"])
    rows = []
    for n in range(ds.spectra.shape[0]):
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        r = _row(res.tracked_freqs, res.pred_axis, res.B_est, ds, n, m["dt_s"])
        if r is not None:
            rows.append(r)
    return rows


def analyze_oracle_association(ds: SequenceDataset, m: dict) -> list[dict]:
    """Ablation: TRUE-label association + classical estimation — the estimation floor.

    Uses the classical detector's peaks but assigns each line-slot the detected peak nearest
    its ground-truth center (falling back to the true center when no peak is in capture
    range), then decodes via splitting→BLUE. Association error is zero by construction, so
    whatever error remains is measurement/estimation error — comparing the trackers against
    this row decomposes association failure from estimation quality.
    """
    trk = ClassicalTracker(ds.frequencies, linewidth_Hz=m["linewidth_Hz"])
    rows = []
    for n in range(ds.spectra.shape[0]):
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
        r = _row(tracked, pred_axis, B_est, ds, n, m["dt_s"])
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
        r = _row(tracked_hz[n], pred_axis, b_est[n], ds, n, m["dt_s"])
        if r is not None:
            rows.append(r)
        # Cross-check: classical splitting->BLUE decode of the learned tracked centers.
        B_x = np.stack(
            [blue_invert_field(tracked_hz[n, t]).b_hat for t in range(tracked_hz.shape[1])]
        )
        rx = _row(tracked_hz[n], pred_axis, B_x, ds, n, m["dt_s"])
        if rx is not None:
            xrows.append(rx)
    return rows, xrows, meta


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-2a report: learned vs classical bar")
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

    summarize(analyze_classical(ds, m), "CLASSICAL lock-in+PID baseline (Increment-1 bar)",
              bias_mag)
    summarize(
        analyze_oracle_association(ds, m),
        "ORACLE association ablation (true-label assignment + splitting→BLUE) — estimation floor",
        bias_mag,
    )

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
        summarize(rows, label, bias_mag)
        summarize(xrows, label + " — splitting→BLUE decode of tracked centers (cross-check)",
                  bias_mag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
