import hashlib
import json
import tempfile
import unittest
import shutil
import subprocess
from pathlib import Path
import numpy as np
import run_stress as r


class StressTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((r.ROOT/"config.json").read_text())
        self.t=np.arange(64)*0.025

    def test_frozen_model_and_core(self):
        self.assertEqual(r.sha(r.MODEL),self.c["source_model_sha256"])
        self.assertEqual(r.sha(r.CORE),r.CORE_SHA)

    def test_no_relaxation_limit(self):
        a=r.alpha_relax(self.t,1,np.inf,0.3,2,1,4)
        np.testing.assert_allclose(a,r.alpha_constant(self.t,2.3,1,4))

    def test_immediate_decay_is_ground(self):
        a=r.alpha_relax(self.t,1,0,0.3,2,1,4)
        np.testing.assert_allclose(a,r.alpha_relax(self.t,0,np.inf,0.3,2,1,4),atol=1e-14)

    def test_amplitude_continuity_at_jump(self):
        event=0.37
        a=r.alpha_relax(np.array([event-1e-10,event,event+1e-10]),1,event,0.3,2,1,4)
        self.assertLess(np.max(abs(np.diff(a))),1e-8)

    def test_independent_piecewise_integrator(self):
        result=r.physics_checks(self.c)
        self.assertTrue(result["passed"])

    def test_affine_identification_without_hidden_parameters(self):
        nominal=r.nominal_templates(self.c)
        m=np.array([[0.8,0.4],[-0.3,1.2]])
        offset=np.array([0.17,-0.24])
        means=nominal@m+offset
        x=np.repeat(means.reshape(2,128),32,axis=0)
        y=np.repeat([0,1],32)
        fit=r.fit_affine(x,y,self.c)
        self.assertTrue(fit["valid"])
        np.testing.assert_allclose(r.apply_affine(x,fit),np.repeat(nominal.reshape(2,128),32,axis=0),atol=1e-13)

    def test_singular_calibration_is_rejected(self):
        x=np.zeros((64,128));y=np.repeat([0,1],32)
        fit=r.fit_affine(x,y,self.c)
        self.assertFalse(fit["valid"])
        with self.assertRaises(ValueError):
            r.apply_affine(x,fit)

    def test_receiver_seed_reproducibility_and_new_noise(self):
        p=r.group_parameters(np.random.default_rng(71),self.c["scenarios"][0],self.c)
        a=r.receiver_records(np.random.default_rng(72),p,self.c,3)
        b=r.receiver_records(np.random.default_rng(72),p,self.c,3)
        d=r.receiver_records(np.random.default_rng(73),p,self.c,3)
        np.testing.assert_array_equal(a[0],b[0])
        self.assertFalse(np.array_equal(a[0],d[0]))

    def test_quantization_and_fixed_weights(self):
        model=json.loads(r.MODEL.read_text())
        x=np.zeros((2,128));x[0,0]=100;x[1,1]=-100
        q,s,clipped=r.integer_score(x,model)
        self.assertEqual(clipped,2)
        self.assertEqual(int(s[0]),214072292-16384*32767)
        self.assertEqual(int(s[1]),214072292+2811*(-32768))
        with self.assertRaises(ValueError):
            r.integer_score(np.full((1,128),np.nan),model)

    def test_little_endian_export_roundtrip(self):
        model=json.loads(r.MODEL.read_text())
        x=np.zeros((1,128),dtype=np.int16);x[0,:2]=[-32768,32767]
        s=x.astype(np.int64)@np.array(model["weight_int16"],dtype=np.int64)+model["bias_int64"]
        with tempfile.TemporaryDirectory() as path:
            manifest=r.write_pack(Path(path),x,s,[1],[{"mode":"raw"}],self.c,model)
            data=(Path(path)/"board_replay/inputs_i16.bin").read_bytes()
            self.assertEqual(data[:4],b"\x00\x80\xff\x7f")
            self.assertEqual(manifest["records"],1)

    def test_portable_reference_rejects_bad_packs(self):
        model=json.loads(r.MODEL.read_text())
        x=np.zeros((2,128),dtype=np.int16)
        x[0]=32767;x[1]=-32768
        scores=x.astype(np.int64)@np.array(model["weight_int16"],dtype=np.int64)+model["bias_int64"]
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);exe=p/"reference"
            subprocess.run([shutil.which("c++"),"-std=c++11",str(r.ROOT/"replay_reference.cpp"),"-o",str(exe)],check=True,capture_output=True)
            inputs=p/"inputs.bin";expected=p/"expected.bin"
            x.astype("<i2").tofile(inputs);scores.astype("<i8").tofile(expected)
            invoke=lambda:subprocess.run([str(exe),str(inputs),str(expected)],capture_output=True).returncode
            self.assertEqual(invoke(),0)
            expected.write_bytes(expected.read_bytes()+b"\0")
            self.assertEqual(invoke(),4)
            scores.astype("<i8").tofile(expected)
            wrong=scores.copy();wrong[0]+=1;wrong.astype("<i8").tofile(expected)
            self.assertEqual(invoke(),1)
            scores.astype("<i8").tofile(expected)
            inputs.write_bytes(inputs.read_bytes()[:-1])
            self.assertEqual(invoke(),4)


if __name__=="__main__":
    unittest.main()
