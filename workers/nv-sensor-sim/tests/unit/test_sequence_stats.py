"""Unit tests for time-series label statistics (crossings, dwell, near-merge)."""

from __future__ import annotations

import json

import numpy as np

from nv_sensor_sim.dynamics.sequence_stats import (
    collision_dwell_lengths,
    count_crossings,
    split_sequence_stats,
)

_GAMMA = 1.5e6


def _two_line_sequence(cross: bool, T: int = 20) -> np.ndarray:
    """(T, 2) centers: line 0 rises through line 1 (cross) or stays below."""
    t = np.linspace(0.0, 1.0, T)
    f1 = np.full(T, 2.87e9)
    if cross:
        f0 = 2.86e9 + t * 0.02e9  # ends 0.01 GHz above f1
    else:
        f0 = 2.86e9 + t * 0.005e9  # ends 0.005 GHz below f1
    return np.stack([f0, f1], axis=1)


class TestCountCrossings:
    def test_single_crossing_counted_once(self):
        n, frames = count_crossings(_two_line_sequence(cross=True))
        assert n == 1
        assert len(frames) == 1
        assert 1 <= frames[0] <= 19

    def test_no_crossing(self):
        n, frames = count_crossings(_two_line_sequence(cross=False))
        assert n == 0
        assert len(frames) == 0

    def test_double_crossing(self):
        # Line 0 crosses up through line 1 and back down.
        T = 21
        t = np.linspace(0.0, 1.0, T)
        f1 = np.full(T, 2.87e9)
        f0 = 2.86e9 + 0.04e9 * np.sin(np.pi * t)  # peaks at +0.03 GHz over f1
        n, frames = count_crossings(np.stack([f0, f1], axis=1))
        assert n == 2
        assert len(frames) == 2
        assert frames[0] < frames[1]

    def test_multi_pair_counting(self):
        # Two independent crossing pairs -> 2 crossings total.
        base = _two_line_sequence(cross=True)
        shifted = base + 0.5e9  # disjoint frequency region, same geometry
        centers = np.concatenate([base, shifted], axis=1)  # (T, 4)
        n, _ = count_crossings(centers)
        assert n == 2


class TestCollisionDwellLengths:
    def test_runs_extracted(self):
        mask = np.array([0, 1, 1, 0, 1, 1, 1, 0, 1], dtype=bool)
        np.testing.assert_array_equal(collision_dwell_lengths(mask), [2, 3, 1])

    def test_empty_and_full(self):
        assert len(collision_dwell_lengths(np.zeros(8, dtype=bool))) == 0
        np.testing.assert_array_equal(collision_dwell_lengths(np.ones(8, dtype=bool)), [8])


class TestSplitSequenceStats:
    def _build_split(self):
        """2 sequences x T=20: one crossing pair + one quiet pair."""
        seq_cross = _two_line_sequence(cross=True)
        seq_quiet = _two_line_sequence(cross=False)
        resonance = np.stack([seq_cross, seq_quiet])  # (2, 20, 2)
        collision = np.zeros((2, 20), dtype=bool)
        collision[0, 9:12] = True  # one 3-frame dwell in the crossing sequence
        B_true = np.zeros((2, 20, 3))
        B_true[:, :, 2] = 3.0e-3  # constant 3 mT along z
        return resonance, collision, B_true

    def test_stats_block(self):
        resonance, collision, B_true = self._build_split()
        stats = split_sequence_stats(resonance, collision, B_true, _GAMMA)

        assert stats["n_sequences"] == 2
        assert stats["crossing_count_per_sequence"] == [1, 0]
        assert stats["no_crossing_fraction"] == 0.5
        assert stats["collision_dwell_frames"]["n"] == 1
        assert stats["collision_dwell_frames"]["max"] == 3.0
        assert stats["collision_frame_fraction"]["max"] == 3.0 / 20.0
        # 3 mT along z projects to |B.n| = 3e-3/sqrt(3) on every axis.
        np.testing.assert_allclose(
            stats["min_abs_projection_T"]["min"], 3.0e-3 / np.sqrt(3.0), rtol=1e-12
        )

    def test_near_merge_counting(self):
        resonance, collision, B_true = self._build_split()
        # Sequence 0's pair approaches within 2*Gamma at the crossing -> its
        # min "splitting" (line 0 = +, line 1 = -) drops below threshold.
        stats = split_sequence_stats(resonance, collision, B_true, _GAMMA)
        assert stats["n_near_merge_sequences"] == 1
        assert stats["near_merge_fraction"] == 0.5

    def test_json_serializable(self):
        resonance, collision, B_true = self._build_split()
        stats = split_sequence_stats(resonance, collision, B_true, _GAMMA)
        dumped = json.dumps(stats)
        assert "crossing_count" in dumped

    def test_line_speed(self):
        resonance, collision, B_true = self._build_split()
        stats = split_sequence_stats(resonance, collision, B_true, _GAMMA)
        # Fastest line: 0.02 GHz over 19 steps.
        expected = 0.02e9 / 19
        np.testing.assert_allclose(stats["max_line_speed_Hz_per_frame"]["max"], expected, rtol=1e-9)
        np.testing.assert_allclose(
            stats["max_line_speed_linewidths_per_frame"]["max"],
            expected / _GAMMA,
            rtol=1e-9,
        )
