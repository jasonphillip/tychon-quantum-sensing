"""Prepared tests. Do not run before root's registered numerical-test allowance."""
from dataclasses import replace
import unittest
import numpy as np
from experiments.sparse_acquisition_screen.core import (
    Acquisition, AcquisitionOracle, Observation, GridBelief, UniformPolicy,
    CoarseToFinePolicy, FisherPolicy, BayesianPolicy, Point, simulate_episode,
)
from experiments.sparse_acquisition_screen.run_screen import authorize
import json
from pathlib import Path
import tempfile


class SparseAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.config = Acquisition(primary_actions=3, recovery_actions=1, maximum_actions=4)
        self.prior = GridBelief(axes=(np.array([20.,45.,70.]), np.array([0.,.6]),
                                    np.array([4.,6.])))
        self.truth = Point(field_uT=45., bias_uT=250.)

    def test_observation_is_counted_and_causal(self):
        oracle = AcquisitionOracle(self.truth, self.config, 1267650600228229401496703477204)
        first = oracle.acquire(40)
        second = oracle.acquire(40)
        third = oracle.acquire(41)
        self.assertEqual(first.exposure_photons, self.config.exposure_photons)
        self.assertEqual(first.settling_seconds, self.config.settling_seconds)
        self.assertEqual(second.settling_seconds, 0)
        self.assertEqual(third.settling_seconds, self.config.settling_seconds)
        self.assertIsInstance(first.count, int)
        self.assertFalse(hasattr(first, "truth"))
        self.assertFalse(hasattr(first, "spectrum"))
        oracle.acquire(42)
        with self.assertRaises(RuntimeError):
            oracle.acquire(43)

    def test_invalid_observation_and_budget(self):
        with self.assertRaises(ValueError):
            replace(self.config, maximum_actions=2).validate()
        for bad in (Observation(-1,1,1.,1.,0.,False), Observation(1,-1,1.,1.,0.,False),
                    Observation(1,1,0.,1.,0.,False)):
            with self.assertRaises(ValueError):
                self.prior.update(bad)

    def test_posterior_matches_poisson_likelihood(self):
        obs = Observation(49, 101, 100., 1., 0., False)
        mu = self.prior.rates[:,49]
        expected = obs.count*np.log(mu)-obs.exposure_photons*mu
        expected = np.exp(expected-expected.max())
        expected /= expected.sum()
        self.prior.update(obs)
        np.testing.assert_allclose(self.prior.weights, expected, rtol=1e-12)
        self.assertAlmostEqual(self.prior.weights.sum(),1.)

    def test_policy_interfaces_do_not_receive_truth(self):
        for policy in (UniformPolicy(),CoarseToFinePolicy(),FisherPolicy(),BayesianPolicy(2,3)):
            index = policy.choose(self.prior,self.config,())
            self.assertIsInstance(index,int)
            self.assertGreaterEqual(index,0)
            self.assertLess(index,100)

    def test_recovery_and_costs_are_included(self):
        config = replace(self.config, credible_half_width_uT=1e-12, photon_rate=1.)
        result = simulate_episode(self.truth,1267650600228229401496703519535,UniformPolicy(),self.prior,config)
        self.assertEqual(result["actions"],4)
        self.assertEqual(result["recovery_actions"],1)
        self.assertTrue(result["failed_precision"])
        self.assertEqual(result["incident_photon_budget"],4*config.exposure_photons)
        expected = sum(result[k] for k in ("dwell_seconds","settling_seconds",
                                           "decision_seconds","update_seconds"))
        self.assertAlmostEqual(result["modeled_total_seconds"],expected)
        self.assertEqual(len(result["trace"]),4)

    def test_prior_is_not_mutated_between_methods(self):
        before = self.prior.weights.copy()
        simulate_episode(self.truth,1267650600228229401496703367179,UniformPolicy(),self.prior,self.config)
        np.testing.assert_array_equal(before,self.prior.weights)
        self.assertEqual(self.prior.observations,[])
        self.assertFalse(self.prior.rates.flags.writeable)
        self.assertFalse(self.prior.states.flags.writeable)

    def test_repeat_seed_reproduces_observations_not_wall_timing(self):
        a = simulate_episode(self.truth,1267650600228229401496703346797,UniformPolicy(),self.prior,self.config)
        b = simulate_episode(self.truth,1267650600228229401496703346797,UniformPolicy(),self.prior,self.config)
        self.assertEqual([x["count"] for x in a["trace"]],[x["count"] for x in b["trace"]])
        self.assertEqual(a["estimate_uT"],b["estimate_uT"])

    def test_poisson_variance_scales_with_dwell(self):
        # Distribution test, only executable under a later numerical-test gate.
        config = replace(self.config, maximum_actions=2000, primary_actions=2000,
                         recovery_actions=0, photon_rate=10000., dwell_seconds=.1)
        normalized_variances = []
        means = []
        for j, dwell in enumerate((.1, .2)):
            current = replace(config, dwell_seconds=dwell)
            oracle = AcquisitionOracle(self.truth,current,(1<<100)+173205+j)
            counts = np.array([oracle.acquire(0).count for _ in range(2000)])
            self.assertLess(abs(counts.var()/counts.mean()-1),.15)
            means.append(counts.mean())
            normalized_variances.append((counts/current.exposure_photons).var())
        self.assertLess(abs(means[1]/means[0]-2),.05)
        self.assertLess(abs(normalized_variances[0]/normalized_variances[1]-2),.4)

    def test_unapproved_gate_refuses_before_numerical_work(self):
        with tempfile.TemporaryDirectory() as folder:
            gate = Path(folder)/"gate.json"
            gate.write_text(json.dumps({"status":"PREPARATION_ONLY"}))
            with self.assertRaisesRegex(RuntimeError,"unregistered"):
                authorize(gate,Path(folder)/"nonexistent-cases.json")


if __name__ == "__main__":
    unittest.main()
