import tempfile
import unittest
from pathlib import Path
import numpy as np
import readout_pilot as r


class ReadoutTests(unittest.TestCase):
    def setUp(self):
        self.c = r.load_config()

    def test_vacuum_and_zero_drive(self):
        t = r.time_axis(self.c)
        self.assertTrue(np.array_equal(r.analytic_alpha(t, 2, 0, 3), np.zeros(len(t))))
        self.assertEqual(r.analytic_alpha([0], 2, 1, 3)[0], 0)

    def test_on_resonance_sign_and_steady_state(self):
        a = r.analytic_alpha([0, 100], 0, 2, 4)
        np.testing.assert_allclose(a, [0, -1j])

    def test_negative_detuning_symmetry(self):
        t = r.time_axis(self.c)
        np.testing.assert_allclose(r.analytic_alpha(t, -2, 1, 4), -r.analytic_alpha(t, 2, 1, 4).conj())

    def test_invalid_physical_parameters(self):
        for args in (([-1], 0, 1, 1), ([0], 0, 1, 0), ([0], np.nan, 1, 1)):
            with self.assertRaises(ValueError):
                r.analytic_alpha(*args)

    def test_independent_density_model(self):
        t = np.linspace(0, 0.7, 15)
        d = r.density_evolve(t, 2, 1, 4, 10, 0.002)
        self.assertLess(np.max(abs(d["alpha"]-r.analytic_alpha(t, 2, 1, 4))), 1e-6)
        self.assertLess(d["trace_error"], 1e-10)
        self.assertGreater(d["minimum_eigenvalue"], -1e-7)

    def test_fresh_group_splits_and_stress_pairing(self):
        d, _ = r.generate(self.c)
        ids = {s: set(d["device_id"][d["split"] == s]) for s in ("train", "validation", "test", "stress")}
        self.assertFalse(ids["train"] & ids["test"])
        self.assertFalse(ids["train"] & ids["validation"])
        self.assertFalse(ids["validation"] & ids["test"])
        self.assertEqual(ids["test"], ids["stress"])
        for s in ids:
            yy = d["y"][d["split"] == s]
            self.assertEqual(int(yy.sum()), len(yy)//2)

    def test_dataset_repeatability(self):
        c = dict(self.c, devices={"train": 2, "validation": 2, "test": 2})
        a, _ = r.generate(c)
        b, _ = r.generate(c)
        np.testing.assert_array_equal(a["x"], b["x"])

    def test_quantization_saturates_and_rejects_nan(self):
        q, clipped = r.quantize_input(np.array([-100, -16, 0, 32767/2048, 100]))
        np.testing.assert_array_equal(q, [-32768, -32768, 0, 32767, 32767])
        self.assertEqual(clipped, 2)
        with self.assertRaises(ValueError):
            r.quantize_input(np.array([np.nan]))

    def test_c_arithmetic_and_full_scale_bound(self):
        rng = np.random.default_rng(718)
        x = rng.integers(-32768, 32768, (300, 128), dtype=np.int16)
        w = rng.integers(-32768, 32768, 128, dtype=np.int16)
        bias = 123456789
        expected = x.astype(np.int64)@w.astype(np.int64)+bias
        with tempfile.TemporaryDirectory() as path:
            np.testing.assert_array_equal(r.c_scores(r.compile_c(Path(path)), x, w, bias), expected)
        bound = sum(abs(int(a))*32768 for a in w)+abs(bias)
        self.assertLess(int(np.max(abs(expected))), bound)


if __name__ == "__main__":
    unittest.main()
