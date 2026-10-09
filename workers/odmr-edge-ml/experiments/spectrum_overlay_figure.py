#!/usr/bin/env python3
"""Publication figure: clean vs noise-corrupted CW-ODMR spectrum overlay."""

import numpy as np
import h5py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
DATASET = HERE.parent / "data/production_50k/dataset.h5"
OUT_PDF = HERE / "spectrum_overlay_figure.pdf"
OUT_PNG = HERE / "spectrum_overlay_figure.png"

# ── Load corrupted spectrum ───────────────────────────────────────────
# Index 627: B=69.8µT, P1=286ppm, b1_grad=0.297 — strong features
IDX = 627
with h5py.File(DATASET, "r") as f:
    spectrum_corr = np.asarray(f["train/spectra"][IDX])
    freqs_hz = np.asarray(f["train/frequencies"][:])
    labels = np.asarray(f["train/labels"][IDX])
    cp = np.asarray(f["train/corruption_params"][IDX])

freqs_ghz = freqs_hz / 1e9
B_field = labels  # in Tesla
print(f"Corrupted: B={np.linalg.norm(B_field)*1e6:.1f} µT, "
      f"P1={cp[0]:.0f} ppm, b1_grad={cp[2]:.3f}, T={cp[1]:.1f} K")

# ── Generate clean Lorentzian spectrum ────────────────────────────────
from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig

config = SimulationConfig(
    B_field_T=B_field,
    temperature_K=293.15,
    mw_freq_range_Hz=(2.82e9, 2.92e9),
    n_freq_points=500,
    p1_concentration_ppm=15.0,
    include_nitrogen=False,
    use_optics=False,
)
adapter = SimOSAdapter(config)
freqs_clean_hz, pl_clean = adapter.generate_odmr_spectrum(
    B_field=B_field, p1_ppm=15.0, mw_scale=1.0,
)
freqs_clean_ghz = freqs_clean_hz / 1e9

print(f"Clean dip: {(1 - pl_clean.min()) * 100:.2f}%  "
      f"Corrupted dip: {(1 - spectrum_corr.min()) * 100:.2f}%")

# ── Compute FWHM of corrupted dip ────────────────────────────────────
dip_idx = np.argmin(spectrum_corr)
dip_val = spectrum_corr[dip_idx]
half_level = 0.5 * (1.0 + dip_val)
above = spectrum_corr > half_level
edges = np.diff(above.astype(int))
fwhm_left = freqs_ghz[np.where(edges == -1)[0][0]]
fwhm_right = freqs_ghz[np.where(edges == 1)[0][-1]]
fwhm_mhz = (fwhm_right - fwhm_left) * 1e3
print(f"Corrupted FWHM: {fwhm_mhz:.0f} MHz")

# ── Figure: two panels (spectrum + baseline zoom) ─────────────────────
fig, (ax, ax_zoom) = plt.subplots(
    2, 1, figsize=(7.5, 5.5),
    gridspec_kw={"height_ratios": [3, 1], "hspace": 0.42},
)

# ── Main panel ────────────────────────────────────────────────────────
ax.plot(freqs_clean_ghz, pl_clean, color="#2176FF", linewidth=1.6,
        label="Clean Lorentzian", zorder=3)
ax.plot(freqs_ghz, spectrum_corr, color="#E63946", linewidth=1.2,
        alpha=0.9, label="Noise-corrupted", zorder=2)

# Annotation style
ann_kw = dict(fontsize=8.5, fontweight="bold", color="#333333")
arrow_kw = dict(arrowstyle="-|>", color="#333333", lw=1.2, mutation_scale=10)

# (a) Fano asymmetry — point to the asymmetric right flank
asym_pt = dip_idx + 6
ax.annotate(
    "(a) Fano asymmetry",
    xy=(freqs_ghz[asym_pt], spectrum_corr[asym_pt]),
    xytext=(2.895, 0.976),
    **ann_kw,
    arrowprops=dict(**arrow_kw, connectionstyle="arc3,rad=0.2"),
)

# (b) Thermal broadening — bracket at half-max showing corrupted FWHM
bkt_y = half_level
ax.plot([fwhm_left, fwhm_right], [bkt_y, bkt_y],
        color="#555555", lw=1.2, zorder=4)
for xv in (fwhm_left, fwhm_right):
    ax.plot([xv, xv], [bkt_y - 0.0012, bkt_y + 0.0012],
            color="#555555", lw=1.2, zorder=4)
ax.text(
    fwhm_left - 0.003, bkt_y,
    f"(b) thermal broadening\n      ({fwhm_mhz:.0f} MHz FWHM)",
    fontsize=7.5, ha="right", va="center", color="#333333", fontweight="bold",
)

ax.set_xlabel("Frequency (GHz)", fontsize=10.5)
ax.set_ylabel("Normalized fluorescence", fontsize=10.5)
ax.set_title("Synthetic CW-ODMR spectrum: clean vs noise-corrupted",
             fontsize=12, fontweight="bold", pad=10)
ax.legend(loc="lower left", fontsize=9, frameon=True, framealpha=0.9,
          edgecolor="#cccccc")
ax.set_xlim(freqs_ghz[0], freqs_ghz[-1])
ax.set_ylim(0.966, 1.003)
ax.tick_params(labelsize=9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_linewidth(0.6)
ax.spines["bottom"].set_linewidth(0.6)

# ── Baseline zoom panel (shot noise) ─────────────────────────────────
# Show right-wing baseline where corrupted deviates from clean
zoom_sl = slice(82, 100)
ax_zoom.plot(freqs_ghz[zoom_sl], spectrum_corr[zoom_sl],
             color="#E63946", lw=1.0, marker="o", ms=3, zorder=2,
             label="Noise-corrupted")
clean_interp = np.interp(freqs_ghz[zoom_sl], freqs_clean_ghz, pl_clean)
ax_zoom.plot(freqs_ghz[zoom_sl], clean_interp,
             color="#2176FF", lw=1.2, zorder=3, label="Clean Lorentzian")

# Shade the gap between clean and corrupted
ax_zoom.fill_between(
    freqs_ghz[zoom_sl], spectrum_corr[zoom_sl], clean_interp,
    color="#E63946", alpha=0.12, zorder=1,
)

ax_zoom.set_xlabel("Frequency (GHz)", fontsize=10.5)
ax_zoom.set_ylabel("Fluorescence", fontsize=10.5)
ax_zoom.set_title("(c) Baseline zoom — shot noise + MW power drift",
                   fontsize=9.5, fontweight="bold", color="#333333", pad=6)
ax_zoom.set_xlim(freqs_ghz[82], freqs_ghz[99])
ymin_z = min(spectrum_corr[zoom_sl].min(), clean_interp.min())
ymax_z = max(spectrum_corr[zoom_sl].max(), clean_interp.max())
margin = (ymax_z - ymin_z) * 0.3
ax_zoom.set_ylim(ymin_z - margin, ymax_z + margin)
ax_zoom.tick_params(labelsize=8)
ax_zoom.legend(fontsize=7.5, loc="lower left", framealpha=0.9)
ax_zoom.spines["top"].set_visible(False)
ax_zoom.spines["right"].set_visible(False)
ax_zoom.spines["left"].set_linewidth(0.6)
ax_zoom.spines["bottom"].set_linewidth(0.6)

# Connect zoom region to main plot
ax.axvspan(freqs_ghz[82], freqs_ghz[99], color="#f5f5f5", alpha=0.6, zorder=0)

# ── Save ──────────────────────────────────────────────────────────────
fig.savefig(OUT_PDF, bbox_inches="tight")
fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
print(f"\nSaved: {OUT_PDF}")
print(f"Saved: {OUT_PNG}")
