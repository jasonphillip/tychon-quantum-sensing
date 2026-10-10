import numpy as np
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.physics.lineshape import generate_multi_axis_spectrum

GOLDEN_MIN = 0.9850899562911801  # pre-change adapter, plan N Step 1b (2026-10-10, base 249c8b9)


def test_default_spectrum_unchanged():
    cfg = SimulationConfig()
    assert cfg.base_contrast == 0.03
    f, s = generate_multi_axis_spectrum(SimOSAdapter(cfg), np.array([0.0, 0.0, 1e-3]), freq_range=(2.80e9, 2.95e9), n_points=600)
    assert abs(float(s.min()) - GOLDEN_MIN) < 1e-9


def test_base_contrast_scales_depth():
    lo = SimulationConfig(base_contrast=0.01)
    hi = SimulationConfig(base_contrast=0.05)
    _, s_lo = generate_multi_axis_spectrum(SimOSAdapter(lo), np.array([0.0, 0.0, 1e-3]), freq_range=(2.80e9, 2.95e9), n_points=600)
    _, s_hi = generate_multi_axis_spectrum(SimOSAdapter(hi), np.array([0.0, 0.0, 1e-3]), freq_range=(2.80e9, 2.95e9), n_points=600)
    assert (1 - s_hi.min()) > 3 * (1 - s_lo.min())
