import unittest
import numpy as np
from nv_model import config, probabilities, hamiltonian, RHO0, evolve, ZE, P0
from nv_stress import (nominal_nuisance, stress_probabilities, stress_density,
                       physical_model, dephase, profiled_scores, stress_counts)


class StressTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config()
        self.n = nominal_nuisance()

    def test_matched_reproduces_frozen_model(self):
        t = np.linspace(0,4,64)
        for frequency in [-.75,0.,.75]:
            a = stress_probabilities(frequency,t,self.cfg["phases_rad"],self.cfg["model"],self.n)
            b = probabilities(frequency,t,self.cfg["phases_rad"],self.cfg["model"])
            np.testing.assert_allclose(a,b,rtol=0,atol=1e-12)

    def test_fixed_pulse_duration_exposes_amplitude_error(self):
        self.n["rabi_scale"] = .9
        p = stress_probabilities(.24,np.linspace(0,4,64),self.cfg["phases_rad"],self.cfg["model"],self.n)
        adjusted = physical_model(self.cfg["model"],self.n)
        artificially_recalibrated = probabilities(.24,np.linspace(0,4,64),self.cfg["phases_rad"],adjusted)
        self.assertGreater(float(np.max(abs(p-artificially_recalibrated))),.01)

    def test_dephasing_commutes_with_free_evolution(self):
        self.n["free_dephasing_us"] = 7.
        h = hamiltonian(.57,self.cfg["model"])
        pulse = 1/(4*self.cfg["model"]["rabi_mhz"])
        prep = evolve(hamiltonian(.57,self.cfg["model"],np.pi/2,True),RHO0,pulse)
        exact = dephase(evolve(h,prep,4.),4.,7.)
        rho = prep.copy()
        dt = .0005
        def rhs(r):
            return -1j*(h@r-r@h)+(ZE@r@ZE-r)/(2*7.)
        for _ in range(8000):
            k1 = rhs(rho)
            k2 = rhs(rho+dt/2*k1)
            k3 = rhs(rho+dt/2*k2)
            k4 = rhs(rho+dt*k3)
            rho += dt/6*(k1+2*k2+2*k3+k4)
        error = float(np.max(abs(rho-exact)))
        print("Independent dephasing RK4 maximum density error:",error)
        self.assertLess(error,1e-7)

    def test_mismatch_physicality_and_scalar_vector_agreement(self):
        self.n.update(rabi_scale=.9,readout_phase_error_rad=.10472,
                      hyperfine_parallel_scale=1.1,hyperfine_transverse_scale=.9,
                      nuclear_frequency_scale=.98,free_dephasing_us=6.)
        t = [0.,.17,4.]
        p = stress_probabilities(-.63,t,self.cfg["phases_rad"],self.cfg["model"],self.n)
        for i,phase in enumerate(self.cfg["phases_rad"]):
            for j,delay in enumerate(t):
                r = stress_density(-.63,delay,phase,self.cfg["model"],self.n)
                np.testing.assert_allclose(r,r.conj().T,atol=1e-12)
                self.assertAlmostEqual(np.trace(r).real,1.,places=12)
                self.assertGreaterEqual(np.linalg.eigvalsh(r).min(),-1e-12)
                self.assertAlmostEqual(np.trace(P0@r).real,p[i,j],places=12)

    def test_profiled_objective_removes_gain_and_offsets(self):
        rng = np.random.default_rng(81726001)
        bank = rng.normal(size=(5,128))
        observed = 1.2*bank[2]+np.repeat([.13,-.24],64)
        scores = profiled_scores(observed,bank)
        self.assertEqual(int(np.argmin(scores)),2)
        self.assertLess(scores[2],1e-10)

    def test_noise_moments_under_drift(self):
        from nv_stress import optical_rates
        self.n.update(optical_gain=.8,optical_contrast_scale=.7,phase_gain_drift=.1,background_photons=.03)
        rng = np.random.default_rng(81726002)
        p = np.full((4,30000),.43)
        counts = stress_counts(p,100,self.n,rng)
        bright,dark,bg = optical_rates(self.n)
        mean = 100*(.43*bright+.57*dark+bg)
        variance = mean+100*.43*.57*(bright-dark)**2
        self.assertLess(float(np.max(abs(counts.mean(axis=1)-mean[:,0])/mean[:,0])),.015)
        self.assertLess(float(np.max(abs(counts.var(axis=1)-variance[:,0])/variance[:,0])),.04)


if __name__ == "__main__":
    unittest.main(verbosity=2)
