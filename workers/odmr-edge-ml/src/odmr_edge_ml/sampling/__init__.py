"""Bias-aware importance samplers for cascade training (P3-12).

All samplers operate as *reweighters* over the existing 50K training
corpus rather than as new generators — the air-gap rule prevents
calling into upstream nv-sensor-sim at training time. Each function
returns ``(N,)`` non-negative weights consumable by
``torch.utils.data.WeightedRandomSampler``.

The shared θ helper consolidates the polar-angle definition used in
``experiments/orientation_binned_comparison.py`` so all samplers (and
the regression test in tests/contract/test_polar_bias_regression.py)
agree on what θ means.
"""

from odmr_edge_ml.sampling.ephemeris import ephemeris_theta_weights
from odmr_edge_ml.sampling.inverse_theta import inverse_theta_weights
from odmr_edge_ml.sampling.theta_utils import polar_theta_from_labels

__all__ = [
    "ephemeris_theta_weights",
    "inverse_theta_weights",
    "polar_theta_from_labels",
]
