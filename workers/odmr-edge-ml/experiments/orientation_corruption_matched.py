#!/usr/bin/env python3
"""Corruption-matched orientation slice of the val set vs. heading sweep.

Tests Reviewer 2's claim that the val set under-samples worst-case
orientations. Filters production_50k val records whose corruption parameters
fall near the sweep's fixed point (P1=50 ppm, T=300 K, B1_grad=0.15), then
compares FCNN+PID MAE reduction on that orientation-conditional subset
against the full-val 54.3% and the 1440-angle sweep's 31.3% headlines.

If the corruption-matched subset shows ~31% reduction, the val set's harder
corruption was masking an orientation gap (Reviewer 2 supported). If it
still shows >50%, the OOD framing is not supported.
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

# Repo src layout: import via PYTHONPATH or installed package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from odmr_edge_ml.models.fcnn import OdmrFCNN  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# --- Paths ---
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
OUT_NPZ = Path(__file__).resolve().parent / "orientation_corruption_matched_results.npz"

# --- Sweep fixed point ---
# Per heading_sweep.py: P1_PPM=50.0, TEMPERATURE_K=300.0, B1_GRADIENT_FRAC=0.15,
# B_PERP_T=0.0. mw_power_scale varies via OU trajectory in the sweep too,
# so we do NOT match on it.
SWEEP_FIXED = {
    "P1_ppm": 50.0,
    "T_K": 300.0,
    "B1_grad": 0.15,
}
ANCHOR_SIGMA = 1.5  # must match training preprocessing

# Match windows tried in order; first window with n >= MIN_N is used.
MATCH_WINDOWS_PCT = [10, 20, 30, 50]
MIN_N = 30


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
    """Vectorized spectrum + Gaussian-anchor preprocessing."""
    s_min = spectra.min(axis=1, keepdims=True)
    s_max = spectra.max(axis=1, keepdims=True)
    denom = np.where(s_max == s_min, 1.0, s_max - s_min)
    spec_norm = 2.0 * (spectra - s_min) / denom - 1.0  # (n, 100)

    n, k = spectra.shape
    bins = np.arange(k)[None, :]
    anchor = np.exp(-0.5 * ((bins - lock_bins[:, None]) / ANCHOR_SIGMA) ** 2)  # (n, 100)

    combined = np.concatenate([spec_norm, anchor], axis=1)  # (n, 200)
    return torch.from_numpy(combined).float().to(DEVICE)


def percent_match_mask(values: np.ndarray, target: float, pct: float) -> np.ndarray:
    return np.abs(values - target) <= (pct / 100.0) * target


def stats(name: str, x: np.ndarray) -> dict[str, float]:
    s = {
        "n": int(x.size),
        "mean": float(x.mean()),
        "median": float(np.median(x)),
        "P90": float(np.percentile(x, 90)),
        "P99": float(np.percentile(x, 99)),
        "max": float(x.max()),
    }
    log.info(
        "  %-25s n=%5d  mean=%7.3f  median=%7.3f  P90=%7.3f  P99=%7.3f  max=%7.3f",
        name, s["n"], s["mean"], s["median"], s["P90"], s["P99"], s["max"],
    )
    return s


def main() -> None:
    if not CKPT_PATH.exists():
        log.error("FCNN checkpoint not found: %s", CKPT_PATH)
        sys.exit(1)

    log.info("Loading val/corruption_params and val/spectra from %s", DATASET_H5)
    with h5py.File(DATASET_H5, "r") as h:
        cp = h["val/corruption_params"][:]      # (5000, 5)
        spectra = h["val/spectra"][:]            # (5000, 100)
        labels = h["val/labels"][:]              # (5000, 3)  B in Tesla
    p1 = cp[:, 0]
    T_K = cp[:, 1]
    b1g = cp[:, 2]

    pid = np.load(PID_NPZ)
    b_pid = pid["val_b_pid_uT"]                  # (5000,)
    b_true = pid["val_b_mag_uT"]                 # (5000,)
    lock_bins = pid["val_lock_bins"]             # (5000,)

    log.info("Val n=%d  P1∈[%.1f,%.1f]  T∈[%.1f,%.1f] K  B1g∈[%.3f,%.3f]",
             spectra.shape[0], p1.min(), p1.max(), T_K.min(), T_K.max(),
             b1g.min(), b1g.max())

    # --- Find usable match window ---
    chosen_window: int | None = None
    chosen_mask: np.ndarray | None = None
    window_log: list[tuple[int, int]] = []
    for pct in MATCH_WINDOWS_PCT:
        m_p1 = percent_match_mask(p1, SWEEP_FIXED["P1_ppm"], pct)
        m_T = percent_match_mask(T_K, SWEEP_FIXED["T_K"], pct)
        m_b1 = percent_match_mask(b1g, SWEEP_FIXED["B1_grad"], pct)
        mask = m_p1 & m_T & m_b1
        n_match = int(mask.sum())
        window_log.append((pct, n_match))
        log.info("  ±%d%% window: n_P1=%d n_T=%d n_B1g=%d  joint=%d",
                 pct, int(m_p1.sum()), int(m_T.sum()), int(m_b1.sum()), n_match)
        if chosen_window is None and n_match >= MIN_N:
            chosen_window = pct
            chosen_mask = mask

    if chosen_mask is None or chosen_window is None:
        log.error("No window in %s gave n >= %d. Bailing.", MATCH_WINDOWS_PCT, MIN_N)
        sys.exit(2)

    log.info("")
    log.info("Using ±%d%% window  →  n_filtered = %d / %d val records",
             chosen_window, int(chosen_mask.sum()), spectra.shape[0])

    # --- Run FCNN on filtered subset ---
    fcnn = load_fcnn(CKPT_PATH)
    log.info("FCNN loaded: %d params", sum(p.numel() for p in fcnn.parameters()))

    sub_spectra = spectra[chosen_mask]
    sub_lockbins = lock_bins[chosen_mask].astype(np.int64)
    sub_b_pid = b_pid[chosen_mask]
    sub_b_true = b_true[chosen_mask]

    x = preprocess_batch(sub_spectra, sub_lockbins)
    with torch.no_grad():
        delta_pred = fcnn(x).detach().cpu().numpy().reshape(-1)
    fcnn_pid = sub_b_pid + delta_pred

    pid_err = np.abs(sub_b_pid - sub_b_true)
    fcnn_err = np.abs(fcnn_pid - sub_b_true)
    mae_pid = float(pid_err.mean())
    mae_fcnn = float(fcnn_err.mean())
    reduction_pct = (1.0 - mae_fcnn / mae_pid) * 100.0

    log.info("")
    log.info("=== Filtered subset error stats (µT) ===")
    pid_s = stats("PID baseline (filtered)", pid_err)
    fcnn_s = stats("FCNN+PID    (filtered)", fcnn_err)

    log.info("")
    log.info("=== MAE reduction comparison ===")
    log.info("  Filtered subset:  MAE_PID=%.3f µT  MAE_FCNN+PID=%.3f µT  reduction=%.2f%%",
             mae_pid, mae_fcnn, reduction_pct)
    log.info("  Headline (full val): 54.3%%")
    log.info("  Headline (sweep):    31.3%%")
    diff_to_val = reduction_pct - 54.3
    diff_to_sweep = reduction_pct - 31.3
    log.info("  Filtered − full-val:   %+.2f pp", diff_to_val)
    log.info("  Filtered − sweep:      %+.2f pp", diff_to_sweep)

    # --- Sanity: also report on FULL val for our own headline check ---
    x_full = preprocess_batch(spectra, lock_bins.astype(np.int64))
    with torch.no_grad():
        delta_full = fcnn(x_full).detach().cpu().numpy().reshape(-1)
    fcnn_pid_full = b_pid + delta_full
    pid_err_full = np.abs(b_pid - b_true)
    fcnn_err_full = np.abs(fcnn_pid_full - b_true)
    mae_pid_full = float(pid_err_full.mean())
    mae_fcnn_full = float(fcnn_err_full.mean())
    red_full = (1.0 - mae_fcnn_full / mae_pid_full) * 100.0
    log.info("")
    log.info("=== Full-val sanity check (re-derived) ===")
    log.info("  MAE_PID=%.3f µT  MAE_FCNN+PID=%.3f µT  reduction=%.2f%%",
             mae_pid_full, mae_fcnn_full, red_full)

    # --- Sweep headline re-derivation ---
    sweep = np.load(SWEEP_NPZ)
    sw_pid = float(np.abs(sweep["pid_error_uT"]).mean())
    sw_fcnn = float(np.abs(sweep["cnn_error_uT"]).mean())
    sw_red = (1.0 - sw_fcnn / sw_pid) * 100.0
    log.info("=== Sweep headline (re-derived) ===")
    log.info("  MAE_PID=%.3f µT  MAE_FCNN+PID=%.3f µT  reduction=%.2f%%",
             sw_pid, sw_fcnn, sw_red)

    # --- Save ---
    out = {
        "window_pct_used": np.asarray(chosen_window),
        "window_log": np.asarray(window_log),
        "n_filtered": np.asarray(int(chosen_mask.sum())),
        "filtered_mask": chosen_mask,
        "filtered_pid_err_uT": pid_err,
        "filtered_fcnn_err_uT": fcnn_err,
        "filtered_delta_pred_uT": delta_pred,
        "filtered_b_pid_uT": sub_b_pid,
        "filtered_b_true_uT": sub_b_true,
        "filtered_corruption_params": cp[chosen_mask],
        "filtered_labels_T": labels[chosen_mask],
        "mae_pid_filtered": np.asarray(mae_pid),
        "mae_fcnn_filtered": np.asarray(mae_fcnn),
        "reduction_pct_filtered": np.asarray(reduction_pct),
        "mae_pid_full_val": np.asarray(mae_pid_full),
        "mae_fcnn_full_val": np.asarray(mae_fcnn_full),
        "reduction_pct_full_val": np.asarray(red_full),
        "mae_pid_sweep": np.asarray(sw_pid),
        "mae_fcnn_sweep": np.asarray(sw_fcnn),
        "reduction_pct_sweep": np.asarray(sw_red),
    }
    np.savez(str(OUT_NPZ), **out)
    log.info("Saved: %s", OUT_NPZ)


if __name__ == "__main__":
    main()
