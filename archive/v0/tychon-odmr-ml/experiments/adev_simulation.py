#!/usr/bin/env python3
"""OADEV stability figure: PID-only vs FCNN+PID over 3 LEO orbits (16,200 s).

Simulates a tumbling satellite NV diamond magnetometer with cascaded
OU noise (temperature + MW power) and computes overlapping Allan deviation.

Usage:
    pip install allantools  # one-time
    python experiments/adev_simulation.py
"""

from __future__ import annotations

import logging
import sys
import time
import warnings
from pathlib import Path

import allantools
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")
warnings.filterwarnings("ignore", message="Grid aliasing risk")

from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
from tychon_nv_sim.config import OUNoiseConfig, SimulationConfig
from tychon_nv_sim.physics.lineshape import corrupt_spectrum
from tychon_nv_sim.physics.noise_injection import sample_ou_trajectory_pair

from tychon_odmr_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID
from tychon_odmr_ml.models.fcnn import OdmrFCNN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
N_STEPS = 16_200            # 3 LEO orbits x 5400 s
DT_S = 1.0                  # 1 Hz measurement rate
ORBIT_PERIOD_S = 5400.0     # 90-min LEO orbit
B_MAG_T = 50e-6             # 50 uT in Tesla
B_MAG_UT = 50.0             # 50 uT
TUMBLE_RATE_DEG_S = 360.0 / ORBIT_PERIOD_S  # 0.0667 deg/s (1 rotation/orbit)
FREQ_RANGE_HZ = (2.82e9, 2.92e9)
N_FREQ_POINTS = 100
SEED = 42

# Sweep plane basis (same as heading_sweep — normal [1,-1,0])
E1 = np.array([0.0, 0.0, 1.0])
E2 = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)

# Corruption parameters
P1_PPM = 50.0
B1_GRADIENT_FRAC = 0.15
B_PERP_T = 0.0
N_SPATIAL_BINS = 10
ANCHOR_SIGMA = 1.5

# Cascaded OU noise config (matching heading_sweep.py / production dataset)
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
    trajectory_dt_s=DT_S,
    enable_thermal_noise=True,
    enable_mw_noise=True,
)

# Paths
CKPT_PATH = Path(__file__).resolve().parent / "scalar_residual/fcnn/checkpoints/best_model.pt"
OUTPUT_NPZ = Path(__file__).resolve().parent / "adev_results.npz"
OUTPUT_PNG = Path(__file__).resolve().parent / "adev_figure.png"
OUTPUT_PDF = Path(__file__).resolve().parent / "adev_figure.pdf"


# ---------------------------------------------------------------------------
# Helpers (duplicated from heading_sweep.py — experiment scripts, not library)
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
    """Build 200-dim FCNN input: spectrum[-1,1] || Gaussian anchor."""
    s_min, s_max = spectrum.min(), spectrum.max()
    denom = s_max - s_min if s_max != s_min else 1.0
    spec_norm = 2.0 * (spectrum - s_min) / denom - 1.0

    bins = np.arange(len(spectrum))
    anchor = np.exp(-0.5 * ((bins - lock_bin) / ANCHOR_SIGMA) ** 2)

    combined = np.concatenate([spec_norm, anchor])
    return torch.from_numpy(combined).float().unsqueeze(0)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
def simulate() -> dict[str, np.ndarray]:
    """Run 16,200-second time series with cascaded OU noise + satellite tumble."""
    if not CKPT_PATH.exists():
        log.error("FCNN checkpoint not found: %s", CKPT_PATH)
        sys.exit(1)

    # -- SimOS adapter --
    config = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, B_MAG_T]),
        temperature_K=293.15,  # will be overwritten per-step
        mw_freq_range_Hz=FREQ_RANGE_HZ,
        n_freq_points=N_FREQ_POINTS,
        p1_concentration_ppm=P1_PPM,
        include_nitrogen=False,
        use_optics=False,
    )
    adapter = SimOSAdapter(config)

    # -- OU noise trajectories (BOTH T and B1, unlike heading_sweep which discards T) --
    t_traj_K, b1_trajectory = sample_ou_trajectory_pair(OU_CONFIG, N_STEPS, seed=SEED)
    log.info("  T range: [%.1f, %.1f] K", t_traj_K.min(), t_traj_K.max())
    log.info("  B1 range: [%.3f, %.3f]", b1_trajectory.min(), b1_trajectory.max())

    # -- Load FCNN --
    fcnn = load_fcnn(CKPT_PATH)
    log.info("  FCNN loaded: %d params", sum(p.numel() for p in fcnn.parameters()))

    # -- Frequencies from probe spectrum --
    freqs_init, _ = adapter.generate_odmr_spectrum(
        temperature_K=293.15, p1_ppm=P1_PPM, mw_scale=1.0,
    )
    pid = DerivativeZeroCrossingPID(freqs_init)

    # -- Pre-allocate --
    time_s = np.arange(N_STEPS, dtype=np.float64) * DT_S
    angles_deg = TUMBLE_RATE_DEG_S * time_s  # 3 full rotations over 16200s
    angles_rad = np.deg2rad(angles_deg)

    pid_estimates_uT = np.zeros(N_STEPS)
    fcnn_delta_b_uT = np.zeros(N_STEPS)

    # -- Main loop --
    t0 = time.monotonic()
    for i in range(N_STEPS):
        # Satellite tumble: evolve heading angle
        theta = angles_rad[i]
        B_vec = B_MAG_T * (np.cos(theta) * E1 + np.sin(theta) * E2)
        config.B_field_T = B_vec

        # OU noise: update temperature for this timestep
        config.temperature_K = float(t_traj_K[i])
        mw_scale = float(b1_trajectory[i])

        # Generate corrupted ODMR spectrum
        _, signal, _ = corrupt_spectrum(
            adapter, config,
            b1_gradient_frac=B1_GRADIENT_FRAC,
            b_perp_T=B_PERP_T,
            p1_ppm=P1_PPM,
            n_spatial_bins=N_SPATIAL_BINS,
            mw_power_scale=mw_scale,
        )

        # PID estimate
        result = pid.estimate(signal)
        pid_estimates_uT[i] = result.b_mag_uT

        # FCNN correction
        x = preprocess_for_fcnn(signal, result.lock_bin)
        with torch.no_grad():
            delta_b = fcnn(x).item()
        fcnn_delta_b_uT[i] = delta_b

        if (i + 1) % 5400 == 0:
            log.info("  Orbit %d / 3 complete (%d s)", (i + 1) // 5400, i + 1)

    elapsed = time.monotonic() - t0
    log.info("  Simulation: %.1fs (%.1f ms/step)", elapsed, 1000 * elapsed / N_STEPS)

    # -- Compute error time series (signed, for OADEV) --
    cnn_pid_estimates_uT = pid_estimates_uT + fcnn_delta_b_uT
    pid_error_uT = pid_estimates_uT - B_MAG_UT      # signed error
    cnn_error_uT = cnn_pid_estimates_uT - B_MAG_UT  # signed error

    return {
        "time_s": time_s,
        "angles_deg": angles_deg,
        "t_traj_K": t_traj_K,
        "b1_trajectory": b1_trajectory,
        "pid_estimates_uT": pid_estimates_uT,
        "cnn_pid_estimates_uT": cnn_pid_estimates_uT,
        "pid_error_uT": pid_error_uT,
        "cnn_error_uT": cnn_error_uT,
        "fcnn_delta_b_uT": fcnn_delta_b_uT,
        "b_mag_true_uT": np.float64(B_MAG_UT),
        "seed": np.int64(SEED),
    }


# ---------------------------------------------------------------------------
# Allan Deviation
# ---------------------------------------------------------------------------
def compute_adev(
    pid_error_uT: np.ndarray,
    cnn_error_uT: np.ndarray,
) -> dict[str, np.ndarray]:
    """Compute overlapping Allan deviation for both error time series."""
    taus_pid, adev_pid, _, _ = allantools.oadev(
        pid_error_uT, rate=1.0 / DT_S, data_type="freq", taus="octave",
    )
    taus_cnn, adev_cnn, _, _ = allantools.oadev(
        cnn_error_uT, rate=1.0 / DT_S, data_type="freq", taus="octave",
    )

    # Shot noise reference: tau^(-1/2) anchored at PID ADEV(tau=1)
    adev_at_1 = np.interp(1.0, taus_pid, adev_pid)
    ref_taus = np.logspace(-0.5, np.log10(taus_pid.max()), 200)
    ref_adev = adev_at_1 * ref_taus ** (-0.5)

    return {
        "taus_pid": taus_pid, "adev_pid": adev_pid,
        "taus_cnn": taus_cnn, "adev_cnn": adev_cnn,
        "ref_taus": ref_taus, "ref_adev": ref_adev,
    }


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------
def plot_adev(ad: dict[str, np.ndarray]) -> None:
    """Generate log-log OADEV figure with AI correction margin."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Main curves
    ax.loglog(ad["taus_pid"], ad["adev_pid"], "o-", color="red", linewidth=1.5,
              markersize=4, label="PID-only", zorder=3)
    ax.loglog(ad["taus_cnn"], ad["adev_cnn"], "s-", color="#2176FF", linewidth=1.5,
              markersize=4, label="FCNN+PID", zorder=3)

    # Shot noise reference
    ax.loglog(ad["ref_taus"], ad["ref_adev"], "--", color="black", linewidth=1.0,
              alpha=0.6, label=r"$\tau^{-1/2}$ (white noise)")

    # AI correction margin (shaded green between curves)
    adev_cnn_interp = np.interp(ad["taus_pid"], ad["taus_cnn"], ad["adev_cnn"])
    ax.fill_between(ad["taus_pid"], adev_cnn_interp, ad["adev_pid"],
                    where=ad["adev_pid"] > adev_cnn_interp,
                    alpha=0.15, color="green", label="AI correction margin")

    # Vertical markers
    for tau_mark, lbl in [(1000, r"$\tau_{\mathrm{thermal}}$=1000s"),
                           (2700, r"$T_{\mathrm{orb}}/2$=2700s")]:
        ax.axvline(tau_mark, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
        ylims = ax.get_ylim()
        ax.annotate(lbl, xy=(tau_mark, ylims[1]), xytext=(5, -15),
                    textcoords="offset points", fontsize=8, color="gray",
                    verticalalignment="top")

    ax.set_xlabel("Averaging Time τ (s)", fontsize=12)
    ax.set_ylabel("Overlapping Allan Deviation (µT)", fontsize=12)
    ax.set_title("Measurement Stability: PID-only vs FCNN+PID Hybrid\n"
                 "(3 LEO orbits, 50 µT, satellite tumble)", fontsize=13, fontweight="bold")
    ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
    ax.grid(True, which="both", alpha=0.3)

    fig.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight")
    fig.savefig(OUTPUT_PDF, bbox_inches="tight")
    log.info("Saved: %s", OUTPUT_PNG)
    log.info("Saved: %s", OUTPUT_PDF)


def print_stats(ad: dict[str, np.ndarray]) -> None:
    """Print OADEV at key tau values."""
    log.info("")
    log.info("%-8s  %12s  %12s  %12s", "tau (s)", "PID OADEV", "CNN OADEV", "Improvement")
    log.info("-" * 50)
    for tau in [1, 10, 100, 1000, 2700]:
        pid_val = np.interp(tau, ad["taus_pid"], ad["adev_pid"])
        cnn_val = np.interp(tau, ad["taus_cnn"], ad["adev_cnn"])
        improv = (1 - cnn_val / pid_val) * 100
        log.info("%-8d  %10.4f µT  %10.4f µT  %10.1f%%", tau, pid_val, cnn_val, improv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 60)
    log.info("ALLAN DEVIATION SIMULATION: PID-only vs FCNN+PID")
    log.info("=" * 60)
    log.info("  Duration: %d s (%d orbits)", N_STEPS, N_STEPS // 5400)
    log.info("  Tumble rate: %.4f deg/s (1 rotation/orbit)", TUMBLE_RATE_DEG_S)
    log.info("  B magnitude: %.0f µT", B_MAG_UT)

    data = simulate()

    ad = compute_adev(data["pid_error_uT"], data["cnn_error_uT"])

    # Save raw data + OADEV results
    np.savez(OUTPUT_NPZ, **data,
             taus_pid=ad["taus_pid"], adev_pid=ad["adev_pid"],
             taus_cnn=ad["taus_cnn"], adev_cnn=ad["adev_cnn"])
    log.info("Saved: %s", OUTPUT_NPZ)

    plot_adev(ad)
    print_stats(ad)

    log.info("=" * 60)


if __name__ == "__main__":
    main()
