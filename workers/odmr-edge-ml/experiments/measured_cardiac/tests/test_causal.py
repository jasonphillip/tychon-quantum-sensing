"""Manufactured causality checks; no public dataset or population evidence."""
import unittest
import numpy as np
from experiments.measured_cardiac.causal import CausalFilter, CausalNLMS, aggregate_completed_beats

class CausalTests(unittest.TestCase):
    def test_filter_chunk_invariance(self):
        x = np.arange(40, dtype=float)
        full = CausalFilter(200, lowpass_hz=30).process(x)
        chunked = CausalFilter(200, lowpass_hz=30)
        result = np.concatenate((chunked.process(x[:13]), chunked.process(x[13:])))
        np.testing.assert_allclose(result, full, atol=1e-12, rtol=1e-12)

    def test_future_cannot_change_filter_prefix(self):
        x = np.zeros(40)
        future = x.copy()
        future[20:] = 10
        a = CausalFilter(200, lowpass_hz=30).process(x)
        b = CausalFilter(200, lowpass_hz=30).process(future)
        np.testing.assert_array_equal(a[:20], b[:20])

    def test_nlms_predicts_before_weight_update(self):
        filt = CausalNLMS(taps=1, step=0.5, epsilon=1e-12)
        out = filt.process([2., 2.], [1., 1.])
        self.assertEqual(out[0], 2.)
        self.assertLess(out[1], 2.)

    def test_nlms_future_cannot_change_prefix(self):
        x, r = np.ones(40), np.arange(40, dtype=float)
        changed = r.copy()
        changed[20:] = -100
        a = CausalNLMS().process(x, r)
        b = CausalNLMS().process(x, changed)
        np.testing.assert_array_equal(a[:20], b[:20])

    def test_aggregation_does_not_accept_negative_quality(self):
        with self.assertRaises(ValueError):
            aggregate_completed_beats([[1., 2.], [3., 4.]], method="quality_weighted", weights=[1., -1.])

    def test_median_rejects_extreme_completed_beat(self):
        result = aggregate_completed_beats([[1., 2.], [1., 2.], [100., 200.]], method="median")
        np.testing.assert_array_equal(result, [1., 2.])

if __name__ == "__main__":
    unittest.main()
