#!/usr/bin/env python3
"""Build the visual sanity-check Jupyter notebook programmatically."""

import nbformat

nb = nbformat.v4.new_notebook()
nb.metadata["kernelspec"] = {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3",
}

cells = []

# Cell 0: Title
cells.append(nbformat.v4.new_markdown_cell("""\
# Visual Sanity Check — CW ODMR Synthetic Spectra

NV Sensor Sim — ODMR validation notebook.

Verifies that the simulator produces physically plausible ODMR spectra across
the P1 concentration and temperature parameter space, demonstrates asymmetric
lineshape corruption, and overlays against experimental Zenodo data."""))

# Cell 1: Imports
cells.append(nbformat.v4.new_code_cell("""\
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.signal import find_peaks

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.physics.lineshape import corrupt_spectrum
from nv_sensor_sim.physics.parameters import compute_linewidth
from nv_sensor_sim.validation.reference_comparison import (
    load_experimental_odmr,
    compute_spectral_mse,
)

plt.rcParams.update({"figure.dpi": 120, "font.size": 10})"""))

# Cell 2: Generate 6 spectra
cells.append(nbformat.v4.new_code_cell("""\
p1_values = [1, 100, 300]
temp_values = [280, 320]
n_freq = 2000

base_config = SimulationConfig(
    B_field_T=np.array([0.0, 0.0, 50e-6]),
    n_freq_points=n_freq,
    mw_freq_range_Hz=(2.82e9, 2.92e9),
    include_nitrogen=False,
    use_optics=False,
)
adapter = SimOSAdapter(base_config)

results = {}
for p1 in p1_values:
    for T in temp_values:
        adapter.config.temperature_K = T
        adapter.config.p1_concentration_ppm = p1
        freqs, signal = adapter.generate_odmr_spectrum(p1_ppm=p1, temperature_K=T)
        results[(p1, T)] = (freqs, signal)

print(f"Generated {len(results)} spectra")"""))

# Cell 3: Plot 2x3 grid
cells.append(nbformat.v4.new_code_cell("""\
fig, axes = plt.subplots(2, 3, figsize=(14, 7), sharex=True)
for col, p1 in enumerate(p1_values):
    for row, T in enumerate(temp_values):
        ax = axes[row, col]
        freqs, signal = results[(p1, T)]
        ax.plot(freqs / 1e9, signal, "b-", linewidth=0.8)
        ax.set_title(f"P1={p1} ppm, T={T} K")
        if row == 1:
            ax.set_xlabel("Frequency (GHz)")
        if col == 0:
            ax.set_ylabel("PL (normalized)")
fig.suptitle("CW ODMR Spectra: P1 Concentration × Temperature", y=1.02, fontsize=14)
fig.tight_layout()
plt.show()"""))

# Cell 4: Asymmetry header
cells.append(nbformat.v4.new_markdown_cell("""\
## Asymmetric Lineshape Corruption

Progressive application of B1 gradient and transverse field corruption
at P1=50 ppm, T=300 K. Shows how corruption channels distort ideal Lorentzian profiles."""))

# Cell 5: Generate 3 asymmetry spectra
cells.append(nbformat.v4.new_code_cell("""\
config_asym = SimulationConfig(
    B_field_T=np.array([0.0, 0.0, 50e-6]),
    n_freq_points=n_freq,
    mw_freq_range_Hz=(2.82e9, 2.92e9),
    temperature_K=300.0,
    p1_concentration_ppm=50.0,
    include_nitrogen=False,
    use_optics=False,
)
adapter_asym = SimOSAdapter(config_asym)

# No corruption
freqs_clean, sig_clean = adapter_asym.generate_odmr_spectrum(p1_ppm=50.0)

# B1 gradient only
freqs_b1, sig_b1, _ = corrupt_spectrum(
    adapter_asym, config_asym, b1_gradient_frac=0.2, b_perp_T=0.0, p1_ppm=50.0
)

# B1 gradient + B_perp
freqs_full, sig_full, _ = corrupt_spectrum(
    adapter_asym, config_asym, b1_gradient_frac=0.2, b_perp_T=30e-6, p1_ppm=50.0
)

print("Generated 3 asymmetry spectra")"""))

# Cell 6: Overlay plot
cells.append(nbformat.v4.new_code_cell("""\
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(freqs_clean / 1e9, sig_clean, "k-", label="Clean (no corruption)", linewidth=1.2)
ax.plot(freqs_b1 / 1e9, sig_b1, "b--", label="B1 gradient = 0.2", linewidth=1.2)
ax.plot(freqs_full / 1e9, sig_full, "r-.", label="B1 grad=0.2 + B_perp=30 uT", linewidth=1.2)
ax.set_xlabel("Frequency (GHz)")
ax.set_ylabel("PL (normalized)")
ax.set_title("Progressive Asymmetric Corruption (P1=50 ppm, T=300 K)")
ax.legend()
fig.tight_layout()
plt.show()"""))

# Cell 7: Linewidth plot
cells.append(nbformat.v4.new_code_cell("""\
p1_range = np.logspace(0, 2.5, 100)
linewidths = np.array([compute_linewidth(p1) for p1 in p1_range])
floor_13c = compute_linewidth(1e-6)  # 13C natural abundance floor

fig, ax = plt.subplots(figsize=(8, 5))
ax.loglog(p1_range, linewidths / 1e6, "b-", linewidth=1.5, label="Total FWHM")
ax.axhline(floor_13c / 1e6, color="gray", linestyle="--", alpha=0.7,
           label=f"13C floor = {floor_13c/1e3:.0f} kHz")
ax.set_xlabel("P1 Concentration (ppm)")
ax.set_ylabel("FWHM Linewidth (MHz)")
ax.set_title("CW ODMR Linewidth vs. P1 Concentration")
ax.legend()
ax.grid(True, alpha=0.3, which="both")
fig.tight_layout()
plt.show()"""))

# Cell 8: Summary table
cells.append(nbformat.v4.new_code_cell("""\
print(f"{'P1 (ppm)':>10} {'T (K)':>8} {'FWHM (MHz)':>12} {'Min PL':>10} {'Dip Depth':>10} {'# Dips':>8}")
print("-" * 65)
for p1 in p1_values:
    for T in temp_values:
        freqs, signal = results[(p1, T)]
        fwhm = compute_linewidth(p1)
        min_pl = np.min(signal)
        depth = 1.0 - min_pl
        # Count resolved dips
        inverted = -signal
        peaks, _ = find_peaks(inverted, height=np.mean(inverted), prominence=0.001)
        n_dips = len(peaks)
        print(f"{p1:>10} {T:>8} {fwhm/1e6:>12.3f} {min_pl:>10.4f} {depth:>10.4f} {n_dips:>8}")"""))

# Cell 9: Experimental comparison header
cells.append(nbformat.v4.new_markdown_cell("""\
## Experimental Data Overlay

Loads 3 spatially-averaged CW-ODMR spectra from Zenodo (Sengottuvel et al. 2022)
and overlays against closest-matching synthetic spectra.

**Caveat:** These are full-frame spatial averages over randomly oriented micro-diamonds.
ODMR dips are heavily smeared by B-field variation and random NV axis orientations.
This comparison tests frequency-range and baseline-level agreement, not detailed lineshape matching."""))

# Cell 10: Experimental overlay
cells.append(nbformat.v4.new_code_cell("""\
# Resolve project root relative to notebook location
_project_root = Path("..").resolve()
zenodo_dir = _project_root / "data" / "experimental" / "zenodo_odmr"
csv_files = ["f0_odmr.csv", "f12_odmr.csv", "f20_odmr.csv"]

fig, axes = plt.subplots(1, 3, figsize=(16, 4))

for ax, csv_name in zip(axes, csv_files):
    csv_path = zenodo_dir / csv_name
    exp_freqs, exp_signal = load_experimental_odmr(str(csv_path))

    # Generate synthetic spectrum matching experimental freq range
    # P1=100 ppm: reasonable for low-quality microdiamonds
    config_exp = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, 50e-6]),
        n_freq_points=200,
        mw_freq_range_Hz=(float(exp_freqs[0]), float(exp_freqs[-1])),
        temperature_K=300.0,
        p1_concentration_ppm=100.0,
        include_nitrogen=False,
        use_optics=False,
    )
    adapter_exp = SimOSAdapter(config_exp)
    sim_freqs, sim_signal = adapter_exp.generate_odmr_spectrum(p1_ppm=100.0)

    # Normalize both for overlay
    exp_range = exp_signal.max() - exp_signal.min()
    sim_range = sim_signal.max() - sim_signal.min()
    exp_norm = (exp_signal - exp_signal.min()) / exp_range if exp_range > 0 else exp_signal
    sim_norm = (sim_signal - sim_signal.min()) / sim_range if sim_range > 0 else sim_signal

    ax.plot(exp_freqs / 1e9, exp_norm, "k-", alpha=0.6, linewidth=0.8, label="Experimental")
    ax.plot(sim_freqs / 1e9, sim_norm, "r-", linewidth=1.0, label="Synthetic (P1=100)")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_title(csv_name.replace("_odmr.csv", ""))
    ax.legend(fontsize=8)

    # Find deepest dip frequency offset
    exp_dip_freq = exp_freqs[np.argmin(exp_signal)]
    sim_dip_freq = sim_freqs[np.argmin(sim_signal)]
    offset_mhz = (exp_dip_freq - sim_dip_freq) / 1e6
    mse = compute_spectral_mse(sim_freqs, sim_signal, exp_freqs, exp_signal)
    print(f"{csv_name}: deepest-dip offset = {offset_mhz:+.1f} MHz, MSE = {mse:.6f}")

axes[0].set_ylabel("Normalized PL")
fig.suptitle("Experimental vs. Synthetic ODMR (Zenodo wide-field average)")
fig.tight_layout()
plt.show()"""))

# Cell 11: Summary
cells.append(nbformat.v4.new_markdown_cell("""\
## Summary

- **P1 concentration** drives linewidth from ~215 kHz (ultra-pure) to ~10 MHz (P1=300 ppm)
- **Temperature** shifts dip positions via ZFS temperature coefficient (dD/dT = -74.2 kHz/K)
- **B1 gradient** and **B_perp** corruption produce realistic asymmetric lineshapes
- **Experimental comparison** is limited by full-frame averaging of randomly oriented micro-diamonds;
  the Zenodo spectra show heavily smeared ODMR features due to spatial averaging over the full FOV"""))

nb.cells = cells
nbformat.write(nb, "experiments/01_visual_sanity_check.ipynb")
print("Notebook written to experiments/01_visual_sanity_check.ipynb")
