"""Prepared numerical tests; execution awaits the shared accounting gate."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments/nv_hybrid_screen"))
from physics import mean_jac,Point,forward,FACTOR
from estimators import Estimator
class HybridPhysicsTests(unittest.TestCase):
    def test_analytic_jacobian(self):
        p=np.array([43.,2871.1,5.2,.014,1.01,.012]);_,jac=mean_jac(p)
        steps=[1e-3,1e-4,1e-4,1e-6,1e-5,1e-5]
        for j,h in enumerate(steps):
            plus=p.copy();minus=p.copy();plus[j]+=h;minus[j]-=h
            numerical=(mean_jac(plus)[0]-mean_jac(minus)[0])/(2*h)
            np.testing.assert_allclose(jac[:,j],numerical,rtol=1e-5,atol=1e-8)
    def test_nominal_source_parity(self):
        for B,T,width in ((25.,293.15,5.),(65.,300.,6.)):
            expected,_=forward(Point(field_uT=B,bias_uT=250,temperature_K=T,width_mhz=width,slope=.01),"fixed_amplitude",FACTOR)
            actual,_=mean_jac([B,2871-.0742*(T-300),width,.015,1.,.01])
            np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-11)
class FallbackFairnessTests(unittest.TestCase):
    @staticmethod
    def rejected_fit():
        return {"parameters":np.array([30.,2871.,5.,.015,1.,0.]),"score":3.,
                "success":True,"nfev":7,"boundary":False}

    def test_multistart_does_not_repeat_completed_search(self):
        starts=[object() for _ in range(6)]
        model=Estimator("analytic_multistart")
        with patch("estimators.fixed_starts",return_value=starts) as fixed, \
             patch("estimators.refine",side_effect=lambda y,p:self.rejected_fit()) as refine:
            result=model(np.ones(100))
        self.assertEqual([call.args[1] for call in refine.call_args_list],starts)
        fixed.assert_called_once()
        self.assertEqual(result["nfev"],42)
        self.assertFalse(result["fallback"])
        self.assertFalse(result["accepted"]);self.assertTrue(result["failed"])
        self.assertEqual(result["estimate"],45.)

    def test_other_initializers_use_one_full_domain_fallback(self):
        for method,count in (("hybrid",1),("coarse_grid",2),("lookup",2)):
            with self.subTest(method=method):
                initial=[object() for _ in range(count)];fallback=[object() for _ in range(6)]
                model=Estimator.__new__(Estimator);model.method=method
                with patch.object(model,"neural_start",return_value=initial[0]), \
                     patch.object(model,"grid_starts",return_value=initial), \
                     patch("estimators.fixed_starts",return_value=fallback) as fixed, \
                     patch("estimators.refine",side_effect=lambda y,p:self.rejected_fit()) as refine:
                    result=model(np.ones(100))
                self.assertEqual([call.args[1] for call in refine.call_args_list],initial+fallback)
                fixed.assert_called_once()
                self.assertEqual(result["nfev"],7*(count+6))
                self.assertTrue(result["fallback"]);self.assertTrue(result["failed"])
                self.assertFalse(result["accepted"]);self.assertEqual(result["estimate"],45.)

if __name__=="__main__":unittest.main()
