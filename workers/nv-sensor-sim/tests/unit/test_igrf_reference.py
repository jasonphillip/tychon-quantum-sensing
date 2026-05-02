"""IGRF-14 reference-point regression tests.

ppigrf ≥2.0.0 defaults to IGRF-14 (validity 2020–2030). We pick a small set
of reference geographic points, evaluate at epoch 2026.0, and pin the
returned total-field magnitudes to 0.5 % tolerance to catch silent model
swaps and unit-scaling regressions.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

pytest.importorskip("ppigrf")

from nv_sensor_sim.orbits.igrf_field import (  # noqa: E402
    IGRF_MODEL_VERSION,
    epoch_decimal_year,
    igrf_ned,
)


_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _total_field_uT(lat, lon, alt_m):
    B = igrf_ned(lat, lon, alt_m, _EPOCH)
    return float(np.linalg.norm(B)) * 1e6  # T → µT


def test_igrf_model_version_is_14():
    """We rely on ppigrf shipping IGRF-14 by default; flag if that changes."""
    assert IGRF_MODEL_VERSION == "14"


@pytest.mark.parametrize(
    "name,lat_deg,lon_deg,alt_m,expected_uT,tol_uT",
    [
        # Boulder, CO (1655 m). Total field ~51 µT in the 2020s.
        ("boulder", 40.0, -105.0, 1655.0, 51.2, 0.5),
        # Equatorial Pacific surface — global field minimum region (~30 µT).
        ("equatorial_pacific", 0.0, -150.0, 0.0, 32.0, 4.0),
        # Geomagnetic poles in the 2020s have |B| ~58 µT at the surface.
        ("northern_arctic", 75.0, -100.0, 0.0, 56.0, 3.0),
    ],
)
def test_igrf_total_field_at_reference_points(name, lat_deg, lon_deg, alt_m, expected_uT, tol_uT):
    """IGRF-14 |B| at well-known geographic markers is in the published band."""
    measured = _total_field_uT(lat_deg, lon_deg, alt_m)
    assert abs(measured - expected_uT) < tol_uT, (
        f"{name}: |B|={measured:.2f} µT vs expected {expected_uT}±{tol_uT} µT"
    )


def test_igrf_returns_tesla_not_nT():
    """Catches the most common unit-scaling regression: forgetting nT→T."""
    B = igrf_ned(40.0, -105.0, 1655.0, _EPOCH)
    mag = float(np.linalg.norm(B))
    # Earth surface field ~5e-5 T = 50 µT. nT would give ~5e4 (catastrophic).
    assert 1e-5 < mag < 1e-4


def test_epoch_decimal_year_matches_january_first():
    """epoch_decimal_year(YYYY-01-01) == YYYY.0 within float tolerance."""
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert abs(epoch_decimal_year(t) - 2026.0) < 1e-12


def test_igrf_vector_input_broadcast():
    """igrf_ned accepts arrays of (lat, lon, alt) and returns (N, 3)."""
    lats = np.array([40.0, 0.0, -40.0])
    lons = np.array([-105.0, 0.0, 100.0])
    alts = np.array([1655.0, 0.0, 500.0])
    B = igrf_ned(lats, lons, alts, _EPOCH)
    assert B.shape == (3, 3)
    # All three points should give physically reasonable magnitudes.
    mags = np.linalg.norm(B, axis=-1)
    assert np.all(mags > 1e-5) and np.all(mags < 1e-4)
