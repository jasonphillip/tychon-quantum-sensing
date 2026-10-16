"""Manufactured scientific and policy contracts; no development data."""
import unittest
from unittest.mock import patch
import numpy as np
from experiments.vector_direct_screen.physics import Engine,CFG
from experiments.vector_direct_screen.baseline import deviance,initialize
from experiments.vector_initializer_development import learning,methods,evaluation

def certificate():
    return dict(purpose="vector_p1",status="ISSUED",freshness_attestation="ROOT_CONFIRMED_NOT_PREVIOUSLY_USED",
        **{n:str(i+301) for i,n in enumerate(learning.SEED_NAMES)})

def example_gate_inputs():
    stats={n:dict(mean_uT=2.,p95_uT=4.,rejections=0) for n in methods.METHODS}
    timings={n:{str(b):dict(host_to_host_seconds=[1.,1.,1.],resident_seconds=[.8,.8,.8]) for b in evaluation.BATCHES} for n in methods.METHODS}
    for b in evaluation.BATCHES:timings["neural1"][str(b)]["host_to_host_seconds"]=[.4,.4,.4]
    return stats,timings

class Contracts(unittest.TestCase):
    def test_seeds_are_fresh_distinct_and_p1_specific(self):
        c=certificate();self.assertEqual(len(learning.seed_values(c)),5)
        c["validation_noise_seed"]=c["train_noise_seed"]
        with self.assertRaises(ValueError):learning.seed_values(c)
        c=certificate();c["purpose"]="vector_p0"
        with self.assertRaises(ValueError):learning.seed_values(c)

    def test_train_only_scaling_and_nonzero_floor(self):
        x=np.array([[2000000,2000000],[4000000,2000000]],dtype=np.int64)
        mean,std=learning.feature_scaling(x)
        np.testing.assert_array_equal(mean,[1.5,1.]);np.testing.assert_array_equal(std,[.5,1e-6])

    def test_normalized_targets_cover_all_eight_physical_units(self):
        center,scale=learning.target_scaling()
        np.testing.assert_allclose((np.asarray(CFG["lower"])-center)/scale,-np.ones(8),atol=1e-11)
        np.testing.assert_allclose((np.asarray(CFG["upper"])-center)/scale,np.ones(8),atol=1e-11)

    def test_architecture_is_exact_and_linear_at_output(self):
        import torch
        model=learning.build_model(torch)
        self.assertEqual([(m.in_features,m.out_features) for m in model if isinstance(m,torch.nn.Linear)],[(512,256),(256,128),(128,64),(64,8)])
        self.assertEqual(sum(p.numel() for p in model.parameters()),173000)
        self.assertIsInstance(model[-1],torch.nn.Linear)
        self.assertEqual(sum(isinstance(m,torch.nn.ReLU) for m in model),3)

    def test_refinement_attempts_exact_budget_without_early_stop(self):
        e=Engine();p=np.asarray([CFG["nominal"]],float);counts=e.spectrum(p)*CFG["photons_per_bin"]
        for steps in (1,3,5):
            with patch.object(e,"spectrum",wraps=e.spectrum) as spy:
                result,accepts=methods.refine(e,counts,p.copy(),steps)
            self.assertEqual(spy.call_count,1+2*steps);self.assertEqual(accepts.shape,(1,steps))
            np.testing.assert_allclose(result,p,rtol=0,atol=1e-10)
        with self.assertRaises(ValueError):methods.refine(e,counts,p,2)

    def test_one_lm_step_matches_independent_normal_equation(self):
        e=Engine();truth=np.asarray([CFG["nominal"]],float);truth[0,:3]=[4.,-3.,2.]
        counts=e.spectrum(truth)*CFG["photons_per_bin"];p=initialize(e,counts,"affine")
        rate,jac=e.spectrum(p,True);J=jac[0]*e.scale;weights=CFG["photons_per_bin"]/rate[0]
        normal=J.T@(weights[:,None]*J);rhs=J.T@(weights*(counts[0]/CFG["photons_per_bin"]-rate[0]))
        delta=np.linalg.solve(normal+.01*np.diag(np.maximum(np.diag(normal),1e-12)),rhs)
        proposed=np.clip(p+delta*e.scale,e.lower,e.upper)
        expected=proposed if deviance(e,counts,e.spectrum(proposed),CFG["photons_per_bin"])[0]<=deviance(e,counts,rate,CFG["photons_per_bin"])[0] else p
        actual,_=methods.refine(e,counts,p.copy(),1)
        np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-9)

    def test_common_guard_triggers_identical_full_fallback(self):
        e=Engine();p=np.asarray([CFG["nominal"]],float);counts=e.spectrum(p)*CFG["photons_per_bin"]
        repaired=dict(parameters=p.copy(),accepted=np.array([True]),reduced_deviance=np.array([0.]))
        for name in ("affine1","neural1"):
            with patch.object(methods,"observed_check",return_value=(np.array([False]),np.array([3.]))),patch.object(methods,"full_fallback",return_value=repaired) as fallback:
                result=methods.policy(e,counts,name,neural=lambda observations:p.copy())
            self.assertEqual(fallback.call_count,1);self.assertTrue(result["fallback"][0]);self.assertTrue(result["accepted"][0])

    def test_error_metrics_include_rejected_cases(self):
        truth=np.zeros((2,8));pred=truth.copy();pred[:,0]=[1,9]
        m=evaluation.metrics(pred,truth,np.array([True,False]),np.array([False,True]))
        self.assertEqual(m["mean_uT"],5);self.assertEqual(m["rejections"],1);self.assertEqual(m["n"],2)

    def test_neural_gate_rejects_more_than_five_percent_error(self):
        s,t=example_gate_inputs();self.assertTrue(evaluation.opportunity_gate(s,t,10)["continuation_pass"])
        s["neural1"]["p95_uT"]=4.2001
        self.assertFalse(evaluation.opportunity_gate(s,t,10)["continuation_pass"])

    def test_neural_gate_uses_primary4096_not_small_batch(self):
        s,t=example_gate_inputs();t["neural1"]["1"]["host_to_host_seconds"]=[10,10,10]
        self.assertTrue(evaluation.opportunity_gate(s,t,10)["continuation_pass"])
        t["neural1"]["4096"]["host_to_host_seconds"]=[.5001]*3
        self.assertFalse(evaluation.opportunity_gate(s,t,10)["continuation_pass"])

    def test_best_adequate_classical_and_rejections_are_not_hidden(self):
        s,t=example_gate_inputs();s["affine1"]["mean_uT"]=3
        g=evaluation.opportunity_gate(s,t,10);self.assertNotIn("affine1",g["adequate_classical"])
        s["neural1"]["rejections"]=1
        self.assertFalse(evaluation.opportunity_gate(s,t,10)["continuation_pass"])

    def test_classical_tie_favors_fewer_steps_but_requires_tied_comparator(self):
        s,t=example_gate_inputs()
        for b in evaluation.BATCHES:
            t["affine1"][str(b)]["host_to_host_seconds"]=[.31]*3
            t["affine3"][str(b)]["host_to_host_seconds"]=[.30]*3
        g=evaluation.opportunity_gate(s,t,10,{"affine1":.1})["classical_engineering_opportunity"]
        self.assertEqual(g["selected"],"affine1");self.assertTrue(g["provisional_vs_full_lm"])
        self.assertIsNone(g["engineering_opportunity_pass"]);self.assertFalse(g["neural_win"])
