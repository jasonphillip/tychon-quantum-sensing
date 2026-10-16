"""Fixed-step LM warm starts with unchanged observed guard and full fallback."""
import numpy as np
from experiments.vector_direct_screen.physics import CFG
from experiments.vector_direct_screen.baseline import initialize,deviance,observed_check,full_fallback
METHODS=("lm","affine1","affine3","affine5","tied12","neural1")

def refine(engine,counts,initial,steps):
    """The original LM update algebra, exactly 1/3/5 attempts, no early exit.

    Both initializers retain all eight initial parameters, including linewidth.
    Unlike the historical multistart solver, this is not a width-grid restart.
    """
    if steps not in (1,3,5):raise ValueError("Unregistered refinement budget")
    e,x=engine,engine.xp;p=e.clamp(initial,e.lower,e.upper)
    damping=e.array(np.full(len(p),.01));exposure=CFG["photons_per_bin"]
    identity=x.eye(8,dtype=e.real_dtype,device=e.device) if e.backend=="torch" else np.eye(8,dtype=e.real_dtype)
    loss=deviance(e,counts,e.spectrum(p),exposure)
    attempted=[]
    for _ in range(steps):
        rates,derivative=e.spectrum(p,True);rates=e.clamp(rates,1e-12)
        weighted_j=derivative*e.scale[None,None,:]*x.sqrt(exposure/rates)[:,:,None]
        residual=(counts/exposure-rates)*x.sqrt(exposure/rates)
        normal=x.einsum("nfi,nfj->nij",weighted_j,weighted_j)
        rhs=x.einsum("nfi,nf->ni",weighted_j,residual)
        diag=normal.diagonal(dim1=-2,dim2=-1) if e.backend=="torch" else np.diagonal(normal,axis1=-2,axis2=-1)
        system=normal+identity[None,:,:]*(damping[:,None]*e.clamp(diag,1e-12))[:,None,:]
        delta=x.linalg.solve(system,rhs[:,:,None])[:,:,0]
        trial=e.clamp(p+delta*e.scale,e.lower,e.upper)
        trial_loss=deviance(e,counts,e.spectrum(trial),exposure)
        accept=x.isfinite(trial_loss)&(trial_loss<=loss)
        p=x.where(accept[:,None],trial,p);loss=x.where(accept,trial_loss,loss)
        damping=e.clamp(x.where(accept,damping/3,damping*10),1e-8,1e12)
        attempted.append(accept)
    return p,e.stack(attempted,1)

def policy(engine,counts,method,neural=None,chunk=1024):
    if method not in METHODS or chunk!=1024:raise ValueError("Unregistered policy")
    if method=="tied12":
        from experiments.vector_line_comparator.comparator import policy_device
        return policy_device(engine,counts,chunk_size=chunk)
    e,x=engine,engine.xp;parts={k:[] for k in ("parameters","accepted","reduced_deviance","fallback","refinement_accepts")}
    for start in range(0,len(counts),chunk):
        batch=counts[start:start+chunk]
        if method=="lm":
            s=full_fallback(e,batch);p=s["parameters"];accepted=s["accepted"];reduced=s["reduced_deviance"]
            fallback=x.ones(len(batch),dtype=x.bool,device=e.device) if e.backend=="torch" else np.ones(len(batch),bool)
            attempts=x.zeros(len(batch),dtype=x.int64,device=e.device) if e.backend=="torch" else np.zeros(len(batch),int)
        else:
            if method=="neural1":
                if neural is None:raise ValueError("Frozen learned initializer required")
                p=neural(batch);steps=1
            else:p=initialize(e,batch,"affine");steps=int(method[-1])
            p,accepted_steps=refine(e,batch,p,steps);attempts=e.sum(accepted_steps,1)
            accepted,reduced=observed_check(e,batch,p);fallback=~accepted
            if bool(fallback.any()):
                repaired=full_fallback(e,batch[fallback]);p[fallback]=repaired["parameters"]
                accepted[fallback]=repaired["accepted"];reduced[fallback]=repaired["reduced_deviance"]
        row=dict(parameters=p,accepted=accepted,reduced_deviance=reduced,fallback=fallback,refinement_accepts=attempts)
        for key in parts:parts[key].append(row[key])
    if not len(counts):raise ValueError("Empty batch")
    return {k:x.cat(v,0) if e.backend=="torch" else np.concatenate(v,0) for k,v in parts.items()}
