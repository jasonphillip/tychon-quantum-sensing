"""Finite noise producer and diagnostic formulas. No tuning or data exclusion."""
import hashlib
import numpy as np
from experiments.vector_direct_screen.physics import CFG, Engine
from experiments.vector_direct_screen.independent import reference_transitions

EXPOSURE=2000000
SCALES=np.asarray(CFG["scales"],dtype=np.float64)
METHODS=(("lm","float64",1024),("affine","float32",4096),
         ("peaks","float64",1024),("calibrated","float64",1024))
A_LO=np.array([-10,-10,-10,2869.9,1.75,.04,.99,-.005],dtype=float)
A_HI=np.array([10,10,10,2870.1,2.25,.08,1.01,.005],dtype=float)


def validate_certificate(certificate):
    if certificate.get("purpose")!="vector_p0" or certificate.get("status")!="ISSUED":
        raise ValueError("Fresh root-issued P0 seed certificate required")
    values=[certificate.get("parameter_seed"),*(certificate.get("noise_seeds") or [])]
    if len(values)!=3 or any(not isinstance(v,str) or not v.isdecimal() for v in values):
        raise ValueError("One parameter seed and two decimal-string noise seeds required")
    numbers=[int(v) for v in values]
    if len(set(numbers))!=3 or any(v<0 or v>=2**128 for v in numbers):
        raise ValueError("Distinct unsigned128-bit seeds required")
    if certificate.get("freshness_attestation")!="ROOT_CONFIRMED_NOT_PREVIOUSLY_USED":
        raise ValueError("Root seed-custody attestation required")
    return numbers


def parameter_rows(seed):
    rng=np.random.Generator(np.random.PCG64(seed))
    return np.concatenate([rng.uniform(A_LO,A_HI,size=(32,8)),
        rng.uniform(np.asarray(CFG["lower"]),np.asarray(CFG["upper"]),size=(32,8))])


def poisson_draw(rates, seed, exposure=EXPOSURE, generator_factory=None):
    if exposure!=EXPOSURE or not np.isfinite(rates).all() or np.any(rates<=0):
        raise ValueError("Positive rates at the frozen photon exposure required")
    rng=(generator_factory(seed) if generator_factory else np.random.Generator(np.random.PCG64(seed)))
    result=np.asarray(rng.poisson(rates*exposure))
    if result.shape!=rates.shape or result.dtype.kind not in "iu" or np.any(result<0):
        raise ValueError("Poisson implementation returned invalid integer counts")
    return result.astype(np.int64,copy=False)


def independent_rates(parameters):
    centers=reference_transitions(parameters,CFG["bias_uT"],CFG["gamma_MHz_per_uT"])
    frequencies=np.linspace(CFG["frequency_start_MHz"],CFG["frequency_stop_MHz"],512)
    output=[]
    for row,lines in zip(parameters,centers):
        profile=np.zeros(512)
        for center in lines:
            profile+=1/(1+(2*(frequencies-center)/row[4])**2)
        output.append(row[6]*(1-row[5]*profile/8)+row[7]*(frequencies-2870)/65)
    return np.asarray(output)


def row_sha(row):
    return hashlib.sha256(np.asarray(row,dtype="<f8").tobytes()).hexdigest()


def generate(certificate):
    parameter_seed,*noise_seeds=validate_certificate(certificate)
    latent=parameter_rows(parameter_seed)
    if len({row_sha(row) for row in latent})!=64:raise ValueError("Duplicate latent rows")
    parameters=np.repeat(latent,2,axis=0)
    rates,jacobian=Engine().spectrum(parameters,True)
    independent=independent_rates(parameters)
    if not np.allclose(rates,independent,rtol=0,atol=1e-11):
        raise AssertionError("Independent Hamiltonian/Lorentzian mean mismatch")
    counts=np.empty((128,512),dtype=np.int64)
    for replicate,seed in enumerate(noise_seeds):
        counts[replicate::2]=poisson_draw(rates[replicate::2],seed)
    records=[]
    for i,row in enumerate(parameters):
        latent_i=i//2;regime="A" if latent_i<32 else "B";identifier=f"{regime}{latent_i%32:02d}"
        records.append({"row":i,"record_id":identifier+f"-r{i%2}","latent_id":identifier,
            "latent_index":latent_i,"regime":regime,"replicate":i%2,"parameter_sha256":row_sha(row)})
    return {"latent_parameters":latent,"parameters":parameters,"counts":counts,
        "expected_counts":rates*EXPOSURE,"true_rates":rates,"true_jacobian":jacobian,
        "independent_true_rates":independent,"latent_index":np.repeat(np.arange(64),2),
        "replicate":np.tile(np.arange(2),64)},records


def information(rates, jacobian, observed_counts=None):
    """Full8-parameter information; scale-normalized rank and nuisance-marginal covariance.

    Count-weighted information is the observed Gauss-Newton term, not the full
    observed likelihood Hessian. Only expected information gives a local CRLB.
    Rank-deficient covariance remains NaN instead of a misleading pseudoinverse.
    """
    if np.any(rates<=0) or not np.isfinite(rates).all():raise ValueError("Invalid rates")
    weight=np.sqrt(EXPOSURE/rates) if observed_counts is None else np.sqrt(observed_counts)/rates
    weighted=jacobian*SCALES[None,None,:]*weight[:,:,None]
    fisher=np.einsum("nfi,nfj->nij",weighted,weighted)
    _,singular,vt=np.linalg.svd(weighted,full_matrices=False)
    cutoff=max(weighted.shape[1:])*np.finfo(float).eps*singular[:,0]
    rank=(singular>cutoff[:,None]).sum(axis=1)
    condition=np.full(len(rates),np.inf);covariance=np.full((len(rates),3,3),np.nan)
    for i in range(len(rates)):
        if rank[i]==8:
            condition[i]=singular[i,0]/singular[i,-1]
            inverse=(vt[i].T/(singular[i]**2))@vt[i]
            physical=inverse*SCALES[:,None]*SCALES[None,:]
            covariance[i]=physical[:3,:3]
    return {"fisher_scaled":fisher,"singular_values":singular,"rank":rank,
            "weighted_jacobian_condition":condition,"field_covariance_uT2":covariance}


def errors(predictions, parameters):
    delta=predictions[:,:3]-parameters[:,:3]
    norm=np.sqrt(np.sum(delta*delta,axis=1))
    return delta,norm


def summarize(norm, accepted, fallback, regimes):
    def group(mask):
        a=norm[mask]
        return {"n":int(mask.sum()),"mean_uT":float(a.mean()),"rmse_uT":float(np.sqrt(np.mean(a*a))),
            "p50_uT":float(np.quantile(a,.5)),"p90_uT":float(np.quantile(a,.9)),
            "p99_uT":float(np.quantile(a,.99)),"max_uT":float(a.max()),
            "accepted":int(accepted[mask].sum()),"fallback":int(fallback[mask].sum())}
    return {"all":group(np.ones(len(norm),dtype=bool)),"A":group(regimes==0),"B":group(regimes==1)}
