"""Fresh calibration stress helpers. The frozen v1 inference core is unchanged."""
import numpy as np
from nv_model import hamiltonian, unitary, evolve, RHO0, P0


NUISANCE_KEYS = ("optical_gain", "optical_contrast_scale", "phase_gain_drift",
                 "background_photons", "rabi_scale", "readout_phase_error_rad",
                 "hyperfine_parallel_scale", "hyperfine_transverse_scale",
                 "nuclear_frequency_scale", "free_dephasing_us")


def nominal_nuisance():
    return dict(optical_gain=1., optical_contrast_scale=1., phase_gain_drift=0.,
                background_photons=.02, rabi_scale=1., readout_phase_error_rad=0.,
                hyperfine_parallel_scale=1., hyperfine_transverse_scale=1.,
                nuclear_frequency_scale=1., free_dephasing_us=np.inf)


def choose_nuisance(scenario, values):
    out = nominal_nuisance()
    if scenario in ("optical_drift", "combined_mismatch"):
        for key in NUISANCE_KEYS[:4]:
            out[key] = values[key]
    if scenario in ("control_drift", "combined_mismatch"):
        for key in NUISANCE_KEYS[4:6]:
            out[key] = values[key]
    if scenario == "combined_mismatch":
        for key in NUISANCE_KEYS[6:]:
            out[key] = values[key]
    if scenario not in ("matched","optical_drift","control_drift","combined_mismatch"):
        raise ValueError("unknown scenario")
    return out


def physical_model(nominal, nuisance):
    m = nominal.copy()
    for field, scale in [("rabi_mhz","rabi_scale"),
                         ("hyperfine_parallel_mhz","hyperfine_parallel_scale"),
                         ("hyperfine_transverse_mhz","hyperfine_transverse_scale"),
                         ("nuclear_frequency_mhz","nuclear_frequency_scale")]:
        m[field] *= nuisance[scale]
    return m


def dephase(rho, delay_us, coherence_us):
    if coherence_us <= 0 or np.isnan(coherence_us):
        raise ValueError("coherence must be positive or infinity")
    out = rho.copy()
    factor = np.exp(-np.asarray(delay_us)/coherence_us)
    if out.ndim == 3:
        out[:,:2,2:] *= factor[:,None,None]
        out[:,2:,:2] *= factor[:,None,None]
    else:
        out[:2,2:] *= factor
        out[2:,:2] *= factor
    return out


def stress_density(detuning, delay, phase, nominal, nuisance):
    m = physical_model(nominal,nuisance)
    # The pulse length is programmed from the nominal calibration, not its drifted value.
    pulse = 1/(4*nominal["rabi_mhz"])
    rho = evolve(hamiltonian(detuning,m,np.pi/2,True),RHO0,pulse)
    rho = evolve(hamiltonian(detuning,m),rho,delay)
    rho = dephase(rho,delay,nuisance["free_dephasing_us"])
    return evolve(hamiltonian(detuning,m,phase-np.pi/2+nuisance["readout_phase_error_rad"],True),rho,pulse)


def stress_probabilities(detuning, delays, phases, nominal, nuisance):
    delays = np.asarray(delays,dtype=float)
    if np.any(delays < 0) or not np.all(np.isfinite(delays)):
        raise ValueError("invalid delays")
    m = physical_model(nominal,nuisance)
    pulse = 1/(4*nominal["rabi_mhz"])
    prep = evolve(hamiltonian(detuning,m,np.pi/2,True),RHO0,pulse)
    e,v = np.linalg.eigh(hamiltonian(detuning,m))
    u = np.einsum("ij,tj,kj->tik",v,np.exp(-1j*delays[:,None]*e),v.conj())
    r = dephase(u@prep@u.conj().transpose(0,2,1),delays,nuisance["free_dephasing_us"])
    out = []
    for phase in phases:
        readout = unitary(hamiltonian(detuning,m,phase-np.pi/2+nuisance["readout_phase_error_rad"],True),pulse)
        observable = readout.conj().T@P0@readout
        out.append(np.einsum("ij,tji->t",observable,r).real)
    p = np.asarray(out)
    if not np.all(np.isfinite(p)) or p.min() < -1e-10 or p.max() > 1+1e-10:
        raise ArithmeticError("invalid probability")
    return p


def optical_rates(nuisance):
    gain = nuisance["optical_gain"]*(1+np.linspace(-1,1,4)*nuisance["phase_gain_drift"])
    dark = gain*.10
    bright = gain*(.10+.14*nuisance["optical_contrast_scale"])
    background = np.full(4,nuisance["background_photons"])
    if np.any(gain <= 0) or np.any(bright < dark) or np.any(background < 0):
        raise ValueError("invalid detection rates")
    return bright[:,None],dark[:,None],background[:,None]


def stress_counts(p, repetitions, nuisance, rng):
    if repetitions <= 0:
        raise ValueError("positive repetitions required")
    bright,dark,background = optical_rates(nuisance)
    k = rng.binomial(repetitions,np.clip(p,0,1))
    rate = k*bright+(repetitions-k)*dark+repetitions*background
    return rng.poisson(rate).astype(np.int32)


def centered(values):
    a = np.asarray(values).reshape((-1,2,64))
    return (a-a.mean(axis=2,keepdims=True)).reshape((-1,128))


def profiled_scores(feature,templates,gain_bounds=(.1,2.)):
    """Profile a shared gain and separate quadrature offsets from observations."""
    x = centered(feature)[0]
    m = centered(templates)
    norm = np.sum(m*m,axis=1)
    if np.any(norm <= 1e-14):
        raise ValueError("degenerate template")
    dot = m@x
    gain = np.clip(dot/norm,*gain_bounds)
    return np.maximum(0.,np.sum(x*x)-2*gain*dot+gain*gain*norm)
