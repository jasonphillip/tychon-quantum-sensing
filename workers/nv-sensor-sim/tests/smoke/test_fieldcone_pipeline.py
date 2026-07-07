"""Smoke test for the field-cone eval generator (sequence_eval_fieldcone_v1)."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from nv_sensor_sim.datasets.schema import DatasetManifest
from nv_sensor_sim.pipelines.fieldcone_generate import generate_fieldcone_dataset

_PIN = (2667390522.8636284, 3074609477.1363726)
_BUCKETS = [
    {"class": "failure", "pair": [0, 2]},
    {"class": "failure", "pair": [4, 6]},
    {"class": "control", "angle_deg": 30.0, "B_mT": 4.5},
    {"class": "beyond", "angle_deg": 68.0, "B_mT": 3.2},
    {"class": "beyond", "angle_deg": 45.0, "B_mT": 2.2},
]


def _gen(out_dir: str) -> DatasetManifest:
    generate_fieldcone_dataset(
        output_dir=out_dir,
        master_seed=20260713,
        bucket_spec=_BUCKETS,
        seqs_per_bucket=12,
        n_timesteps=32,
        bias_B0_T=5.0e-3,
        bias_direction_uvw=(0.2, 0.1, 1.0),
        freq_range_Hz=_PIN,
        n_freq_points=951,
        axis_contrast_scale=(1.0, 0.85, 0.7, 0.55),
        axis_contrast_drift_std=0.05,
    )
    return DatasetManifest.from_json(f"{out_dir}/manifest.json")


def test_fieldcone_smoke(tmp_path):
    out = str(tmp_path / "fc")
    m = _gen(out)
    assert m.sweep_mode == "fieldcone"
    assert m.n_spectra_test == 5 * 12
    assert m.data_md5 is not None
    st = m.sequence_stats["test"]
    assert st["class_counts"] == {"failure": 24, "control": 12, "beyond": 24}
    # Beyond probes must actually exceed the training walls somewhere.
    assert st["realized_offbias_angle_deg"]["max"] > 60.0
    assert st["realized_field_magnitude_mT"]["min"] < 3.0

    with h5py.File(f"{out}/dataset.h5", "r") as f:
        g = f["test"]
        for key in (
            "bucket_class",
            "target_angle_deg",
            "realized_max_offbias_angle_deg",
            "realized_min_B_T",
            "merge_pair_p",
            "merge_pair_q",
        ):
            assert key in g and g[key].shape == (60,)
        # Failure buckets carry a real merge pair; others carry -1.
        mp = g["merge_pair_p"][:]
        assert (mp == 0).any() and (mp == 4).any() and (mp == -1).any()


def test_fieldcone_deterministic(tmp_path):
    a = _gen(str(tmp_path / "a"))
    b = _gen(str(tmp_path / "b"))
    assert a.data_md5 == b.data_md5


def test_fieldcone_infeasible_bucket_stops_and_reports(tmp_path):
    # A magnitude so low it cannot keep every axis projection above the floor at
    # any azimuth -> stop-and-report (RuntimeError), never a silent drop.
    with pytest.raises(RuntimeError, match="stop-and-report"):
        generate_fieldcone_dataset(
            output_dir=str(tmp_path / "bad"),
            master_seed=20260713,
            bucket_spec=[{"class": "beyond", "angle_deg": 89.0, "B_mT": 0.3}],
            seqs_per_bucket=12,
            n_timesteps=16,
            bias_B0_T=5.0e-3,
            bias_direction_uvw=(0.2, 0.1, 1.0),
            freq_range_Hz=_PIN,
            n_freq_points=951,
            min_axis_projection_T=0.4e-3,
        )
