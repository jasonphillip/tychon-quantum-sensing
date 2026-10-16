"""Manufactured checks. Execute only through the root-approved qualification CLI."""
import unittest
import numpy as np
from .physics import CFG, Engine, AXES, FRAMES, validate_counts
from .independent import reference_transitions, manufactured_parameters

class ManufacturedChecks(unittest.TestCase):
    def test_geometry(self):
        np.testing.assert_allclose(AXES@AXES.T,np.eye(4)*4/3-np.ones((4,4))/3,atol=1e-15)
        np.testing.assert_allclose(FRAMES@FRAMES.transpose(0,2,1),np.broadcast_to(np.eye(3),(4,3,3)),atol=1e-15)
        np.testing.assert_allclose(np.linalg.det(FRAMES),1,atol=1e-15)

    def test_independent_hamiltonian(self):
        p = manufactured_parameters()
        np.testing.assert_allclose(Engine().transitions(p),
            reference_transitions(p,CFG["bias_uT"],CFG["gamma_MHz_per_uT"]),
            atol=CFG["fidelity_float64_MHz"],rtol=0)

    def test_zero_and_axial_units(self):
        p = np.array([CFG["nominal"]],dtype=float)
        p[0,:3] = -np.asarray(CFG["bias_uT"])
        np.testing.assert_allclose(Engine().transitions(p),2870.,rtol=0,atol=1e-10)
        p[0,:3] += 100*AXES[0]
        expected = np.array([2870.-100*CFG["gamma_MHz_per_uT"],
                             2870.+100*CFG["gamma_MHz_per_uT"]])
        np.testing.assert_allclose(Engine().transitions(p)[0,:2],expected,rtol=0,atol=1e-9)

    def test_analytic_derivative(self):
        e, p = Engine(), manufactured_parameters()
        _, jac = e.spectrum(p,True)
        for k, scale in enumerate(CFG["scales"]):
            step = scale*1e-4
            upper,lower = p.copy(),p.copy()
            upper[:,k] += step
            lower[:,k] -= step
            finite = (e.spectrum(upper)-e.spectrum(lower))/(2*step)
            np.testing.assert_allclose(jac[:,:,k],finite,
                atol=CFG["jacobian_atol"],rtol=CFG["jacobian_rtol"])

    def test_positive_rate_and_shape(self):
        values = Engine().spectrum(manufactured_parameters())
        self.assertEqual(values.shape,(5,512))
        self.assertTrue(np.isfinite(values).all() and (values>0).all())

    def test_counts_reject_invalid(self):
        for a in [np.zeros((2,511)),np.full((1,512),-1),np.full((1,512),np.nan)]:
            with self.assertRaises(ValueError):
                validate_counts(a)

    def test_numpy_batch_invariance(self):
        p, e = manufactured_parameters(), Engine()
        np.testing.assert_allclose(e.spectrum(p),np.concatenate([e.spectrum(r[None,:]) for r in p]),rtol=0,atol=1e-14)

    def test_poisson_exposure_contract(self):
        from unittest.mock import patch
        from .physics import poisson_counts
        class Recorder:
            def poisson(self,rate):
                self.rate=rate
                return np.zeros(rate.shape,dtype=np.int64)
        recorder=Recorder()
        p=manufactured_parameters()
        with patch("numpy.random.default_rng",return_value=recorder):
            result=poisson_counts(p,12345,100.)
        np.testing.assert_allclose(recorder.rate,100*Engine().spectrum(p),rtol=0,atol=0)
        self.assertEqual(result.dtype,np.dtype("int64"))
        for exposure in (0,-1,np.nan):
            with self.assertRaises(ValueError):
                poisson_counts(p,12345,exposure)

    def test_poisson_deviance_zero_and_empty_counts(self):
        from .baseline import deviance
        e=Engine()
        np.testing.assert_allclose(deviance(e,np.array([[0.,1.]]),np.ones((1,2)),1.),[2.],atol=1e-15)
        np.testing.assert_allclose(deviance(e,np.array([[1e6,2e6]]),np.array([[1.,2.]]),1e6),[0.],atol=0)

    def test_affine_inverse_local_limit(self):
        from .baseline import initialize
        p=np.array([CFG["nominal"]],dtype=float)
        p[0,:3]+=[.001,-.002,.003]
        e=Engine()
        fitted=initialize(e,e.spectrum(p)*CFG["photons_per_bin"],"affine")
        np.testing.assert_allclose(fitted[:,:3],p[:,:3],rtol=0,atol=1e-4)

    def test_observed_guard_and_bounds(self):
        from .baseline import observed_check
        p=np.array([CFG["nominal"]],dtype=float)
        e=Engine()
        counts=e.spectrum(p)*CFG["photons_per_bin"]
        accepted,_=observed_check(e,counts,p)
        self.assertTrue(accepted[0])
        p[0,0]=CFG["upper"][0]+1
        accepted,_=observed_check(e,counts,p)
        self.assertFalse(accepted[0])

    def test_global_sign_ambiguity_is_not_hidden(self):
        p=manufactured_parameters()
        reverse=p.copy()
        reverse[:,:3]=-p[:,:3]-2*np.asarray(CFG["bias_uT"])
        np.testing.assert_allclose(Engine().transitions(p),Engine().transitions(reverse),rtol=0,atol=1e-9)

    def test_invalid_prediction_is_rejected_without_eigensolver_crash(self):
        from .baseline import observed_check
        p=np.array([CFG["nominal"]],dtype=float)
        e=Engine()
        counts=e.spectrum(p)*CFG["photons_per_bin"]
        p[0,0]=np.nan
        accepted,_=observed_check(e,counts,p)
        self.assertFalse(accepted[0])
