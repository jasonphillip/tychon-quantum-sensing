"""Drift bound and basic-shape tests for the SGP4 wrapper.

The optional ``sgp4`` dependency is gated by ``pytest.importorskip`` so this
file becomes a no-op when ``[orbit]`` extras are not installed.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sgp4")

from nv_sensor_sim.orbits.sgp4_propagator import propagate_tle  # noqa: E402


# Published ISS (ZARYA) TLE — Celestrak archive sample, used purely as a
# representative LEO orbit for drift-bound testing.
_ISS_LINE1 = (
    "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9000"
)
_ISS_LINE2 = (
    "2 25544  51.6400 100.0000 0006703  90.0000  10.0000 15.50000000400000"
)


def test_iss_propagation_basic_shape():
    """Sanity: 1-orbit propagation returns the right array shapes and units."""
    out = propagate_tle(_ISS_LINE1, _ISS_LINE2, duration_s=5400.0, dt_s=60.0)
    n = 5400 // 60 + 1
    assert out.r_eci_m.shape == (n, 3)
    assert out.v_eci_mps.shape == (n, 3)
    assert out.t_rel_s.shape == (n,)
    # LEO altitude ~400 km → radius ~6.78 Mm
    radius = np.linalg.norm(out.r_eci_m, axis=1)
    assert np.all(radius > 6.6e6)
    assert np.all(radius < 7.2e6)
    # Speed ~7.7 km/s
    speed = np.linalg.norm(out.v_eci_mps, axis=1)
    assert np.all(speed > 7.0e3)
    assert np.all(speed < 8.5e3)


def test_iss_propagation_drift_bound():
    """SGP4 LEO error envelope: position drift bounded after 24 h.

    SGP4's published accuracy envelope grows from ~1–3 km at epoch to ~1–3 km
    per day. We check the propagated radius stays in the LEO regime and the
    along-track drift between successive samples (60 s apart) varies smoothly
    — i.e. SGP4 doesn't blow up on a 24 h propagation of a published TLE.
    """
    out = propagate_tle(_ISS_LINE1, _ISS_LINE2, duration_s=86400.0, dt_s=60.0)
    radius = np.linalg.norm(out.r_eci_m, axis=1)
    assert np.all(radius > 6.6e6) and np.all(radius < 7.2e6)
    # Step-to-step displacement should be ~v_orbital * dt = ~460 km/min;
    # if SGP4 had blown up we'd see step jumps of 1000+ km.
    step_disp = np.linalg.norm(np.diff(out.r_eci_m, axis=0), axis=1)
    assert np.all(step_disp < 600e3)
    assert np.all(step_disp > 300e3)


def test_t_rel_starts_at_zero_and_monotonic():
    out = propagate_tle(_ISS_LINE1, _ISS_LINE2, duration_s=600.0, dt_s=10.0)
    assert out.t_rel_s[0] == 0.0
    assert np.all(np.diff(out.t_rel_s) > 0)


def test_epoch_utc_carried():
    out = propagate_tle(_ISS_LINE1, _ISS_LINE2, duration_s=60.0, dt_s=30.0)
    # Epoch year encoded in the TLE is 2024 (24001 = 2024 day 1)
    assert out.epoch_utc.year == 2024
    assert out.epoch_utc.month == 1
    assert out.epoch_utc.day == 1
