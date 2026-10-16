"""Authored fixtures only; no population or historical measured/synthetic data."""
import unittest
import numpy as np
from experiments.vector_direct_screen.physics import CFG, Engine
from .comparator import TiedLines, fit_lines, recover_field


class Manufactured(unittest.TestCase):
    def setUp(self):
        self.e = Engine("torch","cpu","float64")

    def test_parameter_matching_and_line_separation(self):
        e = self.e
        p = e.array([CFG["nominal"]])
        model = TiedLines(e)
        line = model.from_physical(p)
        self.assertEqual(tuple(line.shape),(1,12))
        np.testing.assert_allclose(e.numpy(model.spectrum(line)),e.numpy(e.spectrum(p)),
                                   atol=1e-12,rtol=0)

    def test_line_jacobian(self):
        e = self.e
        model = TiedLines(e)
        p = model.from_physical(e.array([CFG["nominal"]]))
        _,jac = model.spectrum(p,True)
        for k in range(12):
            step = float(model.scale[k])*1e-4
            a,b = p.clone(),p.clone()
            a[:,k]+=step
            b[:,k]-=step
            finite = (model.spectrum(a)-model.spectrum(b))/(2*step)
            np.testing.assert_allclose(e.numpy(jac[:,:,k]),e.numpy(finite),atol=2e-7,rtol=2e-4)

    def test_unknown_D_recovery_uses_nominal_start(self):
        # The API uses prior-defined slots; it never guesses an arbitrary oracle order.
        e = self.e
        model = TiedLines(e)
        p = e.array([CFG["nominal"]])
        for d in (-.3,.3):
            truth=p.clone()
            truth[0,:4] += e.array([3.,-5.,4.,d])
            lines=model.from_physical(truth)
            precision=e.xp.eye(8,dtype=e.real_dtype)[None,:,:]
            fitted=recover_field(e,lines,precision,p)
            np.testing.assert_allclose(e.numpy(fitted["parameters"][:,:4]),
                e.numpy(truth[:,:4]),atol=.002,rtol=0)

    def test_noiseless_line_fit_without_truth_initialization(self):
        e = self.e
        initial=e.array([CFG["nominal"]])
        truth=initial.clone()
        truth[0,:4]+=e.array([2.,-3.,4.,.2])
        counts=e.spectrum(truth)*CFG["photons_per_bin"]
        fitted=fit_lines(e,counts,initial)
        self.assertTrue(bool(fitted["valid"].all()))
        np.testing.assert_allclose(e.numpy(fitted["parameters"][:,4:]+2870.),
            e.numpy(e.transitions(truth)),atol=.003,rtol=0)

    def test_known_bias_excludes_global_sign_partner(self):
        e=self.e
        p=e.array([CFG["nominal"]])
        reversed_field=-p[:,:3]-2*e.bias
        self.assertFalse(bool(((reversed_field>=e.lower[:3]) &
                              (reversed_field<=e.upper[:3])).all()))


    def test_prior_corner_envelopes_and_identity(self):
        from itertools import product
        e=self.e
        model=TiedLines(e)
        corners=[]
        for sides in product((0,1),repeat=4):
            row=list(CFG["nominal"])
            for k,side in enumerate(sides):
                row[k]=(CFG["lower"] if side==0 else CFG["upper"])[k]
            corners.append(row)
        centers=e.transitions(e.array(corners))-2870.
        self.assertTrue(bool((e.xp.abs(centers-model.nominal)<=model.envelope+1e-9).all()))
        expected=model.order[None,:].expand(len(corners),-1)
        self.assertTrue(bool((e.xp.argsort(centers,dim=1)==expected).all()))

    def test_invalid_precision_and_failed_fit_rows_survive_fallback(self):
        from unittest.mock import patch
        from . import comparator as c
        e=self.e
        x=e.xp
        n=3
        start=e.array([CFG["nominal"]]*n)
        counts=e.spectrum(start)*CFG["photons_per_bin"]
        counts[:,0]+=x.arange(n,dtype=e.real_dtype)
        captured=[]
        original_fit=c.fit_lines
        original_solve=x.linalg.solve_ex
        def failed_line_solve(engine,normal,rhs,damping):
            return x.zeros_like(rhs),x.tensor([True,False,True])
        def invalid_precision_solve(matrix,rhs,**kwargs):
            answer,info=original_solve(matrix,rhs,**kwargs)
            answer=answer.clone()
            answer[2]=float("nan")
            return answer,info
        def record_fit(*args):
            result=original_fit(*args)
            captured.append(result)
            return result
        recovered=start.clone()
        recovered[:,0]=e.array([0.,1.,2.])
        inverse=dict(parameters=recovered,valid=x.ones(n,dtype=x.bool),
                     converged=x.ones(n,dtype=x.bool))
        repair=start[:2].clone()
        repair[:,0]=e.array([11.,12.])
        repaired=dict(parameters=repair,accepted=x.tensor([True,False]),
                      reduced_deviance=e.array([.5,3.]))
        with patch.object(c,"_solve",side_effect=failed_line_solve), \
             patch.object(x.linalg,"solve_ex",side_effect=invalid_precision_solve), \
             patch.object(c,"fit_lines",side_effect=record_fit), \
             patch.object(c,"recover_field",return_value=inverse), \
             patch.object(c,"observed_check",return_value=(x.ones(n,dtype=x.bool),e.array([0.,0.,0.]))), \
             patch.object(c,"full_fallback",return_value=repaired) as fallback:
            result=c.policy_device(e,counts,chunk_size=1024)
        np.testing.assert_array_equal(e.numpy(captured[0]["valid"]),[True,False,False])
        np.testing.assert_allclose(e.numpy(captured[0]["precision"][2]),np.eye(8),atol=0,rtol=0)
        self.assertEqual(fallback.call_count,1)
        np.testing.assert_array_equal(e.numpy(fallback.call_args.args[1]),e.numpy(counts[1:]))
        np.testing.assert_array_equal(e.numpy(result["parameters"][:,0]),[0.,11.,12.])
        np.testing.assert_array_equal(e.numpy(result["accepted"]),[True,True,False])
        np.testing.assert_array_equal(e.numpy(result["fallback"]),[False,True,True])
        np.testing.assert_array_equal(e.numpy(result["line_valid"]),[True,False,False])
        self.assertEqual(len(result["parameters"]),n)

    def test_chunk_choice_is_explicit_and_does_not_mutate_frozen_config(self):
        from .comparator import policy_device
        before=CFG["chunk_size"]
        with self.assertRaises(ValueError):
            policy_device(self.e,self.e.array(np.zeros((1,512))),chunk_size=256)
        self.assertEqual(CFG["chunk_size"],before)
