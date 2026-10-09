"""Evaluation JSON provenance contract."""

import json

import numpy as np
import pytest

from experiments.vector_v1_eval import _assemble_results, _tflite_predict_batch
from odmr_edge_ml.vector.anchors import bias_from_manifest


def test_results_carry_anchor_source():
    for source in ("oracle", "prior", "spectrum"):
        result = _assemble_results(
            {"n_total": 1},
            anchor_source=source,
            condition="full",
            anchor_noise_bins=0.0,
            dataset_md5="0" * 32,
            regenerated_dataset=False,
            wall_s=0.1,
        )
        assert result["anchor_source"] == source
        assert result["condition"] == "full"
        assert result["oracle_conditioned"] is (source == "oracle")


def test_bias_defaults_from_manifest_and_missing_bias_errors(tmp_path):
    dataset = tmp_path / "dataset.h5"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"bias_B0_T": 0.005, "bias_direction_uvw": [0, 0, 2]}))
    np.testing.assert_allclose(bias_from_manifest(dataset), [0, 0, 0.005])
    manifest.write_text("{}")
    with pytest.raises(ValueError, match="No bias field"):
        bias_from_manifest(dataset)


def test_predict_batch_zeroes_selected_input_channel():
    class Interpreter:
        def get_input_details(self):
            return [{"index": 0, "quantization": (0.01, 0)}]

        def get_output_details(self):
            return [{"index": 0, "quantization": (1.0, 0)}]

        def set_tensor(self, index, value):
            self.input = value

        def invoke(self):
            pass

        def get_tensor(self, index):
            return np.array([[0]], dtype=np.int8)

    interp = Interpreter()
    spectrum = np.ones((1, 8))
    bins = np.array([4])
    _tflite_predict_batch(interp, spectrum, bins, 1.5, anchor_scale=0.0)
    assert np.all(interp.input[..., 1] == 0)
    _tflite_predict_batch(interp, spectrum, bins, 1.5, spectrum_scale=0.0)
    assert np.all(interp.input[..., 0] == 0)
