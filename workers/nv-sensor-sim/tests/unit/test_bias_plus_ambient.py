import numpy as np
from nv_sensor_sim.pipelines.batch_generate import _sample_bias_plus_ambient


def test_bias_plus_ambient_labels_contain_bias():
    rng = np.random.default_rng(0)
    b0 = 2e-3 * np.array([0.2, 0.1, 1.0]) / np.linalg.norm([0.2, 0.1, 1.0])
    draws = np.stack([_sample_bias_plus_ambient(rng, b0, (0.0, 200e-6)) for _ in range(500)])
    ambient = draws - b0
    assert np.all(np.linalg.norm(ambient, axis=1) <= 200e-6 + 1e-12)
    assert np.allclose(draws.mean(0), b0, atol=30e-6)          # ambient averages out; bias stays
    assert np.linalg.norm(draws.mean(0)) > 1.9e-3
