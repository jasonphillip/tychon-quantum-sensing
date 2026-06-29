"""Unit tests for time-series resonance association and collision labelling.

Covers the dynamics layer that turns per-axis diagonalized line centers into
ground-truth labels: axis/transition identity, the signed-projection association
rule, collision labelling, and the honesty guarantee that the stored centers sit
on the rendered spectrum dips and are consistent with the BLUE geometry matrix.
"""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.dynamics.render import render_multi_axis_frame
from nv_sensor_sim.dynamics.resonances import (
    GAMMA_HZ_PER_T,
    associate_axis_centers,
    axis_transition_labels,
    collision_labels,
    reference_zfs_hz,
)
from nv_sensor_sim.physics.lineshape import nv_geometry_matrix
from nv_sensor_sim.physics.parameters import compute_linewidth

pytestmark = pytest.mark.filterwarnings("ignore:Grid aliasing risk:UserWarning")


def test_axis_transition_labels_geometry_order():
    """Labels follow nv_geometry_matrix row order: 2i=+n_i (ms0->+1), 2i+1=-n_i."""
    line_axis, line_transition = axis_transition_labels()
    assert line_axis.dtype == np.int8
    assert line_transition.dtype == np.int8
    np.testing.assert_array_equal(line_axis, [0, 0, 1, 1, 2, 2, 3, 3])
    np.testing.assert_array_equal(line_transition, [1, 0, 1, 0, 1, 0, 1, 0])


def test_associate_axis_centers_sign_rule():
    """s=+1 line is the higher center iff B.n_i >= 0 (lower otherwise)."""
    per_axis = [np.array([2.80e9, 2.94e9]) for _ in range(4)]
    B_par = np.array([+1e-3, -1e-3, +2e-3, -2e-3])
    res = associate_axis_centers(per_axis, B_par)
    assert res[0] == 2.94e9  # axis0 B_par>0 -> s=+1 is the higher line
    assert res[1] == 2.80e9  # axis0 s=-1 is the lower line
    assert res[2] == 2.80e9  # axis1 B_par<0 -> s=+1 is the lower line
    assert res[3] == 2.94e9


def test_associate_axis_centers_degenerate():
    """A single (degenerate) center maps to both transitions."""
    res = associate_axis_centers([np.array([2.87e9])] * 4, np.zeros(4))
    np.testing.assert_array_equal(res, np.full(8, 2.87e9))


def test_collision_labels_known_crossing():
    """A frame with two lines within k*Gamma is flagged; an isolated frame is not."""
    gamma = 1.0e6
    centers = np.array(
        [
            [2.80e9, 2.90e9, 3.00e9, 3.10e9],  # all far apart
            [2.80e9, 2.8005e9, 3.00e9, 3.10e9],  # lines 0,1 within 0.5 MHz
        ]
    )
    collision_mask, line_collision = collision_labels(centers, gamma, k=1.0)
    assert collision_mask.tolist() == [False, True]
    assert line_collision[0].tolist() == [False, False, False, False]
    assert line_collision[1].tolist() == [True, True, False, False]


def test_collision_threshold_boundary():
    """The k*Gamma threshold gates collisions as expected."""
    gamma = 1.0e6
    centers = np.array([[0.0, 0.9e6, 5e6, 9e6]])  # nearest pair separated by 0.9 MHz
    assert collision_labels(centers, gamma, k=1.0)[0][0]  # 0.9 < 1.0 MHz -> collide
    assert not collision_labels(centers, gamma, k=0.5)[0][0]  # 0.9 > 0.5 MHz -> no


def test_reference_zfs_near_2871_mhz():
    """The zero-field splitting read from SimOS is ~2.87 GHz."""
    adapter = SimOSAdapter(SimulationConfig(use_optics=False, include_nitrogen=False))
    D = reference_zfs_hz(adapter)
    assert abs(D - 2.87e9) < 5e6


def test_centers_match_rendered_dips_when_separated():
    """Honesty: each stored label is the local minimum of the rendered spectrum.

    Uses a field that gives 8 well-separated lines and a fine grid so the search
    window cannot reach a neighbouring line.
    """
    n_freq = 4000
    cfg = SimulationConfig(
        use_optics=False,
        include_nitrogen=False,
        n_freq_points=n_freq,
        mw_freq_range_Hz=(2.70e9, 3.04e9),
    )
    adapter = SimOSAdapter(cfg)
    freqs, spec, res = render_multi_axis_frame(
        adapter, 1e-3 * np.array([1.0, 2.0, 4.0]), p1_ppm=40.0
    )
    df = freqs[1] - freqs[0]
    for center in res:
        j = int(np.argmin(np.abs(freqs - center)))
        lo, hi = max(0, j - 5), min(n_freq, j + 6)
        local_min = lo + int(np.argmin(spec[lo:hi]))
        assert abs(freqs[local_min] - center) <= 2.0 * df


def test_signed_split_matches_geometry_matrix():
    """Labels are consistent with the BLUE geometry matrix to first order.

    The signed half-difference of an axis's two lines equals gamma * (A @ B) for
    the +n_i row — i.e. the Zeeman shift the downstream inverter assumes. This is
    exact even with the second-order common-mode shift (which cancels in the
    difference), so it validates both the magnitude and the transition identity.
    """
    cfg = SimulationConfig(
        use_optics=False,
        include_nitrogen=False,
        n_freq_points=2000,
        mw_freq_range_Hz=(2.6e9, 3.15e9),
    )
    adapter = SimOSAdapter(cfg)
    B = 1e-3 * np.array([0.5, -1.0, 2.0])
    _, _, res = render_multi_axis_frame(adapter, B, p1_ppm=40.0)
    A = nv_geometry_matrix()
    gamma_fwhm = compute_linewidth(40.0)
    for i in range(4):
        signed_half = (res[2 * i] - res[2 * i + 1]) / 2.0
        expected = GAMMA_HZ_PER_T * float(A[2 * i] @ B)
        assert abs(signed_half - expected) < 0.3 * gamma_fwhm
