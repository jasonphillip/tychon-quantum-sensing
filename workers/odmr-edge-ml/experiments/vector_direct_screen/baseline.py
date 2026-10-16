"""Batched classical policies with a common observed-data guard and fallback."""
from __future__ import annotations
import numpy as np
from .physics import CFG, Engine, validate_counts

def deviance(engine, counts, rates, exposure):
    """Poisson deviance with a stable near-equality series, not a new noise law."""
    mu = engine.clamp(rates * exposure, 1e-20)
    delta = (counts-mu)/mu
    # Series error at |delta|<.01 is below float32 rounding at this exposure.
    series = mu*delta*delta*(.5+delta*(-1/6+delta*(1/12+delta*(-1/20+delta/30))))
    regular = counts*engine.xp.log(engine.clamp(counts/mu,1e-30))-counts+mu
    terms = engine.xp.where(engine.xp.abs(delta)<.01,series,regular)
    return 2*engine.sum(engine.clamp(terms,0),1)

def observed_check(engine, counts, params):
    """This guard sees observations, known noise, and bounds; never true fields."""
    x = engine.xp
    finite = x.isfinite(params).all(dim=1) if engine.backend=="torch" else np.isfinite(params).all(axis=1)
    bounded = ((params>=engine.lower)&(params<=engine.upper))
    bounded = bounded.all(dim=1) if engine.backend=="torch" else bounded.all(axis=1)
    safe = x.where((finite & bounded)[:,None],params,engine.array([CFG["nominal"]]))
    reduced = deviance(engine,counts,engine.spectrum(safe),CFG["photons_per_bin"])/(CFG["frequency_bins"]-8)
    return finite & bounded & x.isfinite(reduced) & (reduced<=CFG["max_reduced_deviance"]), reduced

def initialize(engine, counts, mode="calibrated", width=2.):
    n = len(counts)
    params = engine.array(np.broadcast_to(CFG["nominal"],(n,8)).copy())
    rates = counts/CFG["photons_per_bin"]
    if mode=="affine":
        nominal_rates,inverse = engine.affine_calibration()
        adjustment = (rates-nominal_rates) @ inverse.T
        params = params + adjustment*engine.scale
        return engine.clamp(params,engine.lower,engine.upper)
    params[:,4] = width
    wing = engine.xp.cat([rates[:,:24],rates[:,-24:]],dim=1) if engine.backend=="torch" else np.concatenate([rates[:,:24],rates[:,-24:]],axis=1)
    params[:,6] = engine.sum(wing,1)/48
    params[:,7] = (engine.sum(rates[:,-24:],1)-engine.sum(rates[:,:24],1))/48
    params = engine.clamp(params,engine.lower,engine.upper)
    if mode=="calibrated":
        return params
    if mode!="peaks":
        raise ValueError("Unknown initializer")
    nominal = engine.array([CFG["nominal"]])
    centers,gradients = engine.transitions(nominal,True)
    mask = engine.xp.abs(engine.freq[None,:]-centers[0,:,None])<=3.
    costs = rates[:,None,:]+(~mask)[None,:,:]*1e6
    indexes = costs.argmin(dim=2) if engine.backend=="torch" else costs.argmin(axis=2)
    shifts = engine.freq[indexes]-centers
    inverse = engine.xp.linalg.pinv(gradients[0])
    params[:,:4] = params[:,:4]+shifts@inverse.T
    return engine.clamp(params,engine.lower,engine.upper)

def fit_chunk(engine,counts,*,mode="affine",width=2.):
    e,x = engine,engine.xp
    p = initialize(e,counts,mode,width)
    # Every multistart differs only by this prospective width, not hidden labels.
    p[:,4] = width
    n = len(p)
    damping = e.array(np.full(n,.01))
    converged = x.zeros(n,dtype=x.bool,device=e.device) if e.backend=="torch" else np.zeros(n,dtype=bool)
    identity = x.eye(8,dtype=e.real_dtype,device=e.device) if e.backend=="torch" else np.eye(8,dtype=e.real_dtype)
    exposure = CFG["photons_per_bin"]
    loss = deviance(e,counts,e.spectrum(p),exposure)
    iterations = 0
    for iterations in range(1,CFG["iterations"]+1):
        rates,derivative = e.spectrum(p,True)
        rates = e.clamp(rates,1e-12)
        weighted_j = derivative*e.scale[None,None,:]*x.sqrt(exposure/rates)[:,:,None]
        residual = (counts/exposure-rates)*x.sqrt(exposure/rates)
        normal = x.einsum("nfi,nfj->nij",weighted_j,weighted_j)
        rhs = x.einsum("nfi,nf->ni",weighted_j,residual)
        diag = normal.diagonal(dim1=-2,dim2=-1) if e.backend=="torch" else np.diagonal(normal,axis1=-2,axis2=-1)
        system = normal+identity[None,:,:]*(damping[:,None]*e.clamp(diag,1e-12))[:,None,:]
        delta = x.linalg.solve(system,rhs[:,:,None])[:,:,0]
        trial = e.clamp(p+delta*e.scale,e.lower,e.upper)
        trial_loss = deviance(e,counts,e.spectrum(trial),exposure)
        accept = x.isfinite(trial_loss)&(trial_loss<=loss)
        step = x.amax(x.abs((trial-p)/e.scale),dim=1) if e.backend=="torch" else np.max(np.abs((trial-p)/e.scale),axis=1)
        converged = converged|(accept&(step<=CFG["relative_step_tolerance"]))
        p = x.where(accept[:,None],trial,p)
        loss = x.where(accept,trial_loss,loss)
        damping = e.clamp(x.where(accept,damping/3,damping*10),1e-8,1e12)
        if bool(converged.all()):
            break
    accepted,reduced = observed_check(e,counts,p)
    return {"parameters":p,"deviance":loss,"accepted":accepted,"converged":converged,
            "reduced_deviance":reduced,"iterations":iterations}

def full_fallback(engine,counts):
    best = None
    for width in (1.,2.,3.):
        candidate = fit_chunk(engine,counts,mode="affine",width=width)
        if best is None:
            best = candidate
        else:
            choose = (candidate["accepted"]&~best["accepted"])|(
                (candidate["accepted"]==best["accepted"])&(candidate["deviance"]<best["deviance"]))
            for key in ("parameters","deviance","accepted","converged","reduced_deviance"):
                best[key] = engine.xp.where(choose[:,None] if key=="parameters" else choose,candidate[key],best[key])
            best["iterations"] += candidate["iterations"]
    return best

def policy_device(engine,counts,variant="affine"):
    """Resident-data policy, including its residual guard and all rejected rows."""
    e,x = engine,engine.xp
    if variant not in ("affine","peaks","calibrated","lm"):
        raise ValueError("Unknown policy")
    parts = {"parameters":[],"accepted":[],"reduced_deviance":[],"fallback":[]}
    for start in range(0,len(counts),CFG["chunk_size"]):
        batch = counts[start:start+CFG["chunk_size"]]
        if variant=="lm":
            solution = full_fallback(e,batch)
            fallback = x.ones(len(batch),dtype=x.bool,device=e.device) if e.backend=="torch" else np.ones(len(batch),dtype=bool)
        else:
            p = initialize(e,batch,variant)
            accepted,reduced = observed_check(e,batch,p)
            fallback = ~accepted
            # The mask comes only from observed likelihood. It never sees target parameters.
            if bool(fallback.any()):
                repaired = full_fallback(e,batch[fallback])
                p[fallback] = repaired["parameters"]
                accepted[fallback] = repaired["accepted"]
                reduced[fallback] = repaired["reduced_deviance"]
            solution = {"parameters":p,"accepted":accepted,"reduced_deviance":reduced}
        for key in parts:
            parts[key].append(fallback if key=="fallback" else solution[key])
    if not len(counts):
        raise ValueError("Empty batch")
    return {key:(x.cat(value,dim=0) if e.backend=="torch" else np.concatenate(value,axis=0))
            for key,value in parts.items()}

def fit_counts(counts,*,backend="numpy",device="cpu",dtype="float64",variant="affine"):
    """Host-in/host-out: count transfer, calibration, guard, solve and output transfer."""
    counts = validate_counts(counts)
    e = Engine(backend,device,dtype)
    result = policy_device(e,e.array(counts),variant)
    e.sync()
    return {key:e.numpy(value) for key,value in result.items()}
