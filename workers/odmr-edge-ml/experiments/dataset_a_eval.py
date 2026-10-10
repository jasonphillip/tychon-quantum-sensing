#!/usr/bin/env python3
"""FCNN v1 evaluation on Dataset A (production_50k_v2_aic) test split.

Dataset A is generated with shift_test_ranges=True (manifest key:
inverse_crime_shift): the test split's corruption ranges (P1, T, B1_grad)
are shifted out of training distribution. Train/val splits are
bit-identical to production_50k.

This script runs PID baseline + FCNN v1 on Dataset A's test split, then
compares MAE reduction against production_50k's test split (in-distribution
corruption). If reduction degrades >5 pp, the script slices the result
by P1, T, B1_grad to identify which corruption regime breaks first.

No retraining — same FCNN v1 checkpoint, same architecture, same env.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import h5py
import numpy as np
import torch

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID  # noqa: E402
from odmr_edge_ml.models.fcnn import OdmrFCNN  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

DS_PROD = Path("~/projects/odmr-edge-ml/data/production_50k/dataset.h5")
PID_PROD = Path("~/projects/odmr-edge-ml/data/production_50k/pid_residuals.npz")
DS_AIC = Path(
    "~/projects/tychon-shared-data/production_50k_v2_aic/dataset.h5"
)
CKPT = Path(
    "~/Desktop/Shared/codex-review/ws1_projects/"
    "tychon-odmr-ml/experiments/scalar_residual/fcnn/checkpoints/best_model.pt"
)
OUT_NPZ = Path(__file__).resolve().parent / "dataset_a_eval_results.npz"

ANCHOR_SIGMA = 1.5
DEGRADATION_THRESHOLD_PP = 5.0


def load_fcnn(ckpt_path: Path) -> OdmrFCNN:
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    sd = ckpt["model_state_dict"]
    skip = ("fake_quant", "activation_post_process", "observer")
    clean_sd = {k: v for k, v in sd.items() if not any(p in k for p in skip)}
    model = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    model.load_state_dict(clean_sd, strict=True)
    model.eval()
    return model.to(DEVICE)


def preprocess_batch(spectra: np.ndarray, lock_bins: np.ndarray) -> torch.Tensor:
    s_min = spectra.min(axis=1, keepdims=True)
    s_max = spectra.max(axis=1, keepdims=True)
    denom = np.where(s_max == s_min, 1.0, s_max - s_min)
    spec_norm = 2.0 * (spectra - s_min) / denom - 1.0
    n, k = spectra.shape
    bins = np.arange(k)[None, :]
    anchor = np.exp(-0.5 * ((bins - lock_bins[:, None]) / ANCHOR_SIGMA) ** 2)
    combined = np.concatenate([spec_norm, anchor], axis=1)
    return torch.from_numpy(combined).float().to(DEVICE)


def run_pid_batch(
    frequencies: np.ndarray, spectra: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (b_pid_uT, lock_bins, n_dips)."""
    pid = DerivativeZeroCrossingPID(frequencies)
    n = spectra.shape[0]
    b_pid = np.zeros(n)
    lb = np.zeros(n, dtype=np.int64)
    nd = np.zeros(n, dtype=np.int64)
    for i in range(n):
        r = pid.estimate(spectra[i])
        b_pid[i] = r.b_mag_uT
        lb[i] = r.lock_bin
        nd[i] = r.n_dips
    return b_pid, lb, nd


def fcnn_correct(
    fcnn: OdmrFCNN, spectra: np.ndarray, lock_bins: np.ndarray
) -> np.ndarray:
    x = preprocess_batch(spectra, lock_bins)
    with torch.no_grad():
        d = fcnn(x).detach().cpu().numpy().reshape(-1)
    return d


def stats_block(label: str, pid_err: np.ndarray, fcnn_err: np.ndarray) -> dict:
    mae_pid = float(pid_err.mean())
    mae_fcnn = float(fcnn_err.mean())
    red = (1.0 - mae_fcnn / mae_pid) * 100.0
    log.info(
        "  %-32s n=%5d  MAE_PID=%7.3f  MAE_FCNN=%7.3f  reduction=%6.2f%%",
        label, pid_err.size, mae_pid, mae_fcnn, red,
    )
    return {
        "n": int(pid_err.size),
        "mae_pid": mae_pid,
        "mae_fcnn": mae_fcnn,
        "reduction_pct": red,
        "median_pid": float(np.median(pid_err)),
        "P90_pid": float(np.percentile(pid_err, 90)),
        "P99_pid": float(np.percentile(pid_err, 99)),
        "median_fcnn": float(np.median(fcnn_err)),
        "P90_fcnn": float(np.percentile(fcnn_err, 90)),
        "P99_fcnn": float(np.percentile(fcnn_err, 99)),
    }


def slice_by(
    name: str,
    values: np.ndarray,
    pid_err: np.ndarray,
    fcnn_err: np.ndarray,
    edges: np.ndarray,
) -> list[dict]:
    bin_idx = np.digitize(values, edges) - 1
    bin_idx = np.clip(bin_idx, 0, len(edges) - 2)
    rows = []
    log.info("  --- slice by %s (edges=%s) ---", name, edges.tolist())
    log.info(
        "    %-15s %6s %10s %10s %10s",
        "bin range", "n", "MAE_PID", "MAE_FCNN", "reduction%",
    )
    for b in range(len(edges) - 1):
        sel = bin_idx == b
        n = int(sel.sum())
        if n < 5:
            log.info("    [%6.3f, %6.3f) n=%4d (skipped, low n)",
                     edges[b], edges[b + 1], n)
            rows.append({
                "name": name, "bin_lo": float(edges[b]), "bin_hi": float(edges[b + 1]),
                "n": n, "mae_pid": float("nan"), "mae_fcnn": float("nan"),
                "reduction_pct": float("nan"),
            })
            continue
        mae_p = float(pid_err[sel].mean())
        mae_f = float(fcnn_err[sel].mean())
        red = (1.0 - mae_f / mae_p) * 100.0
        log.info(
            "    [%6.3f, %6.3f) n=%4d  %10.3f %10.3f %9.2f%%",
            edges[b], edges[b + 1], n, mae_p, mae_f, red,
        )
        rows.append({
            "name": name, "bin_lo": float(edges[b]), "bin_hi": float(edges[b + 1]),
            "n": n, "mae_pid": mae_p, "mae_fcnn": mae_f, "reduction_pct": red,
        })
    return rows


def main() -> None:
    if not CKPT.exists():
        log.error("FCNN checkpoint not found: %s", CKPT)
        sys.exit(1)

    fcnn = load_fcnn(CKPT)
    log.info("FCNN v1 loaded: %d params", sum(p.numel() for p in fcnn.parameters()))

    # --- production_50k test split: PID is precomputed in pid_residuals.npz ---
    log.info("")
    log.info("Loading production_50k test split (in-distribution)")
    with h5py.File(DS_PROD, "r") as h:
        prod_spectra = h["test/spectra"][:]
        prod_cp = h["test/corruption_params"][:]
    pid_pre = np.load(PID_PROD)
    prod_b_pid = pid_pre["test_b_pid_uT"]
    prod_b_true = pid_pre["test_b_mag_uT"]
    prod_lockbins = pid_pre["test_lock_bins"].astype(np.int64)

    prod_delta = fcnn_correct(fcnn, prod_spectra, prod_lockbins)
    prod_pid_err = np.abs(prod_b_pid - prod_b_true)
    prod_fcnn_err = np.abs(prod_b_pid + prod_delta - prod_b_true)

    log.info("=== production_50k test split (in-distribution) ===")
    prod_stats = stats_block("production_50k test", prod_pid_err, prod_fcnn_err)

    # --- Dataset A test split: shifted corruption, PID computed fresh ---
    log.info("")
    log.info("Loading Dataset A (production_50k_v2_aic) test split")
    with h5py.File(DS_AIC, "r") as h:
        aic_spectra = h["test/spectra"][:]
        aic_cp = h["test/corruption_params"][:]
        aic_labels = h["test/labels"][:]
        aic_freq = h["test/frequencies"][:]
    aic_b_true = np.linalg.norm(aic_labels, axis=1) * 1e6  # T → µT

    log.info("  Running PID baseline on %d AIC test spectra…", aic_spectra.shape[0])
    aic_b_pid, aic_lockbins, aic_ndips = run_pid_batch(aic_freq, aic_spectra)

    aic_delta = fcnn_correct(fcnn, aic_spectra, aic_lockbins)
    aic_pid_err = np.abs(aic_b_pid - aic_b_true)
    aic_fcnn_err = np.abs(aic_b_pid + aic_delta - aic_b_true)

    log.info("=== Dataset A test split (AIC-shifted) ===")
    aic_stats = stats_block("Dataset A test (AIC)", aic_pid_err, aic_fcnn_err)

    # --- Compare ---
    delta_red = aic_stats["reduction_pct"] - prod_stats["reduction_pct"]
    log.info("")
    log.info("=== Headline comparison ===")
    log.info("  production_50k test reduction:  %.2f%%", prod_stats["reduction_pct"])
    log.info("  Dataset A test reduction:       %.2f%%", aic_stats["reduction_pct"])
    log.info("  Δ reduction (AIC − prod):       %+.2f pp", delta_red)
    log.info("  v1 training-headline reference: 54.27%% (full val from prior task)")

    degraded = delta_red < -DEGRADATION_THRESHOLD_PP
    log.info("  Degraded by >%g pp?  %s", DEGRADATION_THRESHOLD_PP, degraded)

    # --- Always report regime slicing on AIC; flag if degraded ---
    log.info("")
    log.info("=== Dataset A AIC test split sliced by corruption regime ===")
    aic_p1 = aic_cp[:, 0]
    aic_T = aic_cp[:, 1]
    aic_b1g = aic_cp[:, 2]

    p1_edges = np.array([0.0, 50.0, 100.0, 200.0, 300.0, 400.0])
    T_edges = np.array([280.0, 290.0, 295.0, 300.0, 305.0, 310.0])
    b1g_edges = np.array([0.05, 0.10, 0.15, 0.20, 0.25, 0.35])

    p1_rows = slice_by("P1_ppm", aic_p1, aic_pid_err, aic_fcnn_err, p1_edges)
    T_rows = slice_by("T_K", aic_T, aic_pid_err, aic_fcnn_err, T_edges)
    b1g_rows = slice_by("B1_grad", aic_b1g, aic_pid_err, aic_fcnn_err, b1g_edges)

    # Worst-degradation regime
    worst = min(p1_rows + T_rows + b1g_rows,
                key=lambda r: r["reduction_pct"] if not np.isnan(r["reduction_pct"]) else np.inf)
    log.info("")
    log.info("  WORST regime in AIC: %s [%.3f, %.3f)  n=%d  reduction=%.2f%%",
             worst["name"], worst["bin_lo"], worst["bin_hi"],
             worst["n"], worst["reduction_pct"])

    # --- Save ---
    out: dict[str, np.ndarray] = {}
    for k, v in prod_stats.items():
        out[f"prod_{k}"] = np.asarray(v)
    for k, v in aic_stats.items():
        out[f"aic_{k}"] = np.asarray(v)
    out["aic_pid_err_uT"] = aic_pid_err
    out["aic_fcnn_err_uT"] = aic_fcnn_err
    out["aic_b_pid_uT"] = aic_b_pid
    out["aic_b_true_uT"] = aic_b_true
    out["aic_delta_pred_uT"] = aic_delta
    out["aic_lock_bins"] = aic_lockbins
    out["aic_n_dips"] = aic_ndips
    out["aic_corruption_params"] = aic_cp
    out["prod_pid_err_uT"] = prod_pid_err
    out["prod_fcnn_err_uT"] = prod_fcnn_err
    out["prod_corruption_params"] = prod_cp
    out["delta_reduction_pp"] = np.asarray(delta_red)
    # Slice tables stored as structured arrays
    def to_arr(rows):
        if not rows:
            return np.zeros(0)
        return np.array(
            [(r["name"], r["bin_lo"], r["bin_hi"], r["n"], r["mae_pid"],
              r["mae_fcnn"], r["reduction_pct"]) for r in rows],
            dtype=[("name", "U16"), ("bin_lo", "f8"), ("bin_hi", "f8"),
                   ("n", "i8"), ("mae_pid", "f8"), ("mae_fcnn", "f8"),
                   ("reduction_pct", "f8")],
        )
    out["slice_p1"] = to_arr(p1_rows)
    out["slice_T"] = to_arr(T_rows)
    out["slice_b1g"] = to_arr(b1g_rows)
    np.savez(str(OUT_NPZ), **out)
    log.info("Saved: %s", OUT_NPZ)


if __name__ == "__main__":
    main()
