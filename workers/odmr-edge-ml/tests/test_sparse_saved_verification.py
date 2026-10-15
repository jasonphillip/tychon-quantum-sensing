"""Manufactured arithmetic checks; execute only inside registered accounting."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from experiments.sparse_acquisition_screen.verify_saved import (
    posterior, wasserstein, quantile, verify_development, sha)


class SparseSavedVerificationTests(unittest.TestCase):
    def test_posterior_reconstructs_likelihood_ratio(self):
        table={"states":[[20,0,4],[70,0,4]],"rates":[[.9],[1.1]]}
        obs=[{"index":0,"count":1,"exposure_photons":1.}]
        actual=posterior(table,obs)
        values=[.9*math.exp(-.9),1.1*math.exp(-1.1)]
        self.assertAlmostEqual(actual["weights"][0],values[0]/sum(values),places=14)
        self.assertAlmostEqual(sum(actual["weights"]),1.)

    def test_wasserstein_counts_location_not_index(self):
        self.assertEqual(wasserstein([(20.,1.)],[(22.,1.)]),2.)
        self.assertAlmostEqual(wasserstein([(20.,.5),(22.,.5)],[(21.,1.)]),1.)

    def test_percentile_matches_linear_definition(self):
        self.assertAlmostEqual(quantile([4.,1.,3.,2.],.9),3.7)

    def fixture(self,folder):
        config={"photon_rate":5e8,"dwell_seconds":.01,"settling_seconds":.0003,
                "primary_actions":24,"recovery_actions":8,"maximum_actions":32,
                "credible_half_width_uT":2.}
        trace={"index":50,"count":5000000,"exposure_photons":5000000.,
               "dwell_seconds":.01,"settling_seconds":.0003,"recovered":False,
               "decision_seconds":.002,"update_seconds":.001,
               "estimate_uT":45.,"mean_uT":45.,"lower_uT":44.,"upper_uT":46.,
               "boundary_mass":0.,"internal_precision_stop":True}
        row={k:trace[k] for k in ("estimate_uT","mean_uT","lower_uT","upper_uT","boundary_mass")}
        row.update(case_id="fixture",truth_uT=45.,absolute_error_uT=0.,interval_contains_truth=True,
            actions=1,recovery_actions=0,failed_precision=False,internal_precision_stop=True,
            dwell_seconds=.01,settling_seconds=.0003,decision_seconds=.002,update_seconds=.001,
            episode_setup_seconds=.0001,policy_setup_seconds=.0002,modeled_total_seconds=.0136,
            normalized_exposure_photons=5000000.,detected_photons=5000000,trace=[trace])
        cases={"partition":"fresh-development","cases":[{"case_id":"fixture","point":{"field_uT":45.}}]}
        (folder/"cases.json").write_text(json.dumps(cases))
        result={"status":"development-only","cases_sha256":sha(folder/"cases.json"),"acquisition":config,
                "rows":[dict(copy.deepcopy(row),policy=name) for name in
                        ("uniform","coarse_to_fine","nuisance_fisher","bayesian_variance")]}
        return result

    def test_saved_development_metrics_without_model(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name); result=self.fixture(folder)
            (folder/"results.json").write_text(json.dumps(result))
            report=verify_development(folder)
            self.assertEqual(report["status"],"saved_development_verified")
            self.assertEqual(report["metrics"]["uniform"]["mae_uT"],0.)

    def test_altered_saved_error_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name); result=self.fixture(folder)
            result["rows"][0]["absolute_error_uT"]=1.
            (folder/"results.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,"absolute error"):
                verify_development(folder)

    def test_unpaid_recovery_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name); result=self.fixture(folder)
            result["rows"][0]["trace"][0]["recovered"]=True
            (folder/"results.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,"recovery flag"):
                verify_development(folder)


if __name__=="__main__":
    unittest.main()
