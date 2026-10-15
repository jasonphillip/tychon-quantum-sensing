"""Prepared numerical tests; execution awaits the shared accounting gate."""
import sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments/nv_hybrid_screen"))
from physics import mean_jac,Point,forward,FACTOR
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
if __name__=="__main__":unittest.main()
