"""Independent eigensystem oracle; never uses the production forward model."""
import numpy as np
import pytest

from odmr_vector_tracking.tracking.acquisition import (
    acquire_centers, acquire_centers_with_diagnostics,
)
from odmr_vector_tracking.tracking.exact_inversion_baseline import (
    ExactInversionTracker, invert_axis,
)
from odmr_vector_tracking.vector.geometry import (
    GAMMA_E_HZ_PER_T as GAMMA, ZFS_D_HZ as D, NV_AXES_UNIT,
)


def oracle_transitions_hz(b_lab_t, axis_unit, D, E, gamma):
    """Diagonalize spin one in an independently constructed right-handed axis frame."""
    z = np.asarray(axis_unit, dtype=float)
    z = z / np.linalg.norm(z)
    reference = np.array([0., 0., 1.]) if abs(z[2]) < .9 else np.array([1., 0., 0.])
    x = np.cross(reference, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    bx, by, bz = np.array([x, y, z]) @ np.asarray(b_lab_t)
    sx = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], complex) / np.sqrt(2)
    sy = np.array([[0, -1j, 0], [1j, 0, -1j], [0, 1j, 0]]) / np.sqrt(2)
    sz = np.diag([1., 0., -1.])
    h = D * sz @ sz + E * (sx @ sx - sy @ sy) + gamma * (bx * sx + by * sy + bz * sz)
    eigenvalues = np.linalg.eigvalsh(h)
    return eigenvalues[1:] - eigenvalues[0]


def test_invert_axis_matches_eigenvalue_oracle():
    rng = np.random.default_rng(4022026)
    for _ in range(1000):
        field = rng.normal(size=3)
        field *= rng.uniform(.0001, .003) / np.linalg.norm(field)
        axis = rng.normal(size=3)
        axis /= np.linalg.norm(axis)
        fl, fu = oracle_transitions_hz(field, axis, D, 0., GAMMA)
        magnitude, cosine = invert_axis(fu, fl, D, 0., GAMMA)
        assert abs(magnitude - np.linalg.norm(field)) < 1e-6
        assert abs(cosine - abs(field @ axis) / np.linalg.norm(field)) < 1e-4


def test_invert_axis_is_not_first_order():
    angle = np.radians(70.)
    field = .003 * np.array([np.sin(angle), 0., np.cos(angle)])
    fl, fu = oracle_transitions_hz(field, [0., 0., 1.], D, 0., GAMMA)
    naive_magnitude = (fu - fl) / (2 * GAMMA * np.cos(angle))
    magnitude, _ = invert_axis(fu, fl, D, 0., GAMMA)
    # Dated spec correction: the requested >10 uT at 70 degrees is false.
    # Independent diagonalization gives 1.0070403048357754 uT here.
    assert .9e-6 < abs(naive_magnitude - .003) < 1.1e-6
    assert abs(magnitude - .003) < 1e-6


def test_first_order_fails_by_more_than_10ut_at_85_degrees():
    angle = np.radians(85.)
    field = .003 * np.array([np.sin(angle), 0., np.cos(angle)])
    fl, fu = oracle_transitions_hz(field, [0., 0., 1.], D, 0., GAMMA)
    naive_magnitude = (fu - fl) / (2 * GAMMA * np.cos(angle))
    magnitude, _ = invert_axis(fu, fl, D, 0., GAMMA)
    assert abs(naive_magnitude - .003) > 10e-6
    assert abs(magnitude - .003) < 1e-6


def test_tracker_sign_ambiguity_is_flagged_not_guessed():
    field = np.array([.0003, .0008, .002])
    observed = np.array([oracle_transitions_hz(field, n, D, 0., GAMMA) for n in NV_AXES_UNIT])
    tracker = ExactInversionTracker(np.linspace(2.6e9, 3.15e9, 951), linewidth_Hz=1e6)
    state = tracker.step_from_frequencies(observed[:, 1], observed[:, 0])
    assert state.ambiguous
    assert not state.locked
    assert np.isnan(state.B_est).all()
    assert state.candidates.shape[0] >= 2
    assert np.min(np.linalg.norm(state.candidates - field, axis=1)) < 1e-6
    assert np.min(np.linalg.norm(state.candidates + field, axis=1)) < 1e-6


def test_bias_selects_branch_but_retains_intrinsic_ambiguity():
    field = np.array([.0003, .0008, .002])
    observed = np.array([oracle_transitions_hz(field, n, D, 0., GAMMA) for n in NV_AXES_UNIT])
    tracker = ExactInversionTracker(np.linspace(2.6e9, 3.15e9, 951), linewidth_Hz=1e5, bias_field_t=field)
    state = tracker.step_from_frequencies(observed[:, 1], observed[:, 0])
    assert state.ambiguous
    assert state.locked
    np.testing.assert_allclose(state.B_est, field, atol=1e-9)


def test_nonzero_strain_angle_is_not_identifiable_without_azimuth():
    # Equal trace, trace(H^2), and determinant imply equal eigenvalues. With E!=0,
    # det(H)=-D*(bx^2+by^2)+E*(bx^2-by^2), so theta is not fixed by a spectrum.
    e = 20e6
    norm = .003
    transverse1 = .0025
    transverse2 = transverse1 * np.sqrt((D - e) / (D + e))
    # The oracle's transverse x direction for the z axis is -lab-y.
    b1 = np.array([0., -transverse1, np.sqrt(norm**2 - transverse1**2)])
    b2 = np.array([transverse2, 0., np.sqrt(norm**2 - transverse2**2)])
    first = oracle_transitions_hz(b1, [0, 0, 1], D, e, GAMMA)
    second = oracle_transitions_hz(b2, [0, 0, 1], D, e, GAMMA)
    np.testing.assert_allclose(first, second, atol=1e-4, rtol=0)
    assert abs(b1[2] / norm - b2[2] / norm) > 1e-3
    with pytest.raises(ValueError, match="azimuth"):
        invert_axis(first[1], first[0], D, e, GAMMA)


@pytest.mark.parametrize("field", [np.array([0., 0., .003]), np.array([.003, 0., 0.])])
def test_axis_endpoints(field):
    fl, fu = oracle_transitions_hz(field, [0, 0, 1], D, 0., GAMMA)
    magnitude, cosine = invert_axis(fu, fl, D, 0., GAMMA)
    assert abs(magnitude - .003) < 1e-9
    assert abs(cosine - abs(field[2]) / .003) < 1e-5


@pytest.mark.parametrize("fu,fl", [(np.nan, D), (D, -1.), (1e6, 2e6)])
def test_invalid_frequencies_rejected(fu, fl):
    with pytest.raises(ValueError):
        invert_axis(fu, fl, D, 0., GAMMA)


def test_acquisition_uses_only_frame_and_bias():
    bias = np.array([.0009, .0004, .0048])
    pairs = np.array([oracle_transitions_hz(bias, n, D, 0., GAMMA) for n in NV_AXES_UNIT])
    freqs = np.linspace(2.65e9, 3.1e9, 4501)
    frame = 1 - np.sum(.02 / (1 + ((freqs[:, None] - pairs.ravel()) / .75e6)**2), axis=1)
    centers, diag = acquire_centers_with_diagnostics(frame, freqs, linewidth_Hz=1.5e6, bias_field_t=bias)
    assert diag['n_detected'] == 8
    assert diag['n_bias_fills'] == 0
    np.testing.assert_allclose(np.sort(centers), np.sort(pairs.ravel()), atol=1e5)
    np.testing.assert_array_equal(centers, acquire_centers(frame, freqs, linewidth_Hz=1.5e6, bias_field_t=bias))


def test_flat_spectrum_reports_bias_fills():
    freqs = np.linspace(2.65e9, 3.1e9, 951)
    _, diag = acquire_centers_with_diagnostics(np.ones_like(freqs), freqs, linewidth_Hz=1e6, bias_field_t=np.array([.0009, .0004, .0048]))
    assert diag['n_detected'] == 0
    assert diag['n_bias_fills'] == 8


def test_invalid_frame_never_silently_estimates():
    tracker = ExactInversionTracker(np.linspace(2.6e9, 3.15e9, 951), linewidth_Hz=1e6, bias_field_t=np.array([0, 0, .005]))
    state = tracker.step(np.full(951, np.nan))
    assert not state.locked
    assert np.isnan(state.B_est).all()


def test_spectrum_fit_estimates_field_without_true_initial_centers():
    bias = np.array([.0009, .0004, .0048])
    field = bias + np.array([.0001, -.0001, .0001])
    pairs = np.array([oracle_transitions_hz(field, n, D, 0., GAMMA) for n in NV_AXES_UNIT])
    frequencies = np.linspace(2.65e9, 3.1e9, 4501)
    frame = 1 - np.sum(.02 / (1 + ((frequencies[:, None]-pairs.ravel())/.75e6)**2), axis=1)
    tracker = ExactInversionTracker(frequencies, linewidth_Hz=1.5e6, bias_field_t=bias)
    state = tracker.step(frame)
    assert state.fit_success and state.locked
    assert np.linalg.norm(state.B_est-field) < 5e-6
    assert np.linalg.norm(state.B_est-bias) > 100e-6


def test_analytic_fit_jacobian_matches_finite_difference():
    tracker = ExactInversionTracker(np.linspace(2.65e9, 3.1e9, 951), linewidth_Hz=1.5e6)
    parameters = np.r_[np.linspace(-150,150,8), np.linspace(.01,.03,8), 1., .01]
    _, jacobian = tracker._model_and_jacobian(parameters)
    for i in range(len(parameters)):
        high, low = parameters.copy(), parameters.copy()
        high[i] += 1e-5
        low[i] -= 1e-5
        finite_difference = (tracker._model_and_jacobian(high)[0]-tracker._model_and_jacobian(low)[0])/2e-5
        np.testing.assert_allclose(jacobian[:,i], finite_difference, atol=1e-8, rtol=1e-5)


def test_physical_pairing_recovers_scrambled_axis_assignments():
    field = np.array([.0009, .0004, .0048])
    pairs = np.array([oracle_transitions_hz(field, n, D, 0., GAMMA) for n in NV_AXES_UNIT])
    tracker = ExactInversionTracker(np.linspace(2.65e9, 3.1e9, 951), linewidth_Hz=1.5e6, bias_field_t=field)
    centers = tracker._associate_fitted_centers(np.roll(pairs.ravel(), 3))
    assert centers is not None
    state = tracker.step_from_frequencies(centers[::2], centers[1::2])
    assert state.locked and state.ambiguous
    np.testing.assert_allclose(state.B_est, field, atol=1e-9)
