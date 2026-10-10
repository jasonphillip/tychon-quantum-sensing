"""End-to-end contract for static bias plus ambient field sampling."""

import json

import h5py
import numpy as np

from nv_sensor_sim.dynamics.field_trajectory import static_bias_vector
from nv_sensor_sim.pipelines.batch_generate import generate_dataset


def test_bias_plus_ambient_dataset_labels_and_manifest(tmp_path):
    output = generate_dataset(
        str(tmp_path),
        n_train=20,
        n_val=0,
        n_test=0,
        n_freq_points=100,
        master_seed=42,
        multi_axis_mode=True,
        field_sampling="bias_plus_ambient",
        bias_B0_T=2.0e-3,
        bias_direction_uvw=(0.2, 0.1, 1.0),
        b_mag_range_T=(0.0, 200e-6),
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["field_sampling"] == "bias_plus_ambient"
    assert manifest["labels_are"] == "total_field"
    with h5py.File(f"{output}/dataset.h5") as dataset:
        labels = dataset["train/labels"][:]
    bias = static_bias_vector(2.0e-3, (0.2, 0.1, 1.0))
    assert labels.shape == (20, 3)
    assert np.allclose(labels.mean(axis=0), bias, atol=30e-6)
