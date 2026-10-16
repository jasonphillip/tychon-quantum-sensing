"""Three classical challenges and one unchanged-weight neural zero-step route."""
import numpy as np
from experiments.vector_direct_screen.physics import CFG
from experiments.vector_direct_screen.baseline import initialize,deviance,observed_check,full_fallback
from experiments.vector_initializer_development.methods import policy as frozen_policy
METHODS=("lm","affine3","tied12","neural1","affine2_f64","affine2_f32","affine3_f32","neural0")
CLASSICAL=("lm","affine3","tied12","affine2_f64","affine2_f32","affine3_f32")
NEURAL=("neural1","neural0")
COMMON=("parameters","accepted","reduced_deviance","fallback")

def refine(engine,counts,initial,steps):
    """The frozen P1 LM update algebra; exactly 2/3 attempts, no early exit.

    Both initializers retain all eight initial parameters, including linewidth.
    Unlike the historical multistart solver, this is not a width-grid restart.
    """
    if steps not in (2,3):raise ValueError("Unregistered refinement budget")
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


def double_guard(engine,counts,proposal):
    """No float32 deviance or hidden labels participate in final acceptance."""
    if str(engine.real_dtype) not in ("torch.float64","float64","<class 'numpy.float64'>"):raise ValueError("Float64 guard engine required")
    p=engine.array(proposal)
    accepted,reduced=observed_check(engine,counts,p)
    return p,accepted,reduced

def policy(engine,counts,method,neural=None,mixed_engine=None,chunk=1024):
    if method not in METHODS or chunk!=1024:raise ValueError("Unregistered challenge route")
    if method in ("lm","affine3","tied12","neural1"):
        return frozen_policy(engine,counts,method,neural,chunk)
    if not len(counts):raise ValueError("Empty batch")
    e,x=engine,engine.xp
    parts={k:[] for k in (*COMMON,"refinement_accepts","proposal_parameters","proposal_accepted","proposal_reduced_deviance")}
    for start in range(0,len(counts),chunk):
        batch=counts[start:start+chunk]
        if method=="neural0":
            if neural is None:raise ValueError("Frozen neural initializer required")
            proposal=neural(batch)
            attempts=x.zeros(len(batch),dtype=x.int64,device=e.device) if e.backend=="torch" else np.zeros(len(batch),int)
        else:
            mixed=method.endswith("f32");step_engine=mixed_engine if mixed else e
            if step_engine is None:raise ValueError("Persistent float32 engine required")
            if mixed and str(step_engine.real_dtype) not in ("torch.float32","float32","<class 'numpy.float32'>"):raise ValueError("Wrong refinement precision")
            step_counts=step_engine.array(batch);steps=2 if method.startswith("affine2") else 3
            initial=initialize(step_engine,step_counts,"affine")
            proposal,accepted_steps=refine(step_engine,step_counts,initial,steps)
            attempts=step_engine.sum(accepted_steps,1)
        # The cast is inside the timed route. Do not clamp after this cast.
        p,accepted,reduced=double_guard(e,batch,proposal)
        proposal_copy=p.clone() if e.backend=="torch" else p.copy()
        proposal_accepted=accepted.clone() if e.backend=="torch" else accepted.copy()
        proposal_reduced=reduced.clone() if e.backend=="torch" else reduced.copy()
        fallback=~accepted
        if bool(fallback.any()):
            fixed=full_fallback(e,batch[fallback]);p[fallback]=fixed["parameters"]
            accepted[fallback]=fixed["accepted"];reduced[fallback]=fixed["reduced_deviance"]
        row=dict(parameters=p,accepted=accepted,reduced_deviance=reduced,fallback=fallback,
            refinement_accepts=attempts,proposal_parameters=proposal_copy,
            proposal_accepted=proposal_accepted,proposal_reduced_deviance=proposal_reduced)
        for key in parts:parts[key].append(row[key])
    return {k:x.cat(v,0) if e.backend=="torch" else np.concatenate(v,0) for k,v in parts.items()}
