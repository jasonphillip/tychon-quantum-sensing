"""Focused manufactured tests; execute only after root authorizes the registered job."""
import sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments/scalar_bias_design"))
from fit import mean,fit_one,FACTOR,FREQ
from generator import trajectory_at,streams,LOW_SEED,HIGH_SEED
from budget import cap_check
from metrics import compute
sys.path.insert(0,str(ROOT/"experiments/scalar_information_limit"))
from forward import Point,forward

class BiasDesignTests(unittest.TestCase):
    def test_axis_mixture_matches_unchanged_renderer(self):
        for field,bias,temp,width in ((25,0,293.15,5),(65,250,306.,7)):
            point=Point(field_uT=field,bias_uT=bias,width_mhz=width,temperature_K=temp)
            reference,_=forward(point,"fixed_amplitude",FACTOR)
            parameters=[field,2871-.0742*(temp-300),width,.015,1.,.02]
            np.testing.assert_allclose(mean(parameters,FREQ,bias),reference,rtol=0,atol=1e-11)

    def test_fit_nominal_noiseless_and_nonfinite_fallback(self):
        observed=mean([45,2871.50827,5,.015,1,.02],FREQ,250)
        result=fit_one(observed,FREQ,250)
        self.assertFalse(result["failed"]);self.assertAlmostEqual(result["estimate_uT"],45,places=5)
        self.assertEqual(len(result["starts"]),6)
        bad=fit_one(np.full(100,np.nan),FREQ,0)
        self.assertTrue(bad["failed"]);self.assertEqual(bad["estimate_uT"],45)

    def test_seed_namespaces_and_zero_index(self):
        draws,_=streams(123,3,set())
        values=[x for row in draws for x in row]
        self.assertEqual(len(set(values)),9)
        self.assertTrue(all(LOW_SEED<=x<HIGH_SEED for x in values))
        self.assertEqual(trajectory_at(0,LOW_SEED),(293.15,1.))

    def test_publication_reserve(self):
        zero={"cpu_seconds":0,"wall_seconds":0}
        with self.assertRaises(ValueError):
            cap_check({"cpu_seconds":2490,"wall_seconds":0},zero,zero,100)
        cap_check({"cpu_seconds":2490,"wall_seconds":0},zero,zero,100,publication=True)

    def test_paired_gate_and_failed_calibration_fallback(self):
        ids=[];fields=[];cells=[];truth_values=[];predictions=[];failures=[]
        for i,y in enumerate((20.,30.,60.,70.)):
            for cell in ("realistic_anchor","wide_lines","low_snr"):
                for bias in (0,250):
                    ids.append(f"field{i:04d}:{cell}:bias{bias}")
                    fields.append(i);cells.append(cell);truth_values.append(y)
                    predictions.append(45. if bias==0 else y);failures.append(False)
        pred={"row_ids":np.array(ids),"estimate_uT":np.array(predictions),
            "failed":np.array(failures),"boundary":np.zeros(24,bool),"elapsed_seconds":np.ones(24)*.1}
        truth={"row_id":np.array(ids),"field_index":np.array(fields),"cell":np.array(cells),
            "field_uT":np.array(truth_values),"temperature_K":np.ones(24)*293.15}
        indices=np.tile(np.arange(4),(5000,1))
        self.assertTrue(compute(pred,truth,indices)["gate"]["pass"])
        pred["failed"][1]=True;pred["estimate_uT"][1]=45.
        cell=compute(pred,truth,indices)["cells"]["realistic_anchor"]
        self.assertAlmostEqual(cell["calibration_shift_uT"]["5"]["mae_uT"],10.)
        self.assertAlmostEqual(cell["calibration_shift_uT"]["-5"]["mae_uT"],10.)
        for key,replacement in (("failed",np.zeros(24,float)),("elapsed_seconds",np.full(24,-1.))):
            bad=dict(pred);bad[key]=replacement
            with self.assertRaises(ValueError):compute(bad,truth,indices)
        with self.assertRaises(ValueError):compute(pred,truth,indices.astype(float))

if __name__=="__main__":unittest.main()
