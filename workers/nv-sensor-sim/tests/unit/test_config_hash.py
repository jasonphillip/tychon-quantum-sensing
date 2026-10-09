"""Regression tests for batch generator provenance hashes."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace

import numpy as np
import pytest

from nv_sensor_sim.config import OUNoiseConfig
from nv_sensor_sim.datasets.hashing import content_md5
from nv_sensor_sim.datasets.loaders import DatasetLoader
from nv_sensor_sim.pipelines import batch_generate as batch


def _defaults():
    return {
        name: parameter.default
        for name, parameter in inspect.signature(batch.generate_dataset).parameters.items()
        if parameter.default is not inspect.Parameter.empty
    }


CHANGES = {
    "n_train": 1001,
    "n_val": 201,
    "n_test": 201,
    "master_seed": 43,
    "n_freq_points": 101,
    "freq_range_Hz": (2.81e9, 2.92e9),
    "p1_range_ppm": (2.0, 300.0),
    "temp_range_K": (281.0, 320.0),
    "b1_gradient_range": (0.06, 0.30),
    "b_perp_range_T": (0.0, 60e-6),
    "bz_range_T": (0.006, 0.015),
    "noise_mode": "stochastic",
    "ou_noise_config": OUNoiseConfig(),
    "field_sampling": "z_only",
    "b_mag_range_T": (21e-6, 70e-6),
    "shift_test_ranges": True,
    "test_p1_range_ppm": (3.0, 400.0),
    "test_temp_range_K": (290.0, 330.0),
    "test_b1_gradient_range": (0.07, 0.35),
    "test_b_perp_range_T": (0.0, 70e-6),
    "multi_axis_mode": True,
    "bias_B0_T": 0.001,
    "bias_direction_uvw": (1.0, 0.0, 0.0),
    "concentrator_amplification": 2.0,
    "magnet_drift_ppm_per_K": 1.0,
    "bias_B0_range_T": (0.001, 0.002),
}


@pytest.mark.parametrize("field", sorted(CHANGES))
def test_every_generator_parameter_changes_config_hash(field):
    assert set(_defaults()) == set(CHANGES)
    baseline = _defaults()
    changed = dict(baseline, **{field: CHANGES[field]})
    assert batch._config_hash(changed) != batch._config_hash(baseline)


def test_key_order_and_numpy_representations_do_not_change_hash():
    config = _defaults()
    config["ou_noise_config"] = OUNoiseConfig()
    reordered = dict(reversed(list(config.items())))
    reordered["n_freq_points"] = np.int64(config["n_freq_points"])
    reordered["freq_range_Hz"] = np.asarray(config["freq_range_Hz"])
    reordered["ou_noise_config"] = replace(config["ou_noise_config"])
    assert batch._config_hash(config) == batch._config_hash(reordered)


def test_old_subset_collision_is_fixed():
    baseline = _defaults()
    changed = dict(baseline, b1_gradient_range=(0.06, 0.30))
    assert batch._config_hash(baseline) != batch._config_hash(changed)


def test_output_directory_is_excluded():
    baseline = dict(_defaults(), output_dir="/first")
    changed = dict(baseline, output_dir="/second")
    assert batch.CONFIG_HASH_EXCLUDED_FIELDS == {"output_dir"}
    assert batch._config_hash(baseline) == batch._config_hash(changed)


def test_written_content_hash_is_in_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "_get_versions", lambda: ("test", "test"))
    monkeypatch.setattr(batch, "_get_git_sha", lambda: "test")
    monkeypatch.setattr(batch, "SimOSAdapter", lambda config: object())

    def fake_split(adapter, config, split_seeds, **kwargs):
        count = len(split_seeds)
        points = kwargs["n_freq_points"]
        return (
            np.full((count, points), float(split_seeds[0])),
            np.zeros((count, 3)),
            np.zeros((count, 4)),
            np.asarray(split_seeds),
            np.arange(points, dtype=float),
        )

    monkeypatch.setattr(batch, "_generate_split_deterministic", fake_split)
    batch.generate_dataset(str(tmp_path), n_train=1, n_val=1, n_test=1)
    raw = json.loads((tmp_path / "manifest.json").read_text())
    loader = DatasetLoader(tmp_path)
    assert loader.load_manifest().data_md5 == raw["data_md5"]
    arrays = {}
    for split in ("train", "val", "test"):
        values = loader.load_split(split)
        for key, value in zip(
            ("spectra", "frequencies", "labels", "corruption_params", "seeds"), values
        ):
            arrays[f"{split}/{key}"] = value
    assert raw["data_md5"] == content_md5(arrays)
    assert len(raw["config_hash"]) == 12
