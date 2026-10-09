"""Threading of the physics knobs through render_sequence (per-frame loop).

Verifies the sequence-level plumbing that the dwell generator relies on:
axis_offsets_hz and nv_density_ppm reach every frame, and both default to a
byte-identical no-op.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.dynamics.field_trajectory import held_ramp_trajectory, static_bias_vector
from nv_sensor_sim.dynamics.render import render_sequence
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT
from nv_sensor_sim.physics.parameters import compute_linewidth

_MENESES_HZ = np.array([19.6, -4.2, -3.5, -11.9]) * 1.0e3


def _adapter():
    cfg = SimulationConfig(
        n_freq_points=951,
        mw_freq_range_Hz=(2.7e9, 3.04e9),
        use_optics=False,
        include_nitrogen=False,
        p1_concentration_ppm=40.0,
    )
    return SimOSAdapter(cfg)


def _traj():
    bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
    start = np.array([-1.0e-3, 0.0, 0.0])
    end = np.array([1.0e-3, 0.0, 0.0])
    return held_ramp_trajectory(bias, start, end, 12, 2, 9)


def test_render_sequence_knobs_off_byte_identical():
    adapter = _adapter()
    traj = _traj()
    gamma = compute_linewidth(40.0)
    base = render_sequence(adapter, traj, p1_ppm=40.0, gamma_fwhm_hz=gamma, k=1.0)
    knobs_off = render_sequence(
        adapter,
        traj,
        p1_ppm=40.0,
        gamma_fwhm_hz=gamma,
        k=1.0,
        axis_offsets_hz=None,
        nv_density_ppm=0.0,
    )
    for key in ("spectra", "resonance_freqs", "collision_mask", "line_collision"):
        assert np.array_equal(base[key], knobs_off[key]), key


def test_render_sequence_axis_offsets_shift_every_frame():
    adapter = _adapter()
    traj = _traj()
    gamma = compute_linewidth(40.0)
    base = render_sequence(adapter, traj, p1_ppm=40.0, gamma_fwhm_hz=gamma, k=1.0)
    shifted = render_sequence(
        adapter, traj, p1_ppm=40.0, gamma_fwhm_hz=gamma, k=1.0, axis_offsets_hz=_MENESES_HZ
    )
    # Per axis, every frame's center shifts by the offset. Labels are stored as
    # float32 (contract dtype), which quantizes to ~256 Hz at 2.87 GHz, so the
    # recovered shift carries that storage granularity (still resolves the
    # kHz-scale strain ladder).
    for i in range(len(NV_AXES_UNIT)):
        c_base = 0.5 * (base["resonance_freqs"][:, 2 * i] + base["resonance_freqs"][:, 2 * i + 1])
        c_shift = 0.5 * (
            shifted["resonance_freqs"][:, 2 * i] + shifted["resonance_freqs"][:, 2 * i + 1]
        )
        np.testing.assert_allclose(c_shift - c_base, _MENESES_HZ[i], atol=500.0)


def test_render_sequence_cr_changes_spectra_only():
    adapter = _adapter()
    traj = _traj()
    gamma = compute_linewidth(40.0)
    base = render_sequence(adapter, traj, p1_ppm=40.0, gamma_fwhm_hz=gamma, k=1.0)
    cued = render_sequence(
        adapter, traj, p1_ppm=40.0, gamma_fwhm_hz=gamma, k=1.0, nv_density_ppm=3.8
    )
    # Labels untouched; spectra change somewhere along the sequence.
    assert np.array_equal(base["resonance_freqs"], cued["resonance_freqs"])
    assert not np.array_equal(base["spectra"], cued["spectra"])
