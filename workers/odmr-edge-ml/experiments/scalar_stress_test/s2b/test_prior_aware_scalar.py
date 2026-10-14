import os
import numpy as np
import pytest
from scipy.integrate import quad
from prior_aware_scalar import fit_batch, magnitude_from_projection


@pytest.mark.parametrize('z', [0., 10., 20., 35., 60., 69.])
def test_posterior_normalizes_and_median_has_half_probability(z):
    lower = max(20., z)
    normalization = np.log(70./lower)
    density = lambda b: 1./(b*normalization)
    median, outside = magnitude_from_projection(z)
    assert not outside
    assert quad(density, lower, 70.)[0] == pytest.approx(1., abs=1e-12)
    assert quad(density, lower, float(median))[0] == pytest.approx(.5, abs=1e-12)
    # Numerical posterior loss is minimized at the proposed median.
    expected_loss = lambda a: quad(lambda b: abs(b-a)*density(b), lower, 70., points=[a] if lower<a<70. else None)[0]
    assert expected_loss(float(median)) <= min(expected_loss(float(median)-.1), expected_loss(float(median)+.1))


def test_support_clipping_and_nonfinite_are_explicit():
    magnitude, outside = magnitude_from_projection([-4, 0, 70, 90, np.nan])
    np.testing.assert_allclose(magnitude[:4], [np.sqrt(1400), np.sqrt(1400), 70, 70])
    np.testing.assert_array_equal(outside, [True, False, False, True, False])
    assert np.isnan(magnitude[-1])


@pytest.mark.parametrize('bounds', [(0,70), (70,20), (20,np.nan)])
def test_invalid_prior_rejected(bounds):
    with pytest.raises(ValueError):
        magnitude_from_projection([30],lower_uT=bounds[0],upper_uT=bounds[1])


@pytest.mark.parametrize('backend', ['two_line', 'pid'])
def test_failures_remain_missing_without_hidden_fallback(backend):
    f = np.linspace(2.82e9,2.92e9,100)
    result = fit_batch(np.array([np.ones(100),np.full(100,np.nan)]), f,
                       scalar_repo=os.environ['SCALAR_REPO'],backend=backend)
    assert result['failed'].all()
    assert np.isnan(result['raw_projection_uT']).all()
    assert np.isnan(result['magnitude_uT']).all()


def test_manufactured_valid_two_line_fixtures():
    f = np.linspace(2.866e9,2.876e9,1001)
    gamma = 2.8035e10
    projections = np.array([25.,40.,55.,68.])
    spectra = []
    for z in projections:
        centers = 2.871e9 + np.array([-1,1])*gamma*z*1e-6
        spectra.append(1.-np.sum(.015/(1+((f[:,None]-centers)/.15e6)**2),axis=1))
    result = fit_batch(spectra,f,scalar_repo=os.environ['SCALAR_REPO'])
    assert not result['failed'].any()
    np.testing.assert_allclose(result['raw_projection_uT'],projections,atol=.001)
    np.testing.assert_allclose(result['magnitude_uT'],np.sqrt(70*projections),atol=.001)
    # The transformed result is deliberately not claimed to equal true magnitude.


def test_pid_transform_reuses_recorded_projection():
    f = np.linspace(2.82e9,2.92e9,100)
    row = 1.-.02/(1+((f-2.869e9)/.5e6)**2)-.02/(1+((f-2.873e9)/.5e6)**2)
    result = fit_batch(row[None,:],f,scalar_repo=os.environ['SCALAR_REPO'],backend='pid')
    expected, outside = magnitude_from_projection(result['raw_projection_uT'])
    np.testing.assert_array_equal(result['magnitude_uT'],expected)
    np.testing.assert_array_equal(result['out_of_support'],outside)
