#!/usr/bin/env python3
"""Phase C eval bundle for v2 (Dataset A) — sub-tasks C-1, C-2, C-3, C-4.

C-1  Val MAE — clamped + unclamped (vs PID baseline)
C-2  Heading sweep — clamped + unclamped (re-uses spectra from Apr 1's
     v1 heading_sweep_results.npz; the spectra are deterministic functions
     of seed=42 and corruption params, identical for any model evaluator)
C-3  θ-binned breakdown of the C-2 sweep
C-4  Dataset A AIC test split MAE reduction

C-5 (ADEV) runs separately because the time-series simulation needs the
SimOS adapter; that's adev_simulation_v2.py.

Eval is fp32 only (no autocast). σ=1.267999 in the anchor formula for
v2 (Dataset A) preprocessing.
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
from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID  # noqa: E402
from odmr_edge_ml.models.fcnn import OdmrFCNN  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# --- Paths (env-overridable so the same script can evaluate Apr-1 v2 too) ---
import os as _os
V2_CKPT = Path(_os.environ.get(
    "PHASE_C_CKPT",
    "~/projects/odmr-edge-ml/experiments/"
    "scalar_residual_v2_dataset_a/checkpoints/best_model_dataset_a.pt",
))
PROD_DS = Path("~/projects/odmr-edge-ml/data/production_50k/dataset.h5")
PROD_PID = Path("~/projects/odmr-edge-ml/data/production_50k/pid_residuals.npz")
AIC_DS = Path(
    "~/projects/tychon-shared-data/production_50k_v2_aic/dataset.h5"
)
AIC_PID = Path(
    "~/projects/tychon-shared-data/production_50k_v2_aic/pid_residuals.npz"
)
SWEEP_NPZ = Path(
    "~/shared/codex-review/ws1_projects/"
    "tychon-odmr-ml/experiments/heading_sweep_results.npz"
)
_TAG = _os.environ.get("PHASE_C_TAG", "v2_dataset_a")
OUT_NPZ = Path(
    f"~/projects/odmr-edge-ml/experiments/"
    f"phase_c_results_{_TAG}.npz"
)
OUT_PNG = Path(
    f"~/projects/odmr-edge-ml/experiments/figures/"
    f"{_TAG}_orientation_binned.png"
)

# --- Constants ---
SIGMA_V2_DATASET_A = float(_os.environ.get("PHASE_C_SIGMA", "1.267999"))
CLAMP_UT = 2.25
N_BINS = 10
INPUT_DIM = 100


def strip_compile_qat_keys(sd: dict) -> dict:
    """torch.compile prefix + FX-QAT observer-key strip."""
    skip = ("fake_quant", "activation_post_process", "observer")
    out: dict = {}
    for k, v in sd.items():
        if any(p in k for p in skip):
            continue
        new_key = k[len("_orig_mod."):] if k.startswith("_orig_mod.") else k
        out[new_key] = v
    return out


def load_v2_dataset_a() -> OdmrFCNN:
    """Load v2 (Dataset A) checkpoint into vanilla OdmrFCNN; drop σ/bins."""
    ck = torch.load(V2_CKPT, map_location="cpu", weights_only=False)
    clean = strip_compile_qat_keys(ck["model_state_dict"])
    model = OdmrFCNN(input_dim=INPUT_DIM, output_dim=1, in_channels=2)
    target = set(model.state_dict().keys())
    export_sd = {k: v for k, v in clean.items() if k in target}
    model.load_state_dict(export_sd, strict=True)
    model.eval()
    return model.to(DEVICE)


def preprocess_batch(spectra: np.ndarray, lock_bins: np.ndarray,
                     sigma: float) -> torch.Tensor:
    """Spec norm to [-1,1] + Gaussian anchor with given σ; return (N, 200)."""
    s_min = spectra.min(axis=1, keepdims=True)
    s_max = spectra.max(axis=1, keepdims=True)
    denom = np.where(s_max == s_min, 1.0, s_max - s_min)
    spec_norm = 2.0 * (spectra - s_min) / denom - 1.0

    bins = np.arange(spectra.shape[1])[None, :]
    anchor = np.exp(-0.5 * ((bins - lock_bins[:, None]) / sigma) ** 2)
    return torch.from_numpy(np.concatenate([spec_norm, anchor], axis=1)).float().to(DEVICE)


def fcnn_predict(model: OdmrFCNN, spectra: np.ndarray, lock_bins: np.ndarray,
                 sigma: float) -> np.ndarray:
    x = preprocess_batch(spectra, lock_bins, sigma)
    with torch.no_grad():
        delta = model(x).detach().cpu().numpy().reshape(-1)
    return delta


def polar_theta(b_vec: np.ndarray) -> np.ndarray:
    bmag = np.linalg.norm(b_vec, axis=1)
    bz = b_vec[:, 2]
    return np.arccos(np.clip(bz / np.where(bmag == 0, 1.0, bmag), -1.0, 1.0))


def run_pid_batch(frequencies: np.ndarray, spectra: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
    pid = DerivativeZeroCrossingPID(frequencies)
    n = spectra.shape[0]
    b_pid = np.zeros(n)
    lb = np.zeros(n, dtype=np.int64)
    for i in range(n):
        r = pid.estimate(spectra[i])
        b_pid[i] = r.b_mag_uT
        lb[i] = r.lock_bin
    return b_pid, lb


def main() -> None:
    log.info("Device: %s", DEVICE)
    log.info("σ (v2 Dataset A) = %.6f", SIGMA_V2_DATASET_A)
    log.info("Clamp = ±%.2f µT", CLAMP_UT)

    model = load_v2_dataset_a()
    n_params = sum(p.numel() for p in model.parameters())
    log.info("v2 (Dataset A) loaded: %d params", n_params)

    # =====================================================================
    # C-1: Validation set MAE — clamped vs unclamped
    # =====================================================================
    log.info("")
    log.info("=" * 70)
    log.info("C-1: VAL CLAMPED vs UNCLAMPED")
    log.info("=" * 70)

    with h5py.File(PROD_DS, "r") as h:
        val_spec = h["val/spectra"][:]
        val_labels = h["val/labels"][:]
    pid_pre = np.load(PROD_PID)
    val_b_pid = pid_pre["val_b_pid_uT"]
    val_b_true = pid_pre["val_b_mag_uT"]
    val_lock = pid_pre["val_lock_bins"].astype(np.int64)

    val_delta = fcnn_predict(model, val_spec, val_lock, SIGMA_V2_DATASET_A)
    val_delta_clp = np.clip(val_delta, -CLAMP_UT, CLAMP_UT)

    val_pid_err = np.abs(val_b_pid - val_b_true)
    val_unc_err = np.abs(val_b_pid + val_delta - val_b_true)
    val_clp_err = np.abs(val_b_pid + val_delta_clp - val_b_true)

    val_mae_pid = float(val_pid_err.mean())
    val_mae_unc = float(val_unc_err.mean())
    val_mae_clp = float(val_clp_err.mean())
    val_red_unc = (1.0 - val_mae_unc / val_mae_pid) * 100.0
    val_red_clp = (1.0 - val_mae_clp / val_mae_pid) * 100.0
    val_n_clipped = int(np.sum(np.abs(val_delta) > CLAMP_UT))

    log.info("  n=%d", val_pid_err.size)
    log.info("  PID baseline       MAE = %.4f µT", val_mae_pid)
    log.info("  v2 unclamped       MAE = %.4f µT  reduction = %.2f%%",
             val_mae_unc, val_red_unc)
    log.info("  v2 CLAMPED ±%.2f   MAE = %.4f µT  reduction = %.2f%%",
             CLAMP_UT, val_mae_clp, val_red_clp)
    log.info("  raw |delta| > clamp: %d/%d (%.1f%%)",
             val_n_clipped, val_delta.size, 100.0 * val_n_clipped / val_delta.size)

    # =====================================================================
    # C-2: Heading sweep — clamped vs unclamped (reuse v1 sweep spectra)
    # =====================================================================
    log.info("")
    log.info("=" * 70)
    log.info("C-2: HEADING SWEEP CLAMPED vs UNCLAMPED")
    log.info("=" * 70)

    sweep = np.load(SWEEP_NPZ)
    sw_spec = sweep["spectra"]                     # (1440, 100)
    sw_lock = sweep["pid_lock_bins"].astype(np.int64)
    sw_b_pid = sweep["pid_estimates_uT"]
    sw_b_true = float(sweep["b_mag_true_uT"])
    sw_b_vecs = sweep["b_vecs_T"]
    sw_theta = polar_theta(sw_b_vecs)

    sw_delta = fcnn_predict(model, sw_spec, sw_lock, SIGMA_V2_DATASET_A)
    sw_delta_clp = np.clip(sw_delta, -CLAMP_UT, CLAMP_UT)

    sw_pid_err = np.abs(sw_b_pid - sw_b_true)
    sw_unc_err = np.abs(sw_b_pid + sw_delta - sw_b_true)
    sw_clp_err = np.abs(sw_b_pid + sw_delta_clp - sw_b_true)

    sw_mae_pid = float(sw_pid_err.mean())
    sw_mae_unc = float(sw_unc_err.mean())
    sw_mae_clp = float(sw_clp_err.mean())
    sw_red_unc = (1.0 - sw_mae_unc / sw_mae_pid) * 100.0
    sw_red_clp = (1.0 - sw_mae_clp / sw_mae_pid) * 100.0
    sw_n_clipped = int(np.sum(np.abs(sw_delta) > CLAMP_UT))

    log.info("  n=%d  (sweep spectra reused from Apr-1 v1 sweep, seed=42)", sw_pid_err.size)
    log.info("  PID baseline       MAE = %.4f µT", sw_mae_pid)
    log.info("  v2 unclamped       MAE = %.4f µT  reduction = %.2f%%",
             sw_mae_unc, sw_red_unc)
    log.info("  v2 CLAMPED ±%.2f   MAE = %.4f µT  reduction = %.2f%%",
             CLAMP_UT, sw_mae_clp, sw_red_clp)
    log.info("  raw |delta| > clamp: %d/%d (%.1f%%)",
             sw_n_clipped, sw_delta.size, 100.0 * sw_n_clipped / sw_delta.size)
    log.info("  raw |delta| max = %.4f µT", float(np.abs(sw_delta).max()))

    # =====================================================================
    # C-3: θ-binned breakdown for the sweep
    # =====================================================================
    log.info("")
    log.info("=" * 70)
    log.info("C-3: SWEEP θ-BINNED (10 bins over [0, π])")
    log.info("=" * 70)

    edges = np.linspace(0.0, np.pi, N_BINS + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    bin_idx = np.clip(np.digitize(sw_theta, edges) - 1, 0, N_BINS - 1)

    pid_per_bin = np.zeros(N_BINS)
    unc_per_bin = np.zeros(N_BINS)
    clp_per_bin = np.zeros(N_BINS)
    n_per_bin = np.zeros(N_BINS, dtype=int)
    for b in range(N_BINS):
        sel = bin_idx == b
        n_per_bin[b] = int(sel.sum())
        if n_per_bin[b] > 0:
            pid_per_bin[b] = float(sw_pid_err[sel].mean())
            unc_per_bin[b] = float(sw_unc_err[sel].mean())
            clp_per_bin[b] = float(sw_clp_err[sel].mean())

    log.info("%-4s %-10s %6s %10s %10s %10s %10s %10s",
             "bin", "θ center", "n_sw", "PID",
             "v2_unc", "v2_clp", "Δunc-PID", "Δclp-PID")
    log.info("-" * 92)
    easy_bins = [0, 1, 8, 9]
    for b in range(N_BINS):
        marker = "  ←easy" if b in easy_bins else ""
        log.info("%-4d %-10.3f %6d %10.3f %10.3f %10.3f %+10.3f %+10.3f%s",
                 b, centers[b], n_per_bin[b], pid_per_bin[b],
                 unc_per_bin[b], clp_per_bin[b],
                 unc_per_bin[b] - pid_per_bin[b],
                 clp_per_bin[b] - pid_per_bin[b], marker)

    # Easy-bin behavior — v2 should produce small corrections (was
    # trained on clipped targets), unlike v1 which over-corrected by
    # 5.8-7.0 µT in these bins.
    log.info("")
    log.info("=== Easy-bin (0,1,8,9) over-correction check vs v1 unclamped ===")
    v1_unclamped_overcorrection = {0: 5.836, 1: 7.030, 8: 6.986, 9: 5.775}
    for b in easy_bins:
        d = unc_per_bin[b] - pid_per_bin[b]
        v1_d = v1_unclamped_overcorrection[b]
        log.info("  bin %d θ=%.3f: PID=%.2f  v2_unc=%.2f  Δ=%+.2f  "
                 "(v1_unc Δ was %+.2f)",
                 b, centers[b], pid_per_bin[b], unc_per_bin[b], d, v1_d)

    # =====================================================================
    # C-4: Dataset A AIC test split
    # =====================================================================
    log.info("")
    log.info("=" * 70)
    log.info("C-4: DATASET A AIC TEST SPLIT")
    log.info("=" * 70)

    with h5py.File(AIC_DS, "r") as h:
        aic_spec = h["test/spectra"][:]
        aic_labels = h["test/labels"][:]
        aic_freq = h["test/frequencies"][:]
    aic_b_true = np.linalg.norm(aic_labels, axis=1) * 1e6  # T → µT

    if AIC_PID.exists():
        # Reuse PID from Phase B's training-time generate_pid_labels
        pid_a = np.load(AIC_PID)
        aic_b_pid = pid_a["test_b_pid_uT"]
        aic_lock = pid_a["test_lock_bins"].astype(np.int64)
        log.info("  Reusing AIC test PID labels: %s", AIC_PID)
    else:
        log.info("  Computing PID baseline on %d AIC test spectra…", aic_spec.shape[0])
        aic_b_pid, aic_lock = run_pid_batch(aic_freq, aic_spec)

    aic_delta = fcnn_predict(model, aic_spec, aic_lock, SIGMA_V2_DATASET_A)
    aic_delta_clp = np.clip(aic_delta, -CLAMP_UT, CLAMP_UT)

    aic_pid_err = np.abs(aic_b_pid - aic_b_true)
    aic_unc_err = np.abs(aic_b_pid + aic_delta - aic_b_true)
    aic_clp_err = np.abs(aic_b_pid + aic_delta_clp - aic_b_true)

    aic_mae_pid = float(aic_pid_err.mean())
    aic_mae_unc = float(aic_unc_err.mean())
    aic_mae_clp = float(aic_clp_err.mean())
    aic_red_unc = (1.0 - aic_mae_unc / aic_mae_pid) * 100.0
    aic_red_clp = (1.0 - aic_mae_clp / aic_mae_pid) * 100.0

    log.info("  n=%d", aic_pid_err.size)
    log.info("  PID baseline       MAE = %.4f µT", aic_mae_pid)
    log.info("  v2 unclamped       MAE = %.4f µT  reduction = %.2f%%",
             aic_mae_unc, aic_red_unc)
    log.info("  v2 CLAMPED ±%.2f   MAE = %.4f µT  reduction = %.2f%%",
             CLAMP_UT, aic_mae_clp, aic_red_clp)
    log.info("  v1 reference (from prior task): unclamped 54.21%% on AIC test")

    # =====================================================================
    # Plot — orientation-binned overlay (v1 vs v2 in easy/hard regimes)
    # =====================================================================
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(centers, pid_per_bin, "s-", color="black", linewidth=1.5,
            label=f"sweep PID baseline (n_total={sw_pid_err.size})")
    ax.plot(centers, unc_per_bin, "x--", color="#1B7B47",
            label="v2 (Dataset A) FCNN+PID UNCLAMPED")
    ax.plot(centers, clp_per_bin, "o-", color="#1B7B47", markerfacecolor="white",
            label=f"v2 (Dataset A) FCNN+PID CLAMPED ±{CLAMP_UT} µT")
    ax.set_xlabel("Polar angle θ (rad)")
    ax.set_ylabel("MAE per bin (µT)")
    ax.set_title("Heading sweep — v2 (Dataset A) vs PID baseline\n"
                 "(σ=%.4f, all 1440 angles)" % SIGMA_V2_DATASET_A,
                 fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper center", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    log.info("Saved figure: %s", OUT_PNG)

    # --- Persist all numbers ---
    np.savez(
        str(OUT_NPZ),
        # Constants
        sigma_v2_dataset_a=np.float64(SIGMA_V2_DATASET_A),
        clamp_uT=np.float64(CLAMP_UT),
        # C-1 val
        val_n=np.asarray(val_pid_err.size),
        val_mae_pid=np.float64(val_mae_pid),
        val_mae_unc=np.float64(val_mae_unc),
        val_mae_clp=np.float64(val_mae_clp),
        val_red_unc=np.float64(val_red_unc),
        val_red_clp=np.float64(val_red_clp),
        val_n_clipped=np.asarray(val_n_clipped),
        val_delta=val_delta,
        val_delta_clp=val_delta_clp,
        # C-2/3 sweep
        sweep_n=np.asarray(sw_pid_err.size),
        sweep_mae_pid=np.float64(sw_mae_pid),
        sweep_mae_unc=np.float64(sw_mae_unc),
        sweep_mae_clp=np.float64(sw_mae_clp),
        sweep_red_unc=np.float64(sw_red_unc),
        sweep_red_clp=np.float64(sw_red_clp),
        sweep_n_clipped=np.asarray(sw_n_clipped),
        sweep_delta=sw_delta,
        sweep_delta_clp=sw_delta_clp,
        sweep_theta_rad=sw_theta,
        bin_edges=edges,
        bin_centers=centers,
        bin_n=n_per_bin,
        bin_pid=pid_per_bin,
        bin_unc=unc_per_bin,
        bin_clp=clp_per_bin,
        # C-4 AIC test
        aic_n=np.asarray(aic_pid_err.size),
        aic_mae_pid=np.float64(aic_mae_pid),
        aic_mae_unc=np.float64(aic_mae_unc),
        aic_mae_clp=np.float64(aic_mae_clp),
        aic_red_unc=np.float64(aic_red_unc),
        aic_red_clp=np.float64(aic_red_clp),
    )
    log.info("Saved numbers: %s", OUT_NPZ)


if __name__ == "__main__":
    main()
