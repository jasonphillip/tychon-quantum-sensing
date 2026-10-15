"""Manufactured tests only. Root must authorize their numerical execution."""
import tempfile
from pathlib import Path
import unittest

import numpy as np

from experiments.measured_widefield.io import blocks, inspect_header, select_patches
from experiments.measured_widefield.baselines import curve_jacobian
from experiments.measured_widefield.metrics import compare


class WidefieldTests(unittest.TestCase):
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
            compare(target, rows, saved, 0)
        saved["raw__failed"] = np.zeros(16, dtype=bool)
        saved["raw__seconds"][0] = np.nan
        with self.assertRaisesRegex(ValueError, "timing"):
            compare(target, rows, saved, 0)

    def test_candidate_numpy_matches_torch_manufactured_weights(self):
        try:
            import torch
        except ImportError:
            self.skipTest("Torch unavailable; parity remains a candidate-stage requirement")
        from experiments.measured_widefield.candidate import network, predict
        model = network()
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
