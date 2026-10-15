"""Manufactured tests only. Root must authorize their numerical execution."""
import tempfile
from pathlib import Path
import unittest
from unittest import mock
import json

import numpy as np

from experiments.measured_widefield.io import blocks, inspect_header, select_patches
from experiments.measured_widefield.baselines import curve_jacobian
from experiments.measured_widefield.metrics import compare


class WidefieldTests(unittest.TestCase):
    def test_environment_without_supervisor_is_rejected(self):
        from experiments.measured_widefield.access import supervisor_context
        with mock.patch.dict("os.environ", {"TYCHON_NUMERICAL_RUN_ID": "spoofed", "TYCHON_NUMERICAL_APPROVAL_SHA256": "a" * 64}, clear=True):
            with self.assertRaisesRegex(ValueError, "active supervisor"):
                supervisor_context("a" * 64, ["spoofed"], "manufactured-test-authority")

    def test_changed_protocol_is_not_a_configuration_override(self):
        from experiments.measured_widefield.access import validate_protocol
        protocol = json.loads((Path(__file__).parents[1] / "protocol.json").read_text())
        protocol["status"] = "FROZEN"
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "protocol.json"
            path.write_text(json.dumps(protocol))
            validate_protocol(path)
            protocol["candidate"]["epochs"] += 1
            path.write_text(json.dumps(protocol))
            with self.assertRaisesRegex(ValueError, "implemented scientific contract"):
                validate_protocol(path)

    def test_header_only_rejects_incomplete_file_and_uses_exclusive_stop(self):
        cards = {"SIMPLE": "T", "BITPIX": "16", "NAXIS": "4", "NAXIS1": "1280",
                 "NAXIS2": "1024", "NAXIS3": "200", "NAXIS4": "5", "BSCALE": "1",
                 "BZERO": "32768", "NSCANS": "5", "STARFREQ": "2700", "STOPFREQ": "3000", "STEPSIZE": "1.5"}
        content = b"".join((f"{key:<8}= {value:>20}".ljust(80)).encode() for key, value in cards.items())
        content += b"END".ljust(80)
        content = content.ljust(2880, b" ")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "header.fits"
            path.write_bytes(content)
            record = inspect_header(path)
        self.assertFalse(record["complete"])
        self.assertEqual(record["expected_bytes"], 2621445120)
        self.assertEqual(len(record["frequency_mhz"]), 200)
        self.assertEqual(record["frequency_mhz"][-1], 2998.5)

    def test_spatial_groups_are_disjoint_with_guard_bands(self):
        groups = {split: list(blocks(split)) for split in ("train", "development", "final")}
        self.assertEqual([len(value) for value in groups.values()], [32, 16, 16])
        self.assertEqual(len(set(row[0] for value in groups.values() for row in value)), 64)
        for left, right in (("train", "development"), ("development", "final")):
            latest = max(x + 56 + 2 for _, _, x in groups[left])
            earliest = min(x + 8 - 2 for _, _, x in groups[right])
            self.assertGreaterEqual(earliest - latest, 12)

    def test_selection_never_reads_another_repeat(self):
        class InputOnly:
            def __getitem__(self, key):
                if key[0] != 0:
                    raise AssertionError("Held repeat accessed")
                return np.zeros((200, 48, 48), dtype=np.int16)
        patches = select_patches(InputOnly(), 256, 384)
        self.assertEqual(len(patches), 8)
        for y, x in patches:
            self.assertTrue(264 <= y <= 308 and 392 <= x <= 436)

    def test_analytic_lorentzian_jacobian(self):
        frequency = np.linspace(2700, 2998.5, 200)
        parameters = np.array([1.0, 0.01, 12.0, 2800.0, 2900.0, 0.03, 0.02])
        _, analytic = curve_jacobian(parameters, frequency)
        for column in range(len(parameters)):
            step = 1e-5
            offset = np.zeros_like(parameters)
            offset[column] = step
            finite = (curve_jacobian(parameters + offset, frequency)[0] - curve_jacobian(parameters - offset, frequency)[0]) / (2 * step)
            np.testing.assert_allclose(analytic[:, column], finite, atol=2e-9, rtol=2e-5)

    def test_metric_rejects_corrupted_flags_and_times(self):
        rows = np.column_stack((np.zeros(16, dtype=int), np.arange(16), np.zeros((16, 3), dtype=int)))
        target = np.ones((16, 9, 200))
        saved = {"raw__prediction": np.ones((16, 200)), "raw__failed": np.zeros(16, dtype=int),
                 "raw__fit_reliable": np.zeros(16, dtype=bool), "raw__seconds": np.zeros(16)}
        with self.assertRaisesRegex(ValueError, "failure flags"):
            compare(target, rows, saved, 0, shape_edges=np.arange(50))
        saved["raw__failed"] = np.zeros(16, dtype=bool)
        saved["raw__seconds"][0] = np.nan
        with self.assertRaisesRegex(ValueError, "timing"):
            compare(target, rows, saved, 0, shape_edges=np.arange(50))

    def test_training_mask_has_deterministic_ties_and_classical_grid(self):
        from experiments.measured_widefield.baselines import fit_linear_models, METHODS, predict
        data = np.ones((24, 200))
        model = fit_linear_models(data, data, np.zeros_like(data))
        np.testing.assert_array_equal(model["shape_edges"], np.arange(50))
        self.assertEqual(len(METHODS), 12)
        frequency = np.arange(200) * 1.5 + 2700
        for method in METHODS:
            if method == "robust_lorentzian":
                continue  # The derivative fixture covers the nonlinear implementation.
            result, failure, _, _ = predict(method, data[:1], frequency, model)
            np.testing.assert_allclose(result, data[:1], atol=1e-12)
            self.assertFalse(failure.any())

    def test_derivative_guard_rejects_flattening(self):
        rows = np.column_stack((np.zeros(16, dtype=int), np.arange(16), np.zeros((16, 3), dtype=int)))
        profile = np.ones((16, 200)); profile[:, 20:25] = 0.9
        targets = np.repeat(profile[:, None, :], 9, axis=1)
        saved = {}
        for method, prediction in (("raw", profile), ("training_mean", np.ones_like(profile)), ("candidate_16", np.ones_like(profile))):
            saved.update({method + "__prediction": prediction, method + "__failed": np.zeros(16, dtype=bool),
                          method + "__fit_reliable": np.zeros(16, dtype=bool), method + "__seconds": np.zeros(16)})
        result, _ = compare(targets, rows, saved, 0, shape_edges=np.arange(50), frozen_candidate="candidate_16")
        self.assertFalse(result["candidate_gate"]["conditions"]["shape_derivative_within_2pct_of_classical"])
        self.assertFalse(result["candidate_gate"]["conditions"]["shape_derivative_5pct_better_than_mean_null"])

    def test_perfect_reference_never_becomes_percentage_improvement(self):
        rows = np.column_stack((np.zeros(16, dtype=int), np.arange(16), np.zeros((16, 3), dtype=int)))
        targets = np.ones((16, 9, 200)); saved = {}
        for method in ("raw", "training_mean", "candidate_16", "candidate_32", "candidate_64"):
            saved.update({method + "__prediction": targets[:, 0].copy(), method + "__failed": np.zeros(16, dtype=bool),
                          method + "__fit_reliable": np.zeros(16, dtype=bool), method + "__seconds": np.zeros(16)})
        result, _ = compare(targets, rows, saved, 0, shape_edges=np.arange(50))
        self.assertEqual(result["selected_candidate"], "candidate_16")
        self.assertEqual(result["candidate_gate"]["mse_ratio_ci95"], [1.0, 1.0])
        self.assertFalse(result["candidate_gate"]["passed"])
        self.assertFalse(result["candidate_gate"]["conditions"]["mse_improvement_at_least_5pct"])

    def test_candidate_numpy_matches_torch_manufactured_weights(self):
        try:
            import torch
        except ImportError:
            self.skipTest("Torch unavailable; parity remains a candidate-stage requirement")
        from experiments.measured_widefield.candidate import network, predict
        for width in (16, 32, 64):
            model = network(width)
            self.assertEqual(sum(parameter.numel() for parameter in model.parameters()), 401 * width + 200)
            with torch.no_grad():
                for parameter in model.parameters():
                    parameter.copy_(torch.linspace(-0.001, 0.001, parameter.numel()).reshape(parameter.shape))
            data = np.linspace(0.95, 1.05, 400, dtype=np.float32).reshape(2, 200)
            weights = {key: value.detach().numpy() for key, value in model.state_dict().items()}
            expected = data + model(torch.from_numpy(data - 1)).detach().numpy()
            actual, failed, _ = predict(data, weights)
            np.testing.assert_allclose(actual, expected, atol=2e-7, rtol=1e-6)
            self.assertFalse(failed.any())


if __name__ == "__main__":
    unittest.main()
