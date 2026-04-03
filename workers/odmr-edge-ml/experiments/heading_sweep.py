#!/usr/bin/env python3
"""360-degree heading error sweep: PID-only vs FCNN+PID in the (1,-1,0) plane.

Rotates a 50 µT B-field through 1440 angles (0.25° steps) in the
crystallographic plane with normal [1,-1,0], generating corrupted ODMR
spectra at each angle. Compares PID-only and FCNN+PID magnitude errors.

Usage:
    python experiments/heading_sweep.py
"""

from __future__ import annotations

import logging
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import torch

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")
warnings.filterwarnings("ignore", message="Grid aliasing risk")

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import OUNoiseConfig, SimulationConfig
from nv_sensor_sim.physics.lineshape import corrupt_spectrum
from nv_sensor_sim.physics.noise_injection import sample_ou_trajectory_pair

from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID
from odmr_edge_ml.models.fcnn import OdmrFCNN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
N_ANGLES = 1440
B_MAG_T = 50e-6  # 50 µT
B_MAG_UT = 50.0
FREQ_RANGE_HZ = (2.82e9, 2.92e9)
N_FREQ_POINTS = 100
SEED = 42

# Sweep plane basis vectors (normal = [1,-1,0])
E1 = np.array([0.0, 0.0, 1.0])
E2 = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)

# Corruption parameters (fixed, mid-range)
P1_PPM = 50.0
TEMPERATURE_K = 300.0
B1_GRADIENT_FRAC = 0.15
B_PERP_T = 0.0
N_SPATIAL_BINS = 10

# Anchor Gaussian sigma (must match training)
ANCHOR_SIGMA = 1.5

# Paths
CKPT_PATH = Path(__file__).resolve().parent / "scalar_residual/fcnn/checkpoints/best_model.pt"
OUTPUT_PATH = Path(__file__).resolve().parent / "heading_sweep_results.npz"

# Cascaded OU noise config (matching production dataset generation)
OU_CONFIG = OUNoiseConfig(
    alpha_B1=-0.03,
    T_mean_C=20.0,
    delta_T_orb_C=15.0,
    tau_orb_s=5400.0,
    B1_nominal=1.0,
    theta_T=0.1,
    sigma_T=0.5,
    theta_B1=1.0,
    sigma_B1=0.05,
    trajectory_dt_s=1.0,
    enable_thermal_noise=True,
    enable_mw_noise=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_fcnn(ckpt_path: Path) -> OdmrFCNN:
    """Load trained FCNN from QAT checkpoint, stripping observer keys."""
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    sd = ckpt["model_state_dict"]
    skip = ("fake_quant", "activation_post_process", "observer")
    clean_sd = {k: v for k, v in sd.items() if not any(p in k for p in skip)}
    model = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    model.load_state_dict(clean_sd, strict=True)
    model.eval()
    return model


def preprocess_for_fcnn(spectrum: np.ndarray, lock_bin: int) -> torch.Tensor:
    """Build 200-dim FCNN input from raw spectrum and PID lock-point.

    Channel 0: spectrum normalized to [-1, 1] (per-spectrum min-max).
    Channel 1: Gaussian anchor at lock_bin with sigma=1.5.
    """
    s_min, s_max = spectrum.min(), spectrum.max()
    denom = s_max - s_min if s_max != s_min else 1.0
    spec_norm = 2.0 * (spectrum - s_min) / denom - 1.0

    bins = np.arange(len(spectrum))
    anchor = np.exp(-0.5 * ((bins - lock_bin) / ANCHOR_SIGMA) ** 2)

    combined = np.concatenate([spec_norm, anchor])
    return torch.from_numpy(combined).float().unsqueeze(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not CKPT_PATH.exists():
        log.error("FCNN checkpoint not found: %s", CKPT_PATH)
        log.error("Run experiments/scalar_residual_comparison.py first.")
        sys.exit(1)

    log.info("=" * 60)
    log.info("360-DEGREE HEADING ERROR SWEEP")
    log.info("=" * 60)
    log.info("  B magnitude: %.0f µT", B_MAG_UT)
    log.info("  Angles: %d (%.2f° step)", N_ANGLES, 360.0 / N_ANGLES)
    log.info("  Plane normal: [1,-1,0]")
    log.info("  Corruption: P1=%.0f ppm, T=%.0f K, B1_grad=%.2f", P1_PPM, TEMPERATURE_K, B1_GRADIENT_FRAC)

    # -- SimOS adapter --
    config = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, B_MAG_T]),
        temperature_K=TEMPERATURE_K,
        mw_freq_range_Hz=FREQ_RANGE_HZ,
        n_freq_points=N_FREQ_POINTS,
        p1_concentration_ppm=P1_PPM,
        include_nitrogen=False,
        use_optics=False,
    )
    adapter = SimOSAdapter(config)

    # -- MW power trajectory (OU noise) --
    _, b1_trajectory = sample_ou_trajectory_pair(OU_CONFIG, N_ANGLES, seed=SEED)
    log.info("  MW power range: [%.3f, %.3f]", b1_trajectory.min(), b1_trajectory.max())

    # -- Load FCNN --
    fcnn = load_fcnn(CKPT_PATH)
    log.info("  FCNN loaded: %d params", sum(p.numel() for p in fcnn.parameters()))

    # -- Pre-allocate arrays --
    angles_deg = np.linspace(0.0, 360.0, N_ANGLES, endpoint=False)
    angles_rad = np.deg2rad(angles_deg)

    b_vecs = np.zeros((N_ANGLES, 3))
    spectra = np.zeros((N_ANGLES, N_FREQ_POINTS))
    pid_estimates_uT = np.zeros(N_ANGLES)
    pid_lock_bins = np.zeros(N_ANGLES, dtype=int)
    pid_n_dips = np.zeros(N_ANGLES, dtype=int)
    fcnn_delta_b_uT = np.zeros(N_ANGLES)
    mw_power_scales = np.zeros(N_ANGLES)

    # -- Initialize PID with a probe spectrum to get frequencies --
    freqs_init, _ = adapter.generate_odmr_spectrum(
        temperature_K=TEMPERATURE_K, p1_ppm=P1_PPM, mw_scale=1.0,
    )
    frequencies = freqs_init
    pid = DerivativeZeroCrossingPID(frequencies)

    # -- Sweep --
    t0 = time.monotonic()

    for i in range(N_ANGLES):
        theta = angles_rad[i]
        B_vec = B_MAG_T * (np.cos(theta) * E1 + np.sin(theta) * E2)
        b_vecs[i] = B_vec
        config.B_field_T = B_vec

        mw_scale = float(b1_trajectory[i])
        mw_power_scales[i] = mw_scale

        _, signal, _ = corrupt_spectrum(
            adapter, config,
            b1_gradient_frac=B1_GRADIENT_FRAC,
            b_perp_T=B_PERP_T,
            p1_ppm=P1_PPM,
            n_spatial_bins=N_SPATIAL_BINS,
            mw_power_scale=mw_scale,
        )

        spectra[i] = signal

        result = pid.estimate(signal)
        pid_estimates_uT[i] = result.b_mag_uT
        pid_lock_bins[i] = result.lock_bin
        pid_n_dips[i] = result.n_dips

        x = preprocess_for_fcnn(signal, result.lock_bin)
        with torch.no_grad():
            delta_b = fcnn(x).item()
        fcnn_delta_b_uT[i] = delta_b

        if (i + 1) % 360 == 0:
            log.info("  %d / %d angles (%.0f°)", i + 1, N_ANGLES, angles_deg[i])

    elapsed = time.monotonic() - t0

    # -- Compute errors --
    pid_error_uT = np.abs(pid_estimates_uT - B_MAG_UT)
    cnn_pid_estimates_uT = pid_estimates_uT + fcnn_delta_b_uT
    cnn_error_uT = np.abs(cnn_pid_estimates_uT - B_MAG_UT)

    # -- Save --
    np.savez(
        OUTPUT_PATH,
        angles_deg=angles_deg,
        b_vecs_T=b_vecs,
        frequencies_Hz=frequencies,
        spectra=spectra,
        pid_estimates_uT=pid_estimates_uT,
        pid_lock_bins=pid_lock_bins,
        pid_n_dips=pid_n_dips,
        fcnn_delta_b_uT=fcnn_delta_b_uT,
        cnn_pid_estimates_uT=cnn_pid_estimates_uT,
        pid_error_uT=pid_error_uT,
        cnn_error_uT=cnn_error_uT,
        mw_power_scales=mw_power_scales,
        b_mag_true_uT=np.float64(B_MAG_UT),
        seed=np.int64(SEED),
    )

    # -- Report --
    log.info("")
    log.info("=" * 60)
    log.info("HEADING SWEEP RESULTS")
    log.info("=" * 60)
    log.info("  Generation time: %.1fs (%.1f ms/angle)", elapsed, 1000 * elapsed / N_ANGLES)
    log.info("")
    log.info("  %-20s %10s %10s %10s %10s", "", "MAE", "Max", "P50", "P95")
    log.info("  " + "-" * 60)
    log.info("  %-20s %9.3f %9.3f %9.3f %9.3f",
             "PID-only (µT)",
             pid_error_uT.mean(), pid_error_uT.max(),
             np.percentile(pid_error_uT, 50), np.percentile(pid_error_uT, 95))
    log.info("  %-20s %9.3f %9.3f %9.3f %9.3f",
             "FCNN+PID (µT)",
             cnn_error_uT.mean(), cnn_error_uT.max(),
             np.percentile(cnn_error_uT, 50), np.percentile(cnn_error_uT, 95))
    log.info("")
    improvement = (1 - cnn_error_uT.mean() / pid_error_uT.mean()) * 100
    log.info("  Heading error reduction: %.1f%%", improvement)
    log.info("  PID dip stats: 0-dip=%d, 1-dip=%d, 2-dip=%d",
             (pid_n_dips == 0).sum(), (pid_n_dips == 1).sum(), (pid_n_dips == 2).sum())
    log.info("  Results saved: %s", OUTPUT_PATH)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
