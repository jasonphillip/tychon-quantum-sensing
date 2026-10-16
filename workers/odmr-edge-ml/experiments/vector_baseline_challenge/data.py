"""One fresh full-B population; no P1 case or training access."""
import hashlib
import numpy as np
from experiments.vector_direct_screen.physics import CFG,Engine
from experiments.vector_noise_qualification.core import poisson_draw,independent_rates
N=4096

def seeds(certificate):
    if certificate.get("purpose")!="vector_baseline_challenge" or certificate.get("status")!="ISSUED" or certificate.get("freshness_attestation")!="ROOT_CONFIRMED_NOT_PREVIOUSLY_USED":raise ValueError("Fresh root custody required")
    values=[certificate.get(k) for k in ("parameter_seed","noise_seed")]
    if any(not isinstance(v,str) or not v.isdecimal() or not 0<=int(v)<2**128 for v in values):raise ValueError("Two unsigned128-bit streams required")
    if int(values[0])==int(values[1]):raise ValueError("Streams must differ")
    return [int(v) for v in values]

def generate(certificate):
    ps,ns=seeds(certificate)
    parameters=np.random.Generator(np.random.PCG64(ps)).uniform(CFG["lower"],CFG["upper"],size=(N,8))
    identities=[hashlib.sha256(row.astype("<f8").tobytes()).hexdigest() for row in parameters]
    if len(set(identities))!=N:raise ValueError("Duplicate fresh latent")
    e=Engine();rates=np.concatenate([e.spectrum(parameters[i:i+256]) for i in range(0,N,256)])
    indices=np.linspace(0,N-1,32,dtype=int);reference=independent_rates(parameters[indices])
    if not np.allclose(rates[indices],reference,rtol=0,atol=1e-11):raise AssertionError("Independent means disagree")
    return dict(parameters=parameters,counts=poisson_draw(rates,ns),mean_check_indices=indices,
                rates_at_checks=rates[indices],independent_rates=reference),identities
