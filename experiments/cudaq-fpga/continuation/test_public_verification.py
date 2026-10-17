import json,tempfile,unittest
from pathlib import Path
import numpy as np
from verify_saved_evidence import verify_inventory,verify_integer,compare_quantum
class PublicContracts(unittest.TestCase):
    def test_inventory_rejects_corruption_and_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'x').write_text('x')
            for name in ['x','../outside']:
                (root/'SOURCE_MAP.json').write_text(json.dumps({'files':[{'public_relative_path':name,'public_sha256':'0'*64}]}))
                with self.assertRaises(ValueError):verify_inventory(root)
    def test_full_width_score_mismatch_rejected(self):
        rom=np.zeros((121,128),dtype=np.int16);inputs=np.full((1,128),32767,dtype=np.int16)
        score=128*32767**2
        self.assertEqual(verify_integer(inputs,np.array([0]),np.array([score],dtype=np.uint64),rom),1)
        with self.assertRaises(ValueError):verify_integer(inputs,np.array([0]),np.array([score & 0xffffffff],dtype=np.uint64),rom)
    def test_numerical_comparison_enforces_tolerance(self):
        cfg={'configurations':1,'gates':{'trace_atol':1e-6,'hermiticity_atol':1e-6,'minimum_eigenvalue':-1e-6,'purity_atol':1e-6,'probability_atol':1e-6,'density_atol':1e-6}}
        rho=np.zeros((1,4,64,4,4),dtype=np.complex128);rho[...,0,0]=.5;rho[...,1,1]=.5
        common={'detuning_mhz':np.array([0.]),'delays_us':np.arange(64.),'phases_rad':np.arange(4.)}
        cpu=common|{'density':rho,'probabilities':np.ones((1,4,64))}
        self.assertEqual(compare_quantum(cpu,cpu,cfg),(0.,0.))
        shifted=rho[..., [2,3,0,1],:][...,[2,3,0,1]]
        gpu=common|{'density':shifted,'probabilities':np.zeros((1,4,64))}
        with self.assertRaisesRegex(ValueError,'Probability tolerance'):compare_quantum(cpu,gpu,cfg)
if __name__=='__main__':unittest.main()
