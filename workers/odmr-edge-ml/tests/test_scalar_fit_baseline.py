"""Two-line model recovery, invalid-input behavior, and projection limitation."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'experiments' / 'scalar_fit_baseline.py'
spec = importlib.util.spec_from_file_location('scalar_fit_baseline', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
fit_field_magnitude = module.fit_field_magnitude
GAMMA = 2.8035e10


def fixture_spectra(noise=0.0):
    rng = np.random.default_rng(20261014)
    frequencies = np.linspace(2.866e9, 2.874e9, 100)
    rows, truth = [], []
    for _ in range(50):
        b = rng.uniform(20, 65)
        midpoint = 2.870e9 + rng.uniform(-0.35e6, 0.35e6)
        halfwidth = rng.uniform(0.08e6, 0.30e6)
        centers = midpoint + np.array([-1, 1]) * GAMMA * b * 1e-6
        depths = rng.uniform(0.01, 0.035, 2)
        signal = rng.uniform(0.97, 1.03) + rng.uniform(-0.002, 0.002) * (frequencies - 2.870e9) / 4e6
        for center, depth in zip(centers, depths):
            signal -= depth / (1 + ((frequencies - center) / halfwidth) ** 2)
        signal += rng.normal(0, noise, signal.shape)
        rows.append(signal); truth.append(b)
    return frequencies, np.asarray(rows), np.asarray(truth)


def test_fifty_noiseless_two_line_spectra_below_one_microtesla():
    f, rows, truth = fixture_spectra()
    predictions = np.array([fit_field_magnitude(s, f)[0] for s in rows])
    assert np.mean(np.abs(predictions - truth)) < 1.0


def test_noise_errors_are_finite_and_reported():
    f, rows, truth = fixture_spectra(0.0003)
    predictions = np.array([fit_field_magnitude(s, f)[0] for s in rows])
    assert np.isfinite(predictions).all()
    print('noisy_two_line_fixture_mae_uT', np.mean(np.abs(predictions - truth)))


def test_affine_intensity_scaling_preserves_center_splitting():
    f, rows, _ = fixture_spectra()
    a, r = fit_field_magnitude(rows[0], f)
    b, r2 = fit_field_magnitude(3.0 * rows[0] + 2.0, f)
    assert abs(a - b) < 1e-4
    assert r >= 0 and r2 >= 0


@pytest.mark.parametrize('kind', ['flat', 'nan', 'reversed', 'mismatched', 'short'])
def test_invalid_or_uninformative_input_is_rejected(kind):
    f, rows, _ = fixture_spectra(); s = rows[0]
    if kind == 'flat': s = np.ones_like(s)
    elif kind == 'nan': s[3] = np.nan
    elif kind == 'reversed': f = f[::-1]
    elif kind == 'mismatched': s = s[:-1]
    else: f, s = f[:5], s[:5]
    with pytest.raises(ValueError): fit_field_magnitude(s, f)


def test_splitting_is_not_total_magnitude_for_transverse_field():
    # Independent spin-1 eigenvalue oracle, not the fitter's forward model.
    sx = np.array([[0,1,0],[1,0,1],[0,1,0]]) / np.sqrt(2)
    sy = np.array([[0,-1j,0],[1j,0,-1j],[0,1j,0]]) / np.sqrt(2)
    sz = np.diag([1.0,0.0,-1.0])
    b = 50e-6 * np.array([np.sin(np.pi/3), 0.0, np.cos(np.pi/3)])
    eigen = np.linalg.eigvalsh(2.871e9 * (sz @ sz) + GAMMA * (b[0]*sx+b[1]*sy+b[2]*sz))
    proxy = (eigen[2] - eigen[1]) / (2 * GAMMA) * 1e6
    assert abs(proxy - 25.0) < 0.1
    assert abs(proxy - np.linalg.norm(b)*1e6) > 20.0
