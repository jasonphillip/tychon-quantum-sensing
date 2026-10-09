import numpy as np

from odmr_edge_ml.vector.anchors import (
    jitter_bins,
    oracle_lock_bins,
    prior_lock_bins,
    spectrum_lock_bins,
)
from odmr_edge_ml.vector.windowing import NV_AXES_UNIT


def _grid():
    return np.linspace(2.70e9, 3.04e9, 800)


def test_prior_equals_oracle_when_label_is_bias():
    f = _grid()
    B0 = np.array([0.0, 0.0, 5e-3])
    labels = np.tile(B0, (7, 1))
    for axis in range(4):
        for sign in (+1, -1):
            assert np.array_equal(prior_lock_bins(B0, f, axis, sign, 7), oracle_lock_bins(labels, f, axis, sign))


def test_spectrum_lock_finds_dip_near_prior():
    f = _grid()
    prior = np.array([300, 500])
    spectra = np.ones((2, f.size))
    spectra[0, 310] -= 0.2   # dip 10 bins from prior
    spectra[1, 560] -= 0.2   # dip 60 bins away: outside window -> fall back to prior
    out = spectrum_lock_bins(spectra, f, prior, window_bins=25)
    assert out.tolist() == [310, 500]


def test_jitter_is_clipped_and_integer():
    rng = np.random.default_rng(1)
    bins = np.array([0, 799, 400])
    out = jitter_bins(bins, 8.0, rng, n_bins=800)
    assert out.dtype.kind == "i" and out.min() >= 0 and out.max() <= 799
