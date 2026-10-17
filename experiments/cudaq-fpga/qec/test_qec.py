import json
from pathlib import Path
import unittest

from qec_model import (HX, HZ, LX, LZ, N, STABILIZERS, exact_failure,
                       logical_class, maximum_likelihood_lut, parity,
                       reference_syndrome, syndrome, tables, weight)


class CodeTests(unittest.TestCase):
    def test_commutation_and_rank(self):
        self.assertTrue(all(parity(x & z) == 0 for x in HX for z in HZ))
        self.assertEqual(len(STABILIZERS), 256)  # rank 8; k=9-8=1
        self.assertEqual(parity(LX & LZ), 1)
        self.assertEqual(syndrome(LX), 0)
        self.assertEqual(syndrome(LZ << N), 0)

    def test_full_pauli_space_against_support_reference_and_stabilizer_group(self):
        zero_syndrome, nontrivial_weights = 0, []
        for error in range(1 << (2 * N)):
            s = syndrome(error)
            self.assertEqual(s, reference_syndrome(error))
            if s == 0:
                zero_syndrome += 1
                self.assertEqual(logical_class(error) == 0, error in STABILIZERS)
                if error not in STABILIZERS:
                    nontrivial_weights.append(weight(error))
        self.assertEqual(zero_syndrome, 1024)
        self.assertEqual(min(nontrivial_weights), 3)

    def test_corrections_and_all_single_pauli_errors(self):
        joint, separate, _, _, _, _ = tables()
        for lut in (joint, separate, maximum_likelihood_lut(0.03)):
            for s, correction in enumerate(lut):
                self.assertEqual(syndrome(correction), s)
            for q in range(N):
                for pauli in (1, 2, 3):
                    error = ((pauli & 1) << q) | (((pauli >> 1) & 1) << (q + N))
                    self.assertIn(error ^ lut[syndrome(error)], STABILIZERS)

    def test_exhaustive_decoding_classification(self):
        lut = maximum_likelihood_lut(0.03)
        for error in range(1 << (2 * N)):
            residual = error ^ lut[syndrome(error)]
            self.assertEqual(syndrome(residual), 0)
            self.assertEqual(logical_class(residual) == 0, residual in STABILIZERS)

    def test_probability_boundaries_and_enumeration(self):
        _, _, counts, _, _, _ = tables()
        self.assertEqual(sum(sum(sum(row) for row in syndrome_rows) for syndrome_rows in counts), 4**N)
        self.assertEqual({sum(row) for syndrome_rows in counts for row in syndrome_rows}, {256})
        lut = maximum_likelihood_lut(0.03)
        self.assertEqual(exact_failure(lut, 0), (0, 1))
        failure, total = exact_failure(lut, 0.75)
        self.assertAlmostEqual(total, 1, places=12)
        self.assertAlmostEqual(failure, 0.75, places=12)

    def test_frozen_config_matches_implementation(self):
        config = json.loads(Path(__file__).with_name("config.json").read_text())
        self.assertEqual(HX, tuple(sum(1 << q for q in support) for support in config["x_checks"]))
        self.assertEqual(HZ, tuple(sum(1 << q for q in support) for support in config["z_checks"]))
        self.assertEqual(config["design_error_probability"], 0.03)


if __name__ == "__main__":
    unittest.main(verbosity=2)
