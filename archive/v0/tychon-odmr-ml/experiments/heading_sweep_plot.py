#!/usr/bin/env python3
"""Dual-panel heading sweep figure: error curves + ODMR spectrogram."""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).resolve().parent
NPZ = HERE / "heading_sweep_results.npz"

# ── Load data ──────────────────────────────────────────────────────
d = np.load(NPZ)
angles = d["angles_deg"]
pid_err = d["pid_error_uT"]
cnn_err = d["cnn_error_uT"]
spectra = d["spectra"]
freqs_ghz = d["frequencies_Hz"] / 1e9

# ── Key stats ──────────────────────────────────────────────────────
pid_mae = pid_err.mean()
cnn_mae = cnn_err.mean()
reduction = (1 - cnn_mae / pid_mae) * 100
print(f"PID-only  MAE: {pid_mae:.2f} µT   max: {pid_err.max():.2f} µT")
print(f"FCNN+PID  MAE: {cnn_mae:.2f} µT   max: {cnn_err.max():.2f} µT")
print(f"Reduction: {reduction:.1f}%")

# ── Degeneracy angles ─────────────────────────────────────────────
DEGEN = [0, 54.7, 90, 125.3, 180, 234.7, 270, 305.3, 360]

# ── Figure ─────────────────────────────────────────────────────────
fig, (ax_err, ax_spec) = plt.subplots(
    2, 1, figsize=(12, 6), sharex=True,
    gridspec_kw={"height_ratios": [1, 1], "hspace": 0.08},
)

# Top: heading error curves
ax_err.plot(angles, pid_err, color="red", linewidth=0.8, alpha=0.85, label=f"PID-only (MAE {pid_mae:.1f} µT)")
ax_err.plot(angles, cnn_err, color="#2176FF", linewidth=0.8, alpha=0.85, label=f"FCNN+PID (MAE {cnn_mae:.1f} µT)")
for a in DEGEN:
    ax_err.axvline(a, color="gray", linestyle=":", linewidth=0.5, alpha=0.6)
ax_err.set_ylabel("Heading Error (µT)")
ax_err.legend(loc="upper right", fontsize=9, framealpha=0.9)
ax_err.set_title("Heading Error Sweep: PID-only vs FCNN+PID Hybrid", fontsize=13, fontweight="bold")
ax_err.set_xlim(0, 360)

# Bottom: ODMR spectrogram
extent = [angles[0], angles[-1], freqs_ghz[0], freqs_ghz[-1]]
im = ax_spec.imshow(
    spectra.T, aspect="auto", origin="lower", cmap="inferno",
    extent=extent, interpolation="bilinear",
)
for a in DEGEN:
    ax_spec.axvline(a, color="white", linestyle=":", linewidth=0.5, alpha=0.5)
ax_spec.set_xlabel("Rotation Angle (°)")
ax_spec.set_ylabel("Frequency (GHz)")
cbar = fig.colorbar(im, ax=ax_spec, pad=0.01, aspect=30)
cbar.set_label("ODMR Signal", fontsize=9)

fig.align_ylabels([ax_err, ax_spec])

# ── Save ───────────────────────────────────────────────────────────
out_png = HERE / "heading_sweep_figure.png"
out_pdf = HERE / "heading_sweep_figure.pdf"
fig.savefig(out_png, dpi=300, bbox_inches="tight")
fig.savefig(out_pdf, bbox_inches="tight")
print(f"Saved: {out_png}")
print(f"Saved: {out_pdf}")
