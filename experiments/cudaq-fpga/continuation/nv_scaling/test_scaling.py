import hashlib
import json
import unittest
import numpy as np
from scaling import ROOT, arrays, cpu_density, probabilities, physical_metrics, physical_pass, detector_and_pack, unitary_batch, ROM_SHA
from nv_model import hamiltonian, sequence_density, rk4_density, probabilities as scalar_probabilities, RHO0, evolve


class ScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=json.loads((ROOT/'protocol_dev.json').read_text())
        cls.ds,cls.delays,cls.phases=arrays(cls.cfg)
        cls.rho=cpu_density(cls.cfg,cls.ds)

    def test_all_outputs_match_existing_specialized_scalar(self):
        ref=np.stack([scalar_probabilities(d,self.delays,self.phases,self.cfg['model']) for d in self.ds])
        np.testing.assert_allclose(probabilities(self.rho),ref,atol=4e-14,rtol=0)

    def test_selected_density_independent_rk4(self):
        for config_id,phase_id,delay_id in [(0,0,0),(0,1,63),(1,2,21),(1,3,63)]:
            ref=sequence_density(self.ds[config_id],self.delays[delay_id],self.phases[phase_id],self.cfg['model'],solver=rk4_density)
            np.testing.assert_allclose(self.rho[config_id,phase_id,delay_id],ref,atol=2e-10,rtol=0)

    def test_physical_invariants_every_density(self):
        self.assertEqual(self.rho.shape,(2,4,64,4,4))
        self.assertTrue(physical_pass(physical_metrics(self.rho),self.cfg['gates']))

    def test_normalized_segment_scaling_and_zero_duration(self):
        h=hamiltonian(.25,self.cfg['model'],.7,True)
        for duration in [0.,1/(4*self.cfg['model']['rabi_mhz']),4.]:
            normalized=evolve(h*duration,RHO0,1.)
            np.testing.assert_allclose(normalized,evolve(h,RHO0,duration),atol=3e-14,rtol=0)
        np.testing.assert_allclose(unitary_batch(np.array([h*0]),1),np.eye(4)[None],atol=1e-14)

    def test_zero_coupling_nuclear_frequency_has_no_electron_effect(self):
        cfg=self.cfg|{'model':self.cfg['model']|{'hyperfine_parallel_mhz':0.,'hyperfine_transverse_mhz':0.}}
        changed=cfg|{'model':cfg['model']|{'nuclear_frequency_mhz':2.1}}
        np.testing.assert_allclose(probabilities(cpu_density(cfg,self.ds)),probabilities(cpu_density(changed,self.ds)),atol=3e-14,rtol=0)

    def test_detector_frozen_rom_format_and_determinism(self):
        a=detector_and_pack(self.cfg,probabilities(self.rho))
        b=detector_and_pack(self.cfg,probabilities(self.rho))
        for i in range(4): np.testing.assert_array_equal(a[i],b[i])
        self.assertEqual(a[0].shape,(16,128)); self.assertEqual(a[1].dtype,np.dtype('<u2'))
        self.assertEqual(a[2].dtype,np.dtype('<u8'))
        self.assertEqual(hashlib.sha256((ROOT/'frozen/templates_i16le.bin').read_bytes()).hexdigest(),ROM_SHA)

    def test_seed_separation(self):
        final=json.loads((ROOT/'protocol_final.json').read_text())
        prior={76641017,76641018,76641019,928410171,928410172,928410173,928410174,928410175}
        fresh={self.cfg['parameter_seed'],self.cfg['noise_seed'],final['parameter_seed'],final['noise_seed']}
        self.assertEqual(len(fresh),4); self.assertFalse(fresh&prior)

    def test_physical_gate_rejects_corruption(self):
        bad=self.rho.copy(); bad[0,0,0,0,0]+=.01
        self.assertFalse(physical_pass(physical_metrics(bad),self.cfg['gates']))


if __name__=='__main__': unittest.main()
