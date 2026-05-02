"""Unit tests for the SGP4/IGRF-14 ephemeris-derived importance sampler.

The v1 orbit dataset isn't on disk yet (only the README in
tychon-shared-data/datasets/orbit_in_the_loop/), so these tests inject a
synthetic 3-orbit iterable via the ``orbit_iter`` parameter. When the
real v1 ships, an integration-style test (currently deferred to the
contract tier in commit 5) will exercise the canonical loader path.
"""

from __future__ import annotations

import numpy as np
import pytest

from odmr_edge_ml.sampling import ephemeris_theta_weights


def _synthetic_orbits(n_per_orbit: int = 200, seed: int = 0):
    """3 LEO-ish orbits at incl 51.6°, 85°, 97.5° — small Gaussian jitter
    around each inclination so the marginal θ is non-degenerate."""
    rng = np.random.default_rng(seed)
    for incl_deg in (51.6, 85.0, 97.5):
        # Treat the orbit-frame angle to z as inclination-driven; build a
        # synthetic payload-frame B-vector with that polar angle.
        theta_b = np.deg2rad(incl_deg) + rng.normal(0.0, 0.05, n_per_orbit)
        phi = rng.uniform(0.0, 2.0 * np.pi, n_per_orbit)
        sin_t = np.sin(theta_b)
        bx = sin_t * np.cos(phi) * 25e-6     # ~25 µT magnitudes
        by = sin_t * np.sin(phi) * 25e-6
        bz = np.cos(theta_b) * 25e-6
        yield {
            "B_payload_x": bx,
            "B_payload_y": by,
            "B_payload_z": bz,
        }


def _spherical_uniform_sample(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    cos_theta = rng.uniform(-1.0, 1.0, n)
    phi = rng.uniform(0.0, 2.0 * np.pi, n)
    sin_theta = np.sqrt(1.0 - cos_theta * cos_theta)
    return np.stack(
        [sin_theta * np.cos(phi), sin_theta * np.sin(phi), cos_theta], axis=1,
    )


def test_ephemeris_weights_shape_and_normalization():
    labels = _spherical_uniform_sample(500, seed=0)
    w = ephemeris_theta_weights(labels, orbit_iter=_synthetic_orbits())
    assert w.shape == (500,)
    assert (w >= 0).all()
    assert np.isclose(w.mean(), 1.0, atol=1e-9)


def test_ephemeris_weights_upweight_orbit_modes():
    """Samples whose θ matches the orbit's modes should get bigger
    weights than samples in θ regions the orbit doesn't visit."""
    # Construct two probe sets:
    #  - "match": θ near 51.6°, 85°, 97.5° (the orbit modes)
    #  - "anti-match": θ near 5° and 175° (poles — orbit at ~50-100°
    #    barely touches these)
    def _make_probes(theta_degs: list[float]) -> np.ndarray:
        out = []
        for td in theta_degs:
            tr = np.deg2rad(td)
            out.append([np.sin(tr), 0.0, np.cos(tr)])
        return np.asarray(out, dtype=np.float64)

    match_probes = _make_probes([51.6, 85.0, 97.5])
    anti_probes = _make_probes([5.0, 175.0])
    labels = np.vstack([match_probes, anti_probes])
    w = ephemeris_theta_weights(labels, orbit_iter=_synthetic_orbits())
    assert (w[:3].mean() > w[3:].mean()), (
        f"orbit-mode probes ({w[:3]}) should outweigh pole probes ({w[3:]})"
    )


def test_ephemeris_weight_ratio_capped():
    """Despite a potentially extreme p_orbit/p_dataset ratio, the cap
    keeps max(w) bounded."""
    labels = _spherical_uniform_sample(1000, seed=2)
    w = ephemeris_theta_weights(
        labels, orbit_iter=_synthetic_orbits(), max_weight_ratio=10.0,
    )
    median_w = float(np.median(w))
    assert (w <= 10.0 * median_w + 1e-9).all(), (
        f"max weight {w.max()} exceeds 10× median {median_w}"
    )


def test_ephemeris_rejects_empty_orbit_iter():
    labels = np.array([[1.0, 0, 0]])
    with pytest.raises(ValueError, match="no orbits"):
        ephemeris_theta_weights(labels, orbit_iter=iter([]))


def test_ephemeris_works_with_single_synthetic_orbit():
    """Smallest possible orbit input still yields a usable weight array."""
    one_orbit = [{
        "B_payload_x": np.array([1.0, 0.5]),
        "B_payload_y": np.array([0.0, 0.5]),
        "B_payload_z": np.array([0.0, 0.7]),
    }]
    labels = _spherical_uniform_sample(20, seed=3)
    w = ephemeris_theta_weights(labels, orbit_iter=iter(one_orbit))
    assert w.shape == (20,)
    assert np.isfinite(w).all()
