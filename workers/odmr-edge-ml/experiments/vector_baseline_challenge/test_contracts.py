"""Manufactured checks only. Run exclusively through approved accounting."""
import ast,inspect,unittest
from unittest.mock import patch
import numpy as np
from experiments.vector_direct_screen.physics import CFG,Engine
from experiments.vector_direct_screen.baseline import initialize,observed_check
from experiments.vector_initializer_development import methods as prior
from experiments.vector_baseline_challenge import methods,data,verify_saved,evaluation

class Contracts(unittest.TestCase):
    def test_exact_routes(self):
        self.assertEqual(methods.METHODS,("lm","affine3","tied12","neural1","affine2_f64","affine2_f32","affine3_f32","neural0"))
    def test_update_algebra_unchanged(self):
        old=ast.parse(inspect.getsource(prior.refine)).body[0]
        new=ast.parse(inspect.getsource(methods.refine)).body[0]
        self.assertEqual(ast.dump(ast.Module(body=old.body[2:],type_ignores=[])),ast.dump(ast.Module(body=new.body[2:],type_ignores=[])))
    def test_two_or_three_only(self):
        for steps in (0,1,4,5):
            with self.assertRaises(ValueError):methods.refine(None,None,None,steps)
    def test_three_steps_matches_frozen(self):
        e=Engine();p=np.array([CFG["nominal"]],float);p[0,:3]=[2,-1,.5];counts=np.rint(e.spectrum(p)*2000000)
        initial=initialize(e,counts,"affine")
        a=methods.refine(e,counts,initial,3);b=prior.refine(e,counts,initial,3)
        for x,y in zip(a,b):np.testing.assert_array_equal(x,y)
    def test_float32_step_fidelity(self):
        import torch
        e64=Engine("torch","cpu","float64");e32=Engine("torch","cpu","float32")
        p=np.tile(CFG["nominal"],(3,1));p[:,:3]=[[0,0,0],[2,-1,.5],[-3,2,1]]
        counts=np.rint(e64.numpy(e64.spectrum(e64.array(p)))*2000000)
        for steps in (2,3):
            predictions=[]
            for e in (e64,e32):
                c=e.array(counts);q,flags=methods.refine(e,c,initialize(e,c,"affine"),steps)
                self.assertEqual(tuple(flags.shape),(3,steps));predictions.append(e.numpy(q).astype(float))
            error=np.linalg.norm(predictions[0][:,:3]-predictions[1][:,:3],axis=1)
            self.assertLessEqual(float(error.max()),CFG["noiseless_field_tolerance_uT"])
    def test_double_guard_rejects_float32_engine(self):
        with self.assertRaises(ValueError):methods.double_guard(Engine(dtype="float32"),None,None)
    def test_double_guard_matches_independent_saved_formula(self):
        e=Engine();p=np.array([CFG["nominal"]],np.float32);q=p.astype(np.float64)
        rates=e.spectrum(q);counts=np.rint(rates*2000000).astype(np.int64)
        out,a,r=methods.double_guard(e,counts,p)
        aa,rr=verify_saved.guard_from_saved(counts,out,e.spectrum(out),CFG["lower"],CFG["upper"])
        self.assertEqual(out.dtype,np.float64);np.testing.assert_array_equal(a,aa);np.testing.assert_allclose(r,rr,rtol=0,atol=1e-6)
    def test_no_post_cast_clamp(self):
        e=Engine();p=np.array([CFG["nominal"]],float);p[0,0]=20.00001
        counts=np.rint(e.spectrum(e.array([CFG["nominal"]]))*2000000)
        out,accepted,_=methods.double_guard(e,counts,p)
        self.assertEqual(out[0,0],p[0,0]);self.assertFalse(accepted[0])
    def test_neural_zero_uses_double_fallback(self):
        e=Engine();truth=e.array([CFG["nominal"]]);counts=np.rint(e.spectrum(truth)*2000000)
        proposal=truth.copy();proposal[0,0]=25
        seen=[]
        def fallback(engine,c):
            seen.append((engine.real_dtype,c.dtype));return {"parameters":truth.copy(),"accepted":np.ones(1,bool),"reduced_deviance":np.zeros(1)}
        with patch.object(methods,"full_fallback",fallback):result=methods.policy(e,counts,"neural0",lambda c:proposal.copy())
        self.assertEqual(len(seen),1);self.assertEqual(np.dtype(seen[0][0]),np.dtype('float64'))
        self.assertTrue(result['fallback'][0]);self.assertEqual(result['refinement_accepts'][0],0)
        self.assertEqual(result['parameters'].dtype,np.float64)
    def test_wrong_precision_saved_guard_rejected(self):
        with self.assertRaises(AssertionError):verify_saved.guard_from_saved(np.ones((1,512),int),np.zeros((1,8),np.float32),np.ones((1,512)),CFG['lower'],CFG['upper'])
    def test_seed_contract(self):
        certificate={"purpose":"vector_baseline_challenge","status":"ISSUED","freshness_attestation":"ROOT_CONFIRMED_NOT_PREVIOUSLY_USED","parameter_seed":"1","noise_seed":"2"}
        self.assertEqual(data.seeds(certificate),[1,2])
        for key,value in (("purpose","vector_p1"),("noise_seed","1"),("parameter_seed",str(2**128)),("status","DRAFT")):
            with self.assertRaises(ValueError):data.seeds({**certificate,key:value})
    def test_changed_label_identity_rejected(self):
        labels=np.tile(CFG['nominal'],(4096,1)).astype(float)
        with self.assertRaises(AssertionError):verify_saved.label_identity(labels,[],CFG['lower'],CFG['upper'])
    def test_fast_classical_invalidates_speed_gate(self):
        metrics={n:{'mean_uT':1.,'p95_uT':2.,'rejections':0} for n in methods.METHODS}
        timings={n:{'host_to_host_seconds':[1.,1.,1.]} for n in methods.METHODS};timings['affine2_f32']['host_to_host_seconds']=[.6,.6,.6]
        setup={'original_p1_candidate_setup_seconds':10.,'method_setup_seconds':{n:.1 for n in methods.METHODS}}
        result=evaluation.decide(metrics,timings,setup)
        self.assertEqual(result['fastest_adequate_classical'],'affine2_f32');self.assertFalse(result['any_neural_continuation'])
    def test_failed_neural_zero_retained(self):
        metrics={n:{'mean_uT':1.,'p95_uT':2.,'rejections':0} for n in methods.METHODS};metrics['neural0']['mean_uT']=2.
        timings={n:{'host_to_host_seconds':[1.,1.,1.]} for n in methods.METHODS};timings['neural0']['host_to_host_seconds']=[.1,.1,.1]
        result=evaluation.decide(metrics,timings,{'original_p1_candidate_setup_seconds':10.,'method_setup_seconds':{n:.1 for n in methods.METHODS}})
        self.assertFalse(result['neural_routes']['neural0']['continuation_pass']);self.assertIn('neural0',result['neural_routes'])
