import json
from pathlib import Path
import unittest
import numpy as np
from nv_model import (config, hamiltonian, sequence_density, rk4_density,
                      probabilities, probability_features, quantize, integer_match,
                      RHO0, P0, evolve)


def bloch_rotate(v, axis, angle):
    n = axis / np.linalg.norm(axis)
    return v*np.cos(angle) + np.cross(n, v)*np.sin(angle) + n*np.dot(n, v)*(1-np.cos(angle))


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config()
        self.m = self.cfg["model"].copy()

    def test_hamiltonian_and_density_invariants(self):
        for d in [-.75, 0., .75]:
            h = hamiltonian(d, self.m, .7, True)
            np.testing.assert_allclose(h, h.conj().T, atol=1e-14)
            for delay in [0., .1, 4.]:
                r = sequence_density(d, delay, .9, self.m)
                np.testing.assert_allclose(r, r.conj().T, atol=1e-12)
                self.assertAlmostEqual(np.trace(r).real, 1., places=12)
                self.assertGreaterEqual(np.linalg.eigvalsh(r).min(), -1e-12)
                self.assertAlmostEqual(np.trace(r@r).real, .5, places=12)

    def test_independent_commutator_rk4(self):
        errors = []
        for d, delay, phase in [(-.75, 4., 0.), (.75, 4., np.pi/2),
                                (0., 2.17, np.pi), (.123, 0., .73),
                                (-.213, .318, 3*np.pi/2), (.61, 1.51, .29)]:
            exact = sequence_density(d, delay, phase, self.m)
            numerical = sequence_density(d, delay, phase, self.m, rk4_density)
            errors.append(float(np.max(np.abs(exact-numerical))))
            np.testing.assert_allclose(exact, numerical, atol=1e-7, rtol=0)
        print("Independent RK4 maximum density error:", max(errors))

    def test_zero_coupling_finite_pulse_bloch(self):
        self.m.update(hyperfine_parallel_mhz=0., hyperfine_transverse_mhz=0.)
        omega = self.m["rabi_mhz"]
        pulse = 1/(4*omega)
        for d in [-.75, 0., .75]:
            for phase in [0., np.pi/2, np.pi, 3*np.pi/2]:
                v = np.array([0., 0., 1.])
                axis = np.array([0., omega, d])
                v = bloch_rotate(v, axis, 2*np.pi*np.linalg.norm(axis)*pulse)
                v = bloch_rotate(v, np.array([0.,0.,1.]), 2*np.pi*d*1.37)
                axis = np.array([omega*np.sin(phase), -omega*np.cos(phase), d])
                v = bloch_rotate(v, axis, 2*np.pi*np.linalg.norm(axis)*pulse)
                expected = (1+v[2])/2
                actual = np.trace(P0@sequence_density(d, 1.37, phase, self.m)).real
                self.assertAlmostEqual(actual, expected, places=12)

    def test_ideal_pulse_limit_and_phase_sign(self):
        self.m.update(hyperfine_parallel_mhz=0., hyperfine_transverse_mhz=0., rabi_mhz=1e8)
        delays = np.array([0., .01, 1.3, 4.])
        phases = np.asarray(self.cfg["phases_rad"])
        p = probabilities(.31, delays, phases, self.m)
        ref = (1+np.cos(2*np.pi*.31*delays[None,:]-phases[:,None]))/2
        np.testing.assert_allclose(p, ref, atol=1e-8, rtol=0)
        self.assertGreater(probability_features(p)[len(delays)+1], 0.)

    def test_vectorized_sequence_equals_direct(self):
        t = np.array([0., .7, 4.])
        p = probabilities(-.371, t, self.cfg["phases_rad"], self.m)
        for i, phase in enumerate(self.cfg["phases_rad"]):
            for j, delay in enumerate(t):
                ref = np.trace(P0@sequence_density(-.371, delay, phase, self.m)).real
                self.assertAlmostEqual(p[i,j], ref, places=12)

    def test_transverse_coupling_changes_observables(self):
        t = np.linspace(0.,4.,64)
        actual = probabilities(.23,t,self.cfg["phases_rad"],self.m)
        self.m["hyperfine_transverse_mhz"] = 0.
        no_transverse = probabilities(.23,t,self.cfg["phases_rad"],self.m)
        self.assertGreater(np.max(np.abs(actual-no_transverse)), .01)

    def test_quantization_bounds_and_overflow(self):
        q, clipping = quantize([-3., -2., 0., 1., 3.])
        self.assertEqual(clipping, 2)
        np.testing.assert_array_equal(q, [-32768,-32768,0,16384,32767])
        idx, score = integer_match(np.full(128,-32768,dtype=np.int16),
                                   np.full((1,128),32767,dtype=np.int16))
        self.assertEqual(score, 128*65535**2)
        self.assertEqual(idx, 0)
        with self.assertRaises(ValueError):
            quantize([np.nan])

    def test_invalid_model_and_delays(self):
        with self.assertRaises(ValueError):
            probabilities(0.,[-1.],[0.],self.m)
        self.m["rabi_mhz"] = 0.
        with self.assertRaises(ValueError):
            hamiltonian(0.,self.m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
