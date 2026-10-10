"""fit_row recovers a known linewidth and contrast from synthetic zero-field dips."""

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.physics.lineshape import generate_multi_axis_spectrum
from nv_sensor_sim.physics.parameters import compute_linewidth
from scripts.fit_simulator_to_external import fit_row

FREQ = np.linspace(2.84e9, 2.90e9, 600)


def _lorentzian_dip(freqs_hz, center_hz, fwhm_hz, contrast, baseline=1.0):
    hw = fwhm_hz / 2.0
    return baseline * (1.0 - contrast * hw**2 / ((freqs_hz - center_hz) ** 2 + hw**2))


def _sim_center_hz():
    f, s = generate_multi_axis_spectrum(SimOSAdapter(SimulationConfig()), np.zeros(3),
                                        freq_range=(FREQ[0], FREQ[-1]), n_points=len(FREQ))
    return float(f[np.argmin(s)])


def _expected_inhomogeneous_hz(target_fwhm_hz):
    # Simulated FWHM = compute_linewidth(p1, inh) * sqrt(1 + s0), default p1 10 ppm, s0 0.1.
    cfg = SimulationConfig()
    total = target_fwhm_hz / np.sqrt(1.0 + cfg.base_saturation_s0)
    hom = compute_linewidth(cfg.p1_concentration_ppm, 0.0)
    return float(np.sqrt(total**2 - hom**2))


def test_fit_recovers_width_and_contrast():
    exp = _lorentzian_dip(FREQ, _sim_center_hz(), 6e6, 0.05)
    fit = fit_row(FREQ, exp, B_lab_T=np.zeros(3), adapter_factory=lambda cfg: SimOSAdapter(cfg))
    assert abs(fit["inhomogeneous_fwhm_hz"] - _expected_inhomogeneous_hz(6e6)) < 2e6
    assert abs(fit["base_contrast"] - 0.05) < 0.3 * 0.05
    assert fit["n_evals"] > 0 and np.isfinite(fit["shape_mse"])


def test_fit_without_contrast_term_still_recovers_width():
    exp = _lorentzian_dip(FREQ, _sim_center_hz(), 3e6, 0.004)
    fit = fit_row(FREQ, exp, B_lab_T=np.zeros(3), adapter_factory=lambda cfg: SimOSAdapter(cfg), use_contrast=False)
    assert abs(fit["inhomogeneous_fwhm_hz"] - _expected_inhomogeneous_hz(3e6)) < 2e6
