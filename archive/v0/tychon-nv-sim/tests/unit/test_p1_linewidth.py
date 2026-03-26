"""Unit tests for P1 concentration → linewidth analytical scaling law."""

from __future__ import annotations

import numpy as np
import pytest

from tychon_nv_sim.physics.parameters import compute_linewidth


def test_linewidth_known_values():
    """compute_linewidth matches hand-calculated values from the analytical model.

    Model: 1/T2* = 1/1.48µs + P1/9.9µs, FWHM = 1/(π·T2*)
    At P1=0 (clamped to 1e-6): dominated by 13C floor → ~215 kHz
    At P1=100: rate_13c=675676, rate_n=10101010 → T2*=92.8ns → FWHM≈3.43 MHz
    """
    # Pure 13C floor (P1 ≈ 0)
    lw_floor = compute_linewidth(1e-6)
    expected_13c = 1.0 / (np.pi * 1.48e-6)  # ~215 kHz
    assert lw_floor == pytest.approx(expected_13c, rel=1e-3)

    # P1 = 100 ppm
    rate = 1.0 / 1.48e-6 + 100.0 / 9.9e-6
    expected_100 = rate / np.pi
    assert compute_linewidth(100.0) == pytest.approx(expected_100, rel=1e-6)


def test_linewidth_monotonic_increase():
    """Linewidth increases monotonically with P1 concentration."""
    p1_values = np.logspace(-1, np.log10(300), 30)
    linewidths = [compute_linewidth(p1) for p1 in p1_values]
    for i in range(len(linewidths) - 1):
        assert linewidths[i] <= linewidths[i + 1], (
            f"Linewidth not monotonic at P1={p1_values[i]:.2f}: "
            f"{linewidths[i]:.0f} > {linewidths[i+1]:.0f} Hz"
        )


def test_linewidth_increases_with_p1():
    """Higher P1 concentration → broader linewidth (shorter T2)."""
    lw_low = compute_linewidth(1.0)   # Low P1 → narrow line
    lw_high = compute_linewidth(300.0)  # High P1 → broad line
    assert lw_high > lw_low, f"Expected lw(300ppm)={lw_high} > lw(1ppm)={lw_low}"


def test_linewidth_physical_range():
    """Linewidths should be in physically reasonable range (kHz to MHz)."""
    for p1 in [1.0, 10.0, 100.0, 300.0]:
        lw = compute_linewidth(p1)
        assert 100 < lw < 500e6, f"P1={p1}: linewidth {lw:.0f} Hz out of physical range"


def test_inhomogeneous_broadening():
    """Inhomogeneous broadening adds in quadrature with homogeneous FWHM."""
    hom = compute_linewidth(10.0, inhomogeneous_fwhm_hz=0.0)
    inhom = 1e6  # 1 MHz inhomogeneous contribution
    total = compute_linewidth(10.0, inhomogeneous_fwhm_hz=inhom)
    expected = np.sqrt(hom**2 + inhom**2)
    assert total == pytest.approx(expected, rel=1e-10)
    assert total > hom, "Inhomogeneous broadening should widen the line"


def test_13c_floor():
    """At vanishing P1, linewidth approaches the 13C natural abundance floor."""
    lw_tiny = compute_linewidth(1e-6)
    lw_zero = 1.0 / (np.pi * 1.48e-6)  # Pure 13C limit
    assert lw_tiny == pytest.approx(lw_zero, rel=1e-3)


def test_spectrum_linewidth_varies_with_p1():
    """Spectra generated with different P1 values should have different dip widths.

    Uses a wide frequency window (100 MHz) to fully contain both narrow (P1=1,
    FWHM~247 kHz) and broad (P1=300, FWHM~10 MHz) dips. Compares integrated
    absorption (mean dip area) rather than point depth, since the on-resonance
    Lorentzian value is always 1.0 regardless of linewidth.
    """
    from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
    from tychon_nv_sim.config import SimulationConfig

    # Wide window capturing both ODMR dips, fine resolution
    config = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, 0.001]),
        temperature_K=300.0,
        mw_freq_range_Hz=(2.82e9, 2.92e9),  # 100 MHz window
        n_freq_points=2000,  # 50 kHz per bin
        include_nitrogen=False,
        use_optics=False,
    )
    adapter = SimOSAdapter(config)

    _, signal_low_p1 = adapter.generate_odmr_spectrum(p1_ppm=1.0)
    _, signal_high_p1 = adapter.generate_odmr_spectrum(p1_ppm=300.0)

    # Both should show ODMR dips
    assert np.min(signal_low_p1) < 0.99, "P1=1 spectrum should show ODMR dips"
    assert np.min(signal_high_p1) < 0.99, "P1=300 spectrum should show ODMR dips"

    # Higher P1 → broader Lorentzian → more total absorption across the window.
    # Integrated dip area = mean(1 - PL) captures linewidth difference.
    absorption_low = np.mean(1.0 - signal_low_p1)
    absorption_high = np.mean(1.0 - signal_high_p1)
    assert absorption_high > absorption_low * 1.5, (
        f"Higher P1 should produce broader dips: "
        f"absorption(P1=300)={absorption_high:.6f}, absorption(P1=1)={absorption_low:.6f}"
    )
