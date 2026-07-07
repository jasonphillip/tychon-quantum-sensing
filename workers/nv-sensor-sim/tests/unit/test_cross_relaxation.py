"""Unit tests for the NV-NV cross-relaxation PL feature knob (nv_density_ppm).

Physics grounding (all sources in-corpus, verified)
---------------------------------------------------
- Espinos & Budker, arXiv:2512.13835 ("Microwave-free vector magnetometry ...
  using Bayesian inference"): cross-relaxation resonance condition Eq. (3)
  |B.n_i| = |B.n_j| (i != j) — when two inequivalent NV orientations have the
  same axial projection their transition energies coincide, dipole-dipole
  coupling enhances flip-flops, ms=0 depopulates, and PL drops. Their
  phenomenological model Eq. (8) is a sum of Lorentzian PL dips centered at the
  degeneracy (delta_i = 0) with contrast C and linewidth Gamma.
- Dhungel et al., arXiv:2301.09666: the feature is density-conditional and
  visible only for NV density >~ 0.9 ppm; two calibration points —
  3.8 ppm -> FWHM 0.78 mT, contrast ~1.79%; 16 ppm -> 1.42 mT, 3.95% — with
  both linewidth and contrast growing with density.
- Wickenbrock/Budker arXiv:1505.02253 confirms the mechanism (T1 shortens at
  inter-orientation degeneracy; amplitude scales with NV concentration).

This is a merge marker + realism feature: it modifies the rendered PL spectrum
only and does NOT add lines to resonance_freqs (L=8 unchanged). OFF
(nv_density_ppm == 0) is byte-identical to pre-knob generation.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.dynamics.render import render_multi_axis_frame
from nv_sensor_sim.physics.cross_relaxation import add_cross_relaxation, cr_contrast_and_width
from nv_sensor_sim.physics.lineshape import project_field_onto_axes


def _adapter(freq_range=(2.80e9, 2.94e9), n_points=2001, p1_ppm=40.0):
    cfg = SimulationConfig(
        n_freq_points=n_points,
        mw_freq_range_Hz=freq_range,
        use_optics=False,
        include_nitrogen=False,
        p1_concentration_ppm=p1_ppm,
    )
    return SimOSAdapter(cfg)


def test_contrast_width_dhungel_anchor_3p8ppm():
    """At the 3.8 ppm calibration point: contrast 1.79%, FWHM 0.78 mT."""
    contrast, fwhm_T = cr_contrast_and_width(3.8)
    assert abs(contrast - 0.0179) < 1e-4
    assert abs(fwhm_T - 0.78e-3) < 1e-5


def test_contrast_width_dhungel_anchor_16ppm():
    """At the 16 ppm calibration point: contrast 3.95%, FWHM 1.42 mT."""
    contrast, fwhm_T = cr_contrast_and_width(16.0)
    assert abs(contrast - 0.0395) < 5e-4
    assert abs(fwhm_T - 1.42e-3) < 3e-5


def test_contrast_zero_below_visibility_floor():
    """Below ~0.9 ppm the feature is not visible: contrast is zero."""
    contrast, _ = cr_contrast_and_width(0.5)
    assert contrast == 0.0


def test_contrast_monotonic_in_density():
    """Contrast and width grow with NV density (Dhungel)."""
    c_low, w_low = cr_contrast_and_width(3.8)
    c_hi, w_hi = cr_contrast_and_width(8.0)
    assert c_hi > c_low
    assert w_hi > w_low


def test_off_is_byte_identical():
    """nv_density_ppm == 0.0 leaves the spectrum untouched (byte-identical)."""
    freqs = np.linspace(2.80e9, 2.94e9, 2001)
    spectrum = np.ones_like(freqs)
    # A degenerate field (along z all four |B.n_i| equal) — CR would fire if ON.
    B = np.array([0.0, 0.0, 3.0e-3])
    B_par, _ = project_field_onto_axes(B)
    res = np.array([2.871e9 + s * 2.8e7 for _ in range(4) for s in (+1, -1)])
    out = add_cross_relaxation(freqs, spectrum, res, B_par, 0.0, 1.5e6)
    assert np.array_equal(out, spectrum)


def test_dip_appears_at_degeneracy():
    """At an inter-orientation degeneracy a PL dip of ~contrast depth appears."""
    freqs = np.linspace(2.80e9, 2.94e9, 4001)
    spectrum = np.ones_like(freqs)
    gamma_e = 28.035e9  # Hz/T
    # Field along z: all |B.n_i| = |B|/sqrt(3) equal -> full degeneracy at
    # D +/- gamma_e * |B|/sqrt(3).
    Bz = 3.0e-3
    B = np.array([0.0, 0.0, Bz])
    B_par, _ = project_field_onto_axes(B)
    D = 2.871e9
    off = gamma_e * abs(B_par[0])
    res = np.array([D + s * off for _ in range(4) for s in (+1, -1)])
    contrast, _ = cr_contrast_and_width(3.8)

    out = add_cross_relaxation(freqs, spectrum, res, B_par, 3.8, 1.5e6)
    # PL is reduced somewhere and the deepest reduction is close to `contrast`.
    assert out.min() < 1.0 - 0.5 * contrast
    # The deepest CR reduction sits near a degenerate transition frequency.
    f_min = freqs[np.argmin(out)]
    assert min(abs(f_min - (D + off)), abs(f_min - (D - off))) < 5e6


def test_no_dip_when_orientations_well_separated():
    """With all |B.n_i| distinct by >> the CR field-width, no CR dip forms."""
    freqs = np.linspace(2.60e9, 3.15e9, 4001)
    spectrum = np.ones_like(freqs)
    gamma_e = 28.035e9
    direction = np.array([0.2, 0.1, 1.0])
    B = 5.0e-3 * direction / np.linalg.norm(direction)
    B_par, _ = project_field_onto_axes(B)
    D = 2.871e9
    res = np.empty(8)
    for i in range(4):
        res[2 * i] = D + gamma_e * B_par[i]
        res[2 * i + 1] = D - gamma_e * B_par[i]
    out = add_cross_relaxation(freqs, spectrum, res, B_par, 3.8, 1.5e6)
    # |B.n_i| span 1.97..3.66 mT: nearest pair gap ~0.56 mT < 0.78 mT FWHM, so a
    # small CR contribution is allowed, but nothing approaching a full dip.
    assert out.min() > 1.0 - 0.5 * cr_contrast_and_width(3.8)[0]


def test_render_cr_off_byte_identical():
    """render_multi_axis_frame(nv_density_ppm=0.0) reproduces the frame exactly."""
    adapter = _adapter()
    B = np.array([0.0, 0.0, 3.0e-3])
    f0, s0, r0 = render_multi_axis_frame(adapter, B, p1_ppm=40.0)
    f1, s1, r1 = render_multi_axis_frame(adapter, B, p1_ppm=40.0, nv_density_ppm=0.0)
    assert np.array_equal(f0, f1)
    assert np.array_equal(s0, s1)
    assert np.array_equal(r0, r1)


def test_render_cr_on_adds_dip_but_not_lines():
    """With cues ON at a degeneracy the spectrum gains an extra dip, but the
    L=8 resonance_freqs labels are unchanged (CR adds no lines)."""
    adapter = _adapter()
    B = np.array([0.0, 0.0, 3.0e-3])  # field along z -> all four axes degenerate
    _, s0, r0 = render_multi_axis_frame(adapter, B, p1_ppm=40.0)
    _, s1, r1 = render_multi_axis_frame(adapter, B, p1_ppm=40.0, nv_density_ppm=3.8)
    np.testing.assert_array_equal(r0, r1)  # no new lines
    assert s1.min() < s0.min()  # cross-relaxation deepens the PL reduction
