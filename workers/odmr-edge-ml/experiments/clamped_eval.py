#!/usr/bin/env python3
"""Clamped vs unclamped FCNN+PID evaluation on val + heading sweep.

Existing eval scripts (heading_sweep.py, validation_orientation_audit.py,
orientation_binned_comparison.py) do NOT apply the ±2.25 µT sector clamp
on FCNN output before adding to PID. The clamp lives in Repo 3 HLS as the
sector_clamp safety chain stage. Source of clamp value:
  experiments/scalar_residual_v2.py:53-57
    # Sector clamp: ±4.5% of 50 µT deployment field.
    CLAMP_UT = 2.25
And the position is pre-PID-add (clip u_AI first, THEN sum with u_pid):
  experiments/scalar_residual_v2.py:372
    fcnn_delta_b_uT[i] = np.clip(delta_b, -CLAMP_UT, CLAMP_UT)

This script applies that clamp on top of the existing FCNN v1 outputs and
re-derives val and heading-sweep MAE reductions, plus the per-θ-bin
breakdown. The unclamped path is the same logic with the clamp removed,
for side-by-side reporting. The existing unclamped scripts are not
modified.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from odmr_edge_ml.models.fcnn import OdmrFCNN  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

DATASET_H5 = Path("~/projects/odmr-edge-ml/data/production_50k/dataset.h5")
PID_NPZ = Path("~/projects/odmr-edge-ml/data/production_50k/pid_residuals.npz")
SWEEP_NPZ = Path(
    "~/shared/codex-review/ws1_projects/"
    "tychon-odmr-ml/experiments/heading_sweep_results.npz"
)
CKPT = Path(
    "~/shared/codex-review/ws1_projects/"
    "tychon-odmr-ml/experiments/scalar_residual/fcnn/checkpoints/best_model.pt"
)
OUT_NPZ = Path(__file__).resolve().parent / "clamped_eval_results.npz"
OUT_PNG = (
    Path(__file__).resolve().parent / "figures" / "orientation_binned_comparison_clamped.png"
)

# Source: experiments/scalar_residual_v2.py:53-57 ("Sector clamp: ±4.5% of 50 µT deployment field")
CLAMP_UT = 2.25
ANCHOR_SIGMA = 1.5
N_BINS = 10
LOW_N_THRESH = 20


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


def polar_theta(b_vec: np.ndarray) -> np.ndarray:
    bmag = np.linalg.norm(b_vec, axis=1)
    bz = b_vec[:, 2]
    return np.arccos(np.clip(bz / np.where(bmag == 0, 1.0, bmag), -1.0, 1.0))


def per_bin_mean(theta: np.ndarray, err: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    bin_idx = np.digitize(theta, edges) - 1
    bin_idx = np.clip(bin_idx, 0, len(edges) - 2)
    n_b = len(edges) - 1
    means = np.full(n_b, np.nan)
    counts = np.zeros(n_b, dtype=int)
    for b in range(n_b):
        sel = bin_idx == b
        counts[b] = int(sel.sum())
        if counts[b] > 0:
            means[b] = float(err[sel].mean())
    return means, counts


def headline(label: str, pid_err: np.ndarray, fcnn_err: np.ndarray) -> dict:
    mae_pid = float(pid_err.mean())
    mae_fcnn = float(fcnn_err.mean())
    red = (1.0 - mae_fcnn / mae_pid) * 100.0
    log.info("  %-30s n=%5d  MAE_PID=%7.3f  MAE_FCNN=%7.3f  reduction=%6.2f%%",
             label, pid_err.size, mae_pid, mae_fcnn, red)
    return {"n": int(pid_err.size), "mae_pid": mae_pid,
            "mae_fcnn": mae_fcnn, "reduction_pct": red}


def main() -> None:
    if not CKPT.exists():
        log.error("FCNN checkpoint not found: %s", CKPT)
        sys.exit(1)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)

    log.info("Existing eval scripts apply clamp? NO")
    log.info("  Verified: heading_sweep.py:200 — `delta_b = fcnn(x).item()` then "
             "`fcnn_delta_b_uT[i] = delta_b` (no clip)")
    log.info("  Clamp value: ±%.2f µT (source: experiments/scalar_residual_v2.py:53-57)", CLAMP_UT)
    log.info("  Clamp position: pre-PID-add — clip u_AI first, THEN sum with u_pid")
    log.info("  (source: experiments/scalar_residual_v2.py:372)")

    fcnn = load_fcnn(CKPT)
    log.info("FCNN v1 loaded: %d params", sum(p.numel() for p in fcnn.parameters()))

    # --- Validation eval ---
    log.info("")
    log.info("Loading val data")
    with h5py.File(DATASET_H5, "r") as h:
        val_spectra = h["val/spectra"][:]
        val_labels = h["val/labels"][:]
    pid_pre = np.load(PID_NPZ)
    val_b_pid = pid_pre["val_b_pid_uT"]
    val_b_true = pid_pre["val_b_mag_uT"]
    val_lockbins = pid_pre["val_lock_bins"].astype(np.int64)

    x = preprocess_batch(val_spectra, val_lockbins)
    with torch.no_grad():
        val_delta = fcnn(x).detach().cpu().numpy().reshape(-1)
    val_delta_clamped = np.clip(val_delta, -CLAMP_UT, CLAMP_UT)

    val_pid_err = np.abs(val_b_pid - val_b_true)
    val_fcnn_err_unc = np.abs(val_b_pid + val_delta - val_b_true)
    val_fcnn_err_clp = np.abs(val_b_pid + val_delta_clamped - val_b_true)

    log.info("=== Validation set (n=%d) ===", val_spectra.shape[0])
    val_unc = headline("val unclamped", val_pid_err, val_fcnn_err_unc)
    val_clp = headline("val CLAMPED ±2.25 µT", val_pid_err, val_fcnn_err_clp)
    n_clipped_val = int(np.sum(np.abs(val_delta) > CLAMP_UT))
    log.info("  val: %d / %d (%.1f%%) raw FCNN outputs exceed ±%.2f µT",
             n_clipped_val, val_delta.size,
             100.0 * n_clipped_val / val_delta.size, CLAMP_UT)

    # --- Sweep eval — read raw FCNN outputs from sweep npz; re-clamp ---
    log.info("")
    log.info("Loading heading sweep")
    sweep = np.load(SWEEP_NPZ)
    sw_b_pid = sweep["pid_estimates_uT"]
    sw_b_true_mag = float(sweep["b_mag_true_uT"])
    sw_delta = sweep["fcnn_delta_b_uT"]
    sw_b_vecs = sweep["b_vecs_T"]
    sw_theta = polar_theta(sw_b_vecs)

    sw_delta_clamped = np.clip(sw_delta, -CLAMP_UT, CLAMP_UT)
    sw_pid_err = np.abs(sw_b_pid - sw_b_true_mag)
    sw_fcnn_err_unc = np.abs(sw_b_pid + sw_delta - sw_b_true_mag)
    sw_fcnn_err_clp = np.abs(sw_b_pid + sw_delta_clamped - sw_b_true_mag)

    log.info("=== Heading sweep (n=%d) ===", sw_delta.size)
    sw_unc = headline("sweep unclamped", sw_pid_err, sw_fcnn_err_unc)
    sw_clp = headline("sweep CLAMPED ±2.25 µT", sw_pid_err, sw_fcnn_err_clp)
    n_clipped_sw = int(np.sum(np.abs(sw_delta) > CLAMP_UT))
    log.info("  sweep: %d / %d (%.1f%%) raw FCNN outputs exceed ±%.2f µT",
             n_clipped_sw, sw_delta.size,
             100.0 * n_clipped_sw / sw_delta.size, CLAMP_UT)

    # --- Per-θ-bin breakdown for sweep (and val for context) ---
    edges = np.linspace(0.0, np.pi, N_BINS + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    val_theta = polar_theta(val_labels)

    val_pid_b, val_n = per_bin_mean(val_theta, val_pid_err, edges)
    val_fcnn_unc_b, _ = per_bin_mean(val_theta, val_fcnn_err_unc, edges)
    val_fcnn_clp_b, _ = per_bin_mean(val_theta, val_fcnn_err_clp, edges)
    sw_pid_b, sw_n = per_bin_mean(sw_theta, sw_pid_err, edges)
    sw_fcnn_unc_b, _ = per_bin_mean(sw_theta, sw_fcnn_err_unc, edges)
    sw_fcnn_clp_b, _ = per_bin_mean(sw_theta, sw_fcnn_err_clp, edges)

    log.info("")
    log.info("=== Per-θ-bin breakdown (sweep) ===")
    log.info("%-4s %-10s %6s %10s %10s %10s %10s %10s",
             "bin", "θ center", "n_sw", "PID_sw",
             "FCNN_unc", "FCNN_clp", "Δunc-PID", "Δclp-PID")
    log.info("-" * 90)
    for b in range(N_BINS):
        log.info("%-4d %-10.3f %6d %10.3f %10.3f %10.3f %+10.3f %+10.3f",
                 b, centers[b], sw_n[b], sw_pid_b[b],
                 sw_fcnn_unc_b[b], sw_fcnn_clp_b[b],
                 sw_fcnn_unc_b[b] - sw_pid_b[b],
                 sw_fcnn_clp_b[b] - sw_pid_b[b])

    # --- Read on easy-bin over-correction (bins 0,1,8,9 from prior Analysis 2) ---
    easy_bins = [0, 1, 8, 9]
    log.info("")
    log.info("=== Easy-bin (0,1,8,9) over-correction check ===")
    for b in easy_bins:
        delta_unc = sw_fcnn_unc_b[b] - sw_pid_b[b]
        delta_clp = sw_fcnn_clp_b[b] - sw_pid_b[b]
        improved = (delta_clp < delta_unc) and (delta_clp >= 0 or delta_clp > delta_unc)
        log.info("  bin %d (θ=%.3f): PID=%.2f  FCNN_unc=%.2f (Δ %+.2f)  "
                 "FCNN_clp=%.2f (Δ %+.2f)  clamp helps? %s",
                 b, centers[b], sw_pid_b[b],
                 sw_fcnn_unc_b[b], delta_unc, sw_fcnn_clp_b[b], delta_clp,
                 "YES" if delta_clp < delta_unc else "NO")

    # --- Plot updated orientation-binned figure with clamped overlay ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    ax = axes[0]
    ax.plot(centers, val_pid_b, "o-", color="black", alpha=0.4,
            label=f"val PID (n={val_pid_err.size})")
    ax.plot(centers, sw_pid_b, "s-", color="black", linewidth=1.5,
            label=f"sweep PID (n={sw_pid_err.size})")
    ax.plot(centers, sw_fcnn_unc_b, "x--", color="#D7263D",
            label="sweep FCNN+PID UNCLAMPED")
    ax.plot(centers, sw_fcnn_clp_b, "s-", color="#D7263D", markerfacecolor="white",
            label=f"sweep FCNN+PID CLAMPED ±{CLAMP_UT} µT")
    ax.set_xlabel("Polar angle θ (rad)")
    ax.set_ylabel("MAE per bin (µT)")
    ax.set_title("Heading sweep — FCNN+PID error vs orientation\n(clamped vs unclamped)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper center", fontsize=9)

    ax = axes[1]
    ax.plot(centers, val_pid_b, "o-", color="#2176FF", linewidth=1.5,
            label="val PID")
    ax.plot(centers, val_fcnn_unc_b, "x--", color="#2176FF",
            label="val FCNN+PID UNCLAMPED")
    ax.plot(centers, val_fcnn_clp_b, "o-", color="#2176FF", markerfacecolor="white",
            label=f"val FCNN+PID CLAMPED ±{CLAMP_UT} µT")
    ax.set_xlabel("Polar angle θ (rad)")
    ax.set_ylabel("MAE per bin (µT)")
    ax.set_title("Validation set — FCNN+PID error vs orientation\n(clamped vs unclamped)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper center", fontsize=9)

    fig.suptitle(
        f"Orientation-binned MAE — clamp ±{CLAMP_UT} µT applied pre-PID-add",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    log.info("Saved: %s", OUT_PNG)

    # --- Save numeric results ---
    out: dict[str, np.ndarray] = {
        "clamp_uT": np.asarray(CLAMP_UT),
        "n_bins": np.asarray(N_BINS),
        "edges_rad": edges,
        "centers_rad": centers,
        # val
        "val_pid_err_uT": val_pid_err,
        "val_fcnn_err_unc_uT": val_fcnn_err_unc,
        "val_fcnn_err_clp_uT": val_fcnn_err_clp,
        "val_delta_pred_uT": val_delta,
        "val_delta_clamped_uT": val_delta_clamped,
        "val_n_clipped": np.asarray(n_clipped_val),
        "val_pid_per_bin": val_pid_b,
        "val_fcnn_unc_per_bin": val_fcnn_unc_b,
        "val_fcnn_clp_per_bin": val_fcnn_clp_b,
        "val_n_per_bin": val_n,
        # sweep
        "sweep_pid_err_uT": sw_pid_err,
        "sweep_fcnn_err_unc_uT": sw_fcnn_err_unc,
        "sweep_fcnn_err_clp_uT": sw_fcnn_err_clp,
        "sweep_delta_pred_uT": sw_delta,
        "sweep_delta_clamped_uT": sw_delta_clamped,
        "sweep_n_clipped": np.asarray(n_clipped_sw),
        "sweep_pid_per_bin": sw_pid_b,
        "sweep_fcnn_unc_per_bin": sw_fcnn_unc_b,
        "sweep_fcnn_clp_per_bin": sw_fcnn_clp_b,
        "sweep_n_per_bin": sw_n,
        # headlines
        "val_mae_pid": np.asarray(val_unc["mae_pid"]),
        "val_mae_fcnn_unc": np.asarray(val_unc["mae_fcnn"]),
        "val_mae_fcnn_clp": np.asarray(val_clp["mae_fcnn"]),
        "val_reduction_unc_pct": np.asarray(val_unc["reduction_pct"]),
        "val_reduction_clp_pct": np.asarray(val_clp["reduction_pct"]),
        "sweep_mae_pid": np.asarray(sw_unc["mae_pid"]),
        "sweep_mae_fcnn_unc": np.asarray(sw_unc["mae_fcnn"]),
        "sweep_mae_fcnn_clp": np.asarray(sw_clp["mae_fcnn"]),
        "sweep_reduction_unc_pct": np.asarray(sw_unc["reduction_pct"]),
        "sweep_reduction_clp_pct": np.asarray(sw_clp["reduction_pct"]),
    }
    np.savez(str(OUT_NPZ), **out)
    log.info("Saved: %s", OUT_NPZ)


if __name__ == "__main__":
    main()
