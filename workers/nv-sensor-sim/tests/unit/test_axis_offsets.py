"""Unit tests for the per-axis static strain / E-field offset knob (axis_offsets_hz).

Physics grounding
-----------------
A static axial strain / electric-field offset shifts an NV orientation's
zero-field splitting D by a per-orientation amount delta_i (the "M_z ladder";
real-device fit Meneses (19.6, -4.2, -3.5, -11.9) kHz). Because it is a ZFS
shift, BOTH the ms0->+1 and ms0->-1 transitions of that axis move by the same
delta_i (common mode). Consequences verified here:

- the per-axis line CENTER (f+ + f-)/2 moves by delta_i, so the offset flows
  into the resonance_freqs ground truth automatically;
- the per-axis SPLIT (f+ - f-) is UNCHANGED, so a splitting-based decode is
  blind to the offset (documented interaction) — the offset is a static,
  center-only identity cue;
- OFF (offset == 0) is byte-identical to pre-knob generation.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.dynamics.render import render_multi_axis_frame
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

_MENESES_KHZ = (19.6, -4.2, -3.5, -11.9)


def _adapter(freq_range=(2.83e9, 2.91e9), n_points=1601, p1_ppm=40.0):
    cfg = SimulationConfig(
        n_freq_points=n_points,
        mw_freq_range_Hz=freq_range,
        use_optics=False,
        include_nitrogen=False,
        p1_concentration_ppm=p1_ppm,
    )
    return SimOSAdapter(cfg)


def test_center_offset_shifts_both_transitions_equally():
    """generate_odmr_spectrum(center_offset_hz=d) shifts every line center by d."""
    adapter = _adapter()
    B = np.array([0.0, 0.0, 1.0e-3])  # 1 mT axial
    delta = 5.0e5  # 500 kHz, resolvable on the grid

    _, _, centers0 = adapter.generate_odmr_spectrum(B_field=B, return_line_centers=True)
    _, _, centers_d = adapter.generate_odmr_spectrum(
        B_field=B, center_offset_hz=delta, return_line_centers=True
    )
    # Every allowed transition center moves by exactly delta (common mode).
    np.testing.assert_allclose(np.sort(centers_d), np.sort(centers0) + delta, rtol=0, atol=1.0)


def test_center_offset_off_is_byte_identical():
    """center_offset_hz == 0.0 reproduces the spectrum bit-for-bit."""
    adapter = _adapter()
    B = np.array([0.0, 0.0, 1.2e-3])
    f0, s0, c0 = adapter.generate_odmr_spectrum(B_field=B, return_line_centers=True)
    f1, s1, c1 = adapter.generate_odmr_spectrum(
        B_field=B, center_offset_hz=0.0, return_line_centers=True
    )
    assert np.array_equal(f0, f1)
    assert np.array_equal(s0, s1)
    assert np.array_equal(c0, c1)


def test_center_offset_moves_the_rendered_dip():
    """The rendered Lorentzian dip shifts with the center offset."""
    adapter = _adapter(freq_range=(2.86e9, 2.88e9), n_points=4001, p1_ppm=40.0)
    B = np.zeros(3)  # zero field: single degenerate dip at D
    delta = 3.0e6  # 3 MHz
    freqs, s0, _ = adapter.generate_odmr_spectrum(B_field=B, return_line_centers=True)
    _, sd = adapter.generate_odmr_spectrum(B_field=B, center_offset_hz=delta)
    f_dip0 = freqs[np.argmin(s0)]
    f_dipd = freqs[np.argmin(sd)]
    assert abs((f_dipd - f_dip0) - delta) < 2.0 * (freqs[1] - freqs[0])


def test_axis_offsets_shift_centers_preserve_split():
    """render_multi_axis_frame(axis_offsets_hz=...) shifts each axis center by
    delta_i while leaving that axis' split f+ - f- unchanged."""
    adapter = _adapter()
    # Off-symmetry bias so all four |B.n_i| are distinct and lines are resolved.
    direction = np.array([0.2, 0.1, 1.0])
    B_lab = 5.0e-3 * direction / np.linalg.norm(direction)
    offsets = np.array(_MENESES_KHZ) * 1.0e3  # Hz

    _, _, res0 = render_multi_axis_frame(adapter, B_lab, p1_ppm=40.0)
    _, _, res_d = render_multi_axis_frame(adapter, B_lab, p1_ppm=40.0, axis_offsets_hz=offsets)

    for i in range(len(NV_AXES_UNIT)):
        c0 = 0.5 * (res0[2 * i] + res0[2 * i + 1])
        cd = 0.5 * (res_d[2 * i] + res_d[2 * i + 1])
        split0 = res0[2 * i] - res0[2 * i + 1]
        splitd = res_d[2 * i] - res_d[2 * i + 1]
        # Center shifts by delta_i ...
        np.testing.assert_allclose(cd - c0, offsets[i], atol=2.0)
        # ... split is preserved (common-mode shift).
        np.testing.assert_allclose(splitd, split0, atol=2.0)


def test_axis_offsets_off_is_byte_identical():
    """axis_offsets_hz=None reproduces the frame bit-for-bit."""
    adapter = _adapter()
    direction = np.array([0.2, 0.1, 1.0])
    B_lab = 5.0e-3 * direction / np.linalg.norm(direction)
    f0, s0, r0 = render_multi_axis_frame(adapter, B_lab, p1_ppm=40.0)
    f1, s1, r1 = render_multi_axis_frame(adapter, B_lab, p1_ppm=40.0, axis_offsets_hz=None)
    assert np.array_equal(f0, f1)
    assert np.array_equal(s0, s1)
    assert np.array_equal(r0, r1)
