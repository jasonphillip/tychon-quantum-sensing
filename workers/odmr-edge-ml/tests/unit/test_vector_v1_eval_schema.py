"""Evaluation JSON provenance contract."""

import json
import sys

import h5py
import numpy as np
import pytest

from experiments import vector_v1_eval as evaluator
from experiments.vector_v1_eval import _assemble_results, _coarse_fit_diagnostics, _tflite_predict_batch
from odmr_edge_ml.vector.anchors import bias_from_manifest


def test_results_carry_anchor_source():
    for source in ("oracle", "prior", "spectrum", "coarse_fit"):
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
        assert result["selection_uses_labels"] is (source == "oracle")


def test_coarse_fit_diagnostics_respect_field_sign():
    labels = np.array([[0.0, 0.0, 2e-3], [1e-3, 0.0, 0.0]])
    fitted = np.array([[0.0, 0.0, -2e-3], [1.5e-3, 0.0, 0.0]])
    metrics = _coarse_fit_diagnostics(fitted, labels)
    assert metrics["coarse_fit_angle_err_deg_median"] == pytest.approx(0.0)
    assert metrics["coarse_fit_mag_err_T_median"] == pytest.approx(0.25e-3)


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


def test_non_oracle_selection_and_blue_inputs_ignore_labels(tmp_path, monkeypatch):
    models = tmp_path / "models"
    channels = []
    for axis in range(4):
        for sign in (1, -1):
            tag = evaluator._channel_tag(axis, sign)
            path = models / evaluator._channel_dirname(axis, sign) / f"{tag}_int8.tflite"
            path.parent.mkdir(parents=True)
            path.touch()
            channels.append({"axis_idx": axis, "sign": sign,
                             "val_mae_uT": float(10 + len(channels))})
    (models / "training_summary.json").write_text(json.dumps({"channels": channels}))
    freq = np.linspace(2.82e9, 2.92e9, 800)
    spectra = np.ones((2, 800))
    predictions = np.array([50., -70., 90., -110., 150., -170., 200., 5000.])
    monkeypatch.setattr(evaluator, "_load_tflite", lambda path: path)
    monkeypatch.setattr(evaluator, "_tflite_predict_batch", lambda path, spectra_norm,
                        lock_bins, sigma_anchor, **kwargs: np.full(len(spectra_norm),
                        predictions[next(i for i, ch in enumerate(channels)
                                         if evaluator._channel_tag(ch["axis_idx"], ch["sign"]) in path.name)]))
    calls = []
    original_blue = evaluator.blue_project

    def capture_blue(pred, geometry, sigma):
        calls.append((pred.copy(), sigma.copy()))
        return original_blue(pred, geometry, sigma=sigma)

    monkeypatch.setattr(evaluator, "blue_project", capture_blue)
    snapshots = []
    for run, labels in enumerate((np.zeros((2, 3)),
                                  np.array([[0.004, 0.003, 0.002],
                                            [-0.004, -0.003, -0.002]]))):
        dataset = tmp_path / f"dataset_{run}.h5"
        with h5py.File(dataset, "w") as h5:
            h5.create_dataset("test/spectra", data=spectra)
            h5.create_dataset("test/labels", data=labels)
            h5.create_dataset("test/frequencies", data=freq)
        output = tmp_path / f"output_{run}.json"
        calls.clear()
        monkeypatch.setattr(sys, "argv", ["vector_v1_eval.py", "--dataset", str(dataset),
                                        "--models", str(models), "--anchor-source", "coarse_fit",
                                        "--out-json", str(output)])
        monkeypatch.setattr(evaluator, "coarse_fit_field",
                            lambda spec, grid: np.zeros((len(spec), 3)))
        evaluator.main()
        result = json.loads(output.read_text())
        snapshots.append((result["n_blue_used"], result["selection_uses_labels"],
                          [ch["n_in_grid"] for ch in result["per_channel"]],
                          [(pred.tolist(), sigma.tolist()) for pred, sigma in calls]))
    assert snapshots[0] == snapshots[1]
    assert snapshots[0][0] == 2
    assert snapshots[0][1] is False
    assert snapshots[0][2][-1] == 0


def test_non_oracle_rejects_label_based_sample_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["vector_v1_eval.py", "--anchor-source", "coarse_fit",
                                    "--filter-bmag-max-mT", "1", "--dataset",
                                    str(tmp_path / "unused.h5")])
    with pytest.raises(SystemExit, match="2"):
        evaluator.main()


def test_residual_metrics_handle_no_usable_sample():
    # A label-free anchor source can leave every sample with fewer than 3 valid channels
    # (plan N, bias set at 2 mT): the summary must report n_blue_used 0, not crash.
    from experiments.vector_v1_eval import _residual_metrics

    lab = np.array([[0.0, 0.0, 10.0], [0.0, 0.0, 10.0]])
    b_hat = np.array([[3.0, 4.0, 10.0], [0.0, 0.0, 0.0]])
    empty = _residual_metrics(b_hat, lab, np.array([False, False]))
    assert empty["blue_3d_residual_uT"] == dict(rms=None, mean=None, p50=None, p90=None, max=None)
    assert empty["blue_3d_residual_pct_of_B"]["rms_over_b_mean"] is None
    assert empty["b_norm_true_uT"]["mean"] is None
    one = _residual_metrics(b_hat, lab, np.array([True, False]))
    assert one["blue_3d_residual_uT"]["rms"] == pytest.approx(5.0)
    assert one["blue_3d_residual_uT"]["p90"] == pytest.approx(5.0)
    assert one["blue_3d_residual_pct_of_B"]["rms_over_b_mean"] == pytest.approx(0.5)
    assert one["blue_per_axis_residual_uT"]["y_p50"] == pytest.approx(4.0)
    assert one["b_norm_true_uT"]["max"] == pytest.approx(10.0)
