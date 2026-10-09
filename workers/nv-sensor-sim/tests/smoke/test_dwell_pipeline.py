"""Smoke tests for the dwell-sweep eval generator (CPU-only).

Covers the dwell-lineage contract, determinism, and the seed-paired cues:
generation with cues off is deterministic and byte-identical across runs, and
turning the cues on leaves the kinematics (B_true, seeds) untouched while
shifting the labels (strain) and the spectra (cross-relaxation).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import h5py
import numpy as np
import pytest

pytestmark = pytest.mark.filterwarnings("ignore:Grid aliasing risk:UserWarning")

# Pinned v1 window (coarser grid here for speed; centers are grid-independent).
_FREQ = (2667390522.8636284, 3074609477.1363726)
_MENESES_HZ = (19600.0, -4200.0, -3500.0, -11900.0)

_COMMON = dict(
    master_seed=20260707,
    n_timesteps=256,
    p1_ppm=40.0,
    temperature_K=300.0,
    bias_B0_T=0.005,
    bias_direction_uvw=(0.2, 0.1, 1.0),
    freq_range_Hz=_FREQ,
    n_freq_points=201,
    axis_contrast_scale=(1.0, 0.85, 0.7, 0.55),
    axis_contrast_drift_std=0.05,
    axis_contrast_drift_tau_frames=64.0,
    dwell_frames_list=(8, 16),
    seqs_per_bucket=2,
)


def _generate(tmp, **overrides):
    from nv_sensor_sim.pipelines.dwell_generate import generate_dwell_sequence_dataset

    return generate_dwell_sequence_dataset(str(tmp), **{**_COMMON, **overrides})


@pytest.mark.smoke
def test_dwell_contract_and_metadata():
    """Eval-only test split, dwell manifest keys, and per-sequence label arrays."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(_generate(Path(tmpdir)))
        m = json.loads((out / "manifest.json").read_text())
        assert m["contract_version"] == "v1"
        assert m["sweep_mode"] == "dwell"
        assert m["n_spectra_train"] == 0 and m["n_spectra_val"] == 0
        assert m["n_spectra_test"] == 2 * 2 * 2  # |D| x |topo| x per_bucket
        assert m["data_md5"] is not None
        buckets = m["sequence_stats"]["test"]["dwell_buckets"]
        for d in (8, 16):
            for topo in ("cross", "bounce"):
                b = buckets[f"D{d}_{topo}"]
                assert b["n"] == 2
                assert abs(b["realized_dwell_mean"] - d) <= max(1, 0.1 * d)

        with h5py.File(out / "dataset.h5", "r") as f:
            g = f["test"]
            for key in ("exit_topology", "dwell_frames", "dwell_frames_target",
                        "merge_p", "merge_q", "mirror_p", "mirror_q"):
                assert key in g, key
            # exactly the target pair + its mirror collide; four spectators protected
            res = g["resonance_freqs"][:].astype(float)
            gamma = m["linewidth_Hz"]
            for s in range(res.shape[0]):
                p, q = int(g["merge_p"][s]), int(g["merge_q"][s])
                pm, qm = int(g["mirror_p"][s]), int(g["mirror_q"][s])
                coalescing = {p, q, pm, qm}
                spectators = [ell for ell in range(8) if ell not in coalescing]
                for u in spectators:
                    for v in range(8):
                        if u == v:
                            continue
                        assert np.min(np.abs(res[s, :, u] - res[s, :, v])) >= gamma, (
                            f"seq {s} spectator {u} collided with {v}"
                        )


@pytest.mark.smoke
def test_dwell_determinism_and_seed_paired_cues():
    """Same seed -> identical md5 (cues off); cues on keep B_true/seeds, shift labels+spectra."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        off_a = Path(_generate(base / "off_a"))
        off_b = Path(_generate(base / "off_b"))
        cues = Path(_generate(base / "cues", axis_offsets_hz=_MENESES_HZ, nv_density_ppm=3.8))

        md5_a = json.loads((off_a / "manifest.json").read_text())["data_md5"]
        md5_b = json.loads((off_b / "manifest.json").read_text())["data_md5"]
        assert md5_a == md5_b, "cues-off generation is not deterministic"

        with h5py.File(off_a / "dataset.h5", "r") as fa, h5py.File(cues / "dataset.h5", "r") as fc:
            ga, gc = fa["test"], fc["test"]
            # Kinematics identical (seed-paired): B_true and seeds byte-identical.
            assert np.array_equal(ga["B_true"][:], gc["B_true"][:])
            assert np.array_equal(ga["seeds"][:], gc["seeds"][:])
            # Cues change the labels (strain) and the spectra (cross-relaxation).
            assert not np.array_equal(ga["resonance_freqs"][:], gc["resonance_freqs"][:])
            assert not np.array_equal(ga["spectra"][:], gc["spectra"][:])
            # Strain shifts each axis' center by the offset (split preserved).
            ra = ga["resonance_freqs"][0].astype(float)
            rc = gc["resonance_freqs"][0].astype(float)
            for i in range(4):
                ca = 0.5 * (ra[:, 2 * i] + ra[:, 2 * i + 1])
                cc = 0.5 * (rc[:, 2 * i] + rc[:, 2 * i + 1])
                np.testing.assert_allclose(np.median(cc - ca), _MENESES_HZ[i], atol=500.0)
