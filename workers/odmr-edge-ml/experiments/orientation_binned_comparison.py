#!/usr/bin/env python3
"""Orientation-binned (polar θ) comparison: val split vs heading sweep.

Bins each set by polar angle θ = arccos(B_z / ||B||) of the B-field vector
into ~10 bins covering [0, π], then computes |PID error| and |FCNN+PID
error| per bin for both sets. Plots side-by-side and flags low-n bins.

Tells us, conditional on θ, whether the val split or the sweep covers any
specific orientation regime more sparsely than the other.
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
    "~/Desktop/Shared/codex-review/spark1_projects/"
    "tychon-odmr-ml/experiments/heading_sweep_results.npz"
)
CKPT_PATH = Path(
    "~/Desktop/Shared/codex-review/spark1_projects/"
    "tychon-odmr-ml/experiments/scalar_residual/fcnn/checkpoints/best_model.pt"
)
OUT_PNG = Path(__file__).resolve().parent / "figures" / "orientation_binned_comparison.png"
OUT_NPZ = Path(__file__).resolve().parent / "orientation_binned_comparison.npz"

ANCHOR_SIGMA = 1.5
N_BINS = 10
LOW_N_THRESH = 20  # mark bins with n below this in either set


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
    """θ = arccos(B_z / ||B||), in [0, π]."""
    bmag = np.linalg.norm(b_vec, axis=1)
    bz = b_vec[:, 2]
    return np.arccos(np.clip(bz / np.where(bmag == 0, 1.0, bmag), -1.0, 1.0))


def per_bin_stats(theta: np.ndarray, err: np.ndarray, edges: np.ndarray) -> dict:
    bin_idx = np.digitize(theta, edges) - 1
    bin_idx = np.clip(bin_idx, 0, len(edges) - 2)
    n_bins = len(edges) - 1
    out = {
        "n": np.zeros(n_bins, dtype=int),
        "mean": np.full(n_bins, np.nan),
        "median": np.full(n_bins, np.nan),
        "P90": np.full(n_bins, np.nan),
    }
    for b in range(n_bins):
        sel = bin_idx == b
        n = int(sel.sum())
        out["n"][b] = n
        if n > 0:
            out["mean"][b] = float(err[sel].mean())
            out["median"][b] = float(np.median(err[sel]))
            if n >= 5:
                out["P90"][b] = float(np.percentile(err[sel], 90))
    return out


def main() -> None:
    if not CKPT_PATH.exists():
        log.error("FCNN checkpoint not found: %s", CKPT_PATH)
        sys.exit(1)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)

    # --- Load val ---
    log.info("Loading val data")
    with h5py.File(DATASET_H5, "r") as h:
        spectra = h["val/spectra"][:]
        labels = h["val/labels"][:]  # 3D B in Tesla
    pid = np.load(PID_NPZ)
    val_b_pid = pid["val_b_pid_uT"]
    val_b_true = pid["val_b_mag_uT"]
    val_lockbins = pid["val_lock_bins"].astype(np.int64)
    val_theta = polar_theta(labels)

    # --- Run FCNN on full val ---
    fcnn = load_fcnn(CKPT_PATH)
    log.info("FCNN loaded: %d params", sum(p.numel() for p in fcnn.parameters()))
    x = preprocess_batch(spectra, val_lockbins)
    with torch.no_grad():
        delta_pred = fcnn(x).detach().cpu().numpy().reshape(-1)
    val_fcnn_pid = val_b_pid + delta_pred
    val_pid_err = np.abs(val_b_pid - val_b_true)
    val_fcnn_err = np.abs(val_fcnn_pid - val_b_true)

    # --- Load sweep ---
    sweep = np.load(SWEEP_NPZ)
    sw_b_vecs = sweep["b_vecs_T"]              # (1440, 3)
    sw_theta = polar_theta(sw_b_vecs)
    sw_pid_err = np.abs(sweep["pid_error_uT"])
    sw_fcnn_err = np.abs(sweep["cnn_error_uT"])

    log.info("val θ range: [%.3f, %.3f] rad   sweep θ range: [%.3f, %.3f] rad",
             val_theta.min(), val_theta.max(), sw_theta.min(), sw_theta.max())

    # --- Bin both sets on shared edges over [0, π] ---
    edges = np.linspace(0.0, np.pi, N_BINS + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])

    val_pid_bin = per_bin_stats(val_theta, val_pid_err, edges)
    val_fcnn_bin = per_bin_stats(val_theta, val_fcnn_err, edges)
    sw_pid_bin = per_bin_stats(sw_theta, sw_pid_err, edges)
    sw_fcnn_bin = per_bin_stats(sw_theta, sw_fcnn_err, edges)

    # --- Print per-bin table ---
    log.info("")
    log.info("%-6s %-12s %8s %10s %10s   %8s %10s %10s",
             "bin", "θ center", "n_val", "MAE_PID_v", "MAE_FCN_v",
             "n_sweep", "MAE_PID_s", "MAE_FCN_s")
    log.info("-" * 92)
    for b in range(N_BINS):
        log.info("%-6d %-12.3f %8d %10.3f %10.3f   %8d %10.3f %10.3f",
                 b, centers[b],
                 val_pid_bin["n"][b], val_pid_bin["mean"][b], val_fcnn_bin["mean"][b],
                 sw_pid_bin["n"][b], sw_pid_bin["mean"][b], sw_fcnn_bin["mean"][b])

    # --- Highlight under-represented bins ---
    val_low = [b for b in range(N_BINS) if val_pid_bin["n"][b] < LOW_N_THRESH]
    sw_low = [b for b in range(N_BINS) if sw_pid_bin["n"][b] < LOW_N_THRESH]
    log.info("")
    log.info("Bins with n < %d  in val:   %s", LOW_N_THRESH, val_low or "none")
    log.info("Bins with n < %d  in sweep: %s", LOW_N_THRESH, sw_low or "none")

    # Bins well-represented in val but sparse in sweep, and vice versa
    val_well_sw_sparse = [b for b in range(N_BINS)
                          if val_pid_bin["n"][b] >= LOW_N_THRESH
                          and sw_pid_bin["n"][b] < LOW_N_THRESH]
    sw_well_val_sparse = [b for b in range(N_BINS)
                          if sw_pid_bin["n"][b] >= LOW_N_THRESH
                          and val_pid_bin["n"][b] < LOW_N_THRESH]
    log.info("Bins well-covered in val but sparse in sweep: %s", val_well_sw_sparse or "none")
    log.info("Bins well-covered in sweep but sparse in val: %s", sw_well_val_sparse or "none")

    # --- Plot ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=False)

    # Left: |PID error| vs θ
    ax = axes[0]
    ax.plot(centers, val_pid_bin["mean"], "o-", color="#2176FF",
            label=f"val |PID err| (mean), n_total={val_pid_err.size}")
    ax.plot(centers, sw_pid_bin["mean"], "s-", color="#D7263D",
            label=f"sweep |PID err| (mean), n_total={sw_pid_err.size}")
    ax.set_xlabel("Polar angle θ (rad)")
    ax.set_ylabel("|PID baseline error| (µT, mean per bin)")
    ax.set_title("PID baseline error vs orientation")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9)

    # Right: |FCNN+PID error| vs θ
    ax = axes[1]
    ax.plot(centers, val_fcnn_bin["mean"], "o-", color="#2176FF",
            label="val |FCNN+PID err| (mean)")
    ax.plot(centers, sw_fcnn_bin["mean"], "s-", color="#D7263D",
            label="sweep |FCNN+PID err| (mean)")
    ax.set_xlabel("Polar angle θ (rad)")
    ax.set_ylabel("|FCNN+PID error| (µT, mean per bin)")
    ax.set_title("FCNN+PID error vs orientation")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9)

    # Mark low-n bins on both axes
    for ax in axes:
        for b in range(N_BINS):
            if val_pid_bin["n"][b] < LOW_N_THRESH:
                ax.axvspan(edges[b], edges[b + 1], color="#2176FF", alpha=0.07)
            if sw_pid_bin["n"][b] < LOW_N_THRESH:
                ax.axvspan(edges[b], edges[b + 1], color="#D7263D", alpha=0.07)

    fig.suptitle(
        "Orientation-binned error comparison — val split (50k) vs heading sweep (1440)\n"
        "(shaded bands: low-n bins in val=blue, sweep=red)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    log.info("Saved: %s", OUT_PNG)

    # --- Save numeric results ---
    out = {
        "edges_rad": edges,
        "centers_rad": centers,
        "val_n": val_pid_bin["n"],
        "val_mae_pid": val_pid_bin["mean"],
        "val_mae_fcnn": val_fcnn_bin["mean"],
        "val_median_pid": val_pid_bin["median"],
        "val_median_fcnn": val_fcnn_bin["median"],
        "val_p90_pid": val_pid_bin["P90"],
        "val_p90_fcnn": val_fcnn_bin["P90"],
        "sweep_n": sw_pid_bin["n"],
        "sweep_mae_pid": sw_pid_bin["mean"],
        "sweep_mae_fcnn": sw_fcnn_bin["mean"],
        "sweep_median_pid": sw_pid_bin["median"],
        "sweep_median_fcnn": sw_fcnn_bin["median"],
        "sweep_p90_pid": sw_pid_bin["P90"],
        "sweep_p90_fcnn": sw_fcnn_bin["P90"],
        "val_theta_rad": val_theta,
        "sweep_theta_rad": sw_theta,
    }
    np.savez(str(OUT_NPZ), **out)
    log.info("Saved: %s", OUT_NPZ)


if __name__ == "__main__":
    main()
