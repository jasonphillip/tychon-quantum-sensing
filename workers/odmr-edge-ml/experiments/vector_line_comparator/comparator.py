"""Tied Lorentzian fit followed by numerical, unknown-D Hamiltonian inversion.

The numerical primitives follow vector_direct_screen at commit 18395df.
This is a PyTorch mathematical comparator, not a native Gpufit speed result.
"""
from __future__ import annotations
import numpy as np
from experiments.vector_direct_screen.physics import CFG, Engine, validate_counts
from experiments.vector_direct_screen.baseline import (
    deviance, initialize, observed_check, full_fallback,
)


class TiedLines:
    """[baseline, slope, FWHM, shared dip amplitude, eight centered frequencies]."""
    def __init__(self, engine):
        if engine.backend != "torch":
            raise ValueError("This comparator uses the existing PyTorch allocator only")
        self.e, self.xp = engine, engine.xp
        nominal = engine.transitions(engine.array([CFG["nominal"]]))[0] - 2870.
        # Weyl: each transition moves at most twice the Hamiltonian norm change.
        delta_b = np.linalg.norm(np.maximum(np.abs(CFG["lower"][:3]),
                                            np.abs(CFG["upper"][:3])))
        self.envelope = 2 * (CFG["gamma_MHz_per_uT"] * delta_b + .4)
        order = self.xp.argsort(nominal)
        ordered = nominal[order]
        if not bool(((ordered[1:] - ordered[:-1]) > 2*self.envelope).all()):
            raise ValueError("Prior line intervals overlap: association not qualified")
        self.nominal, self.order = nominal, order
        self.lower = self.xp.cat([engine.array([.98, -.01, 1., -1.02*.12/8]),
                                 nominal-self.envelope])
        self.upper = self.xp.cat([engine.array([1.02, .01, 3., -.98*.02/8]),
                                 nominal+self.envelope])
        self.scale = engine.array([.02, .01, 1., .05/8] + [1.]*8)

    def from_physical(self, physical):
        e = self.e
        return self.xp.cat([physical[:,6:7], physical[:,7:8], physical[:,4:5],
            -physical[:,6:7]*physical[:,5:6]/8,
            e.transitions(physical)-2870.], dim=1)

    def spectrum(self, p, jacobian=False):
        e, x = self.e, self.xp
        d = e.freq[None,None,:]-2870.-p[:,4:,None]
        g = p[:,2,None,None]/2
        den = d*d + g*g
        lorentz = g*g/den
        total = lorentz.sum(dim=1)
        values = p[:,0,None] + p[:,1,None]*e.x + p[:,3,None]*total
        if not jacobian:
            return values
        width = (p[:,3,None,None]*g*d*d/(den*den)).sum(dim=1)
        centers = 2*p[:,3,None,None]*g*g*d/(den*den)
        jac = x.cat([x.ones_like(values)[:,:,None],
            e.x[None,:,None].expand(len(p),-1,-1), width[:,:,None],
            total[:,:,None], centers.transpose(1,2)], dim=2)
        return values, jac


def _solve(e, normal, rhs, damping):
    """Keep singular systems row-local; never turn them into accepted estimates."""
    x = e.xp
    diagonal = normal.diagonal(dim1=-2,dim2=-1)
    system = normal + x.diag_embed(damping[:,None]*e.clamp(diagonal,1e-12))
    delta, info = x.linalg.solve_ex(system, rhs[:,:,None], check_errors=False)
    delta = delta[:,:,0]
    valid = (info == 0) & x.isfinite(delta).all(dim=1)
    return x.where(valid[:,None],delta,x.zeros_like(delta)), valid


def fit_lines(e, counts, physical_start):
    """One fixed start; Poisson Fisher scoring with the inherited deviance guard."""
    x, model = e.xp, TiedLines(e)
    p = model.from_physical(physical_start)
    damping = e.array(np.full(len(p),.01))
    scale = model.scale
    exposure = CFG["photons_per_bin"]
    loss = deviance(e,counts,model.spectrum(p),exposure)
    valid = x.ones(len(p),device=e.device,dtype=x.bool)
    converged = x.zeros_like(valid)
    for iteration in range(1,CFG["iterations"]+1):
        rates,jac = model.spectrum(p,True)
        rootweight = x.sqrt(exposure/e.clamp(rates,1e-12))
        weighted = jac*scale[None,None,:]*rootweight[:,:,None]
        normal = x.einsum("nfi,nfj->nij",weighted,weighted)
        rhs = x.einsum("nfi,nf->ni",weighted,(counts/exposure-rates)*rootweight)
        delta, solved = _solve(e,normal,rhs,damping)
        valid &= solved
        trial = e.clamp(p+delta*scale,model.lower,model.upper)
        trial_loss = deviance(e,counts,model.spectrum(trial),exposure)
        accept = solved & x.isfinite(trial_loss) & (trial_loss<=loss)
        step = x.amax(x.abs((trial-p)/scale),dim=1)
        converged |= accept & (step<=CFG["relative_step_tolerance"])
        p = x.where(accept[:,None],trial,p)
        loss = x.where(accept,trial_loss,loss)
        damping = e.clamp(x.where(accept,damping/3,damping*10),1e-8,1e12)
        if bool(converged.all()):
            break
    # Fitted-rate expected Poisson Fisher, not the count-weighted observed Hessian.
    # Schur complement retains correlations after profiling the four line nuisances.
    rates,jac = model.spectrum(p,True)
    weighted = jac*x.sqrt(exposure/e.clamp(rates,1e-12))[:,:,None]
    fisher = x.einsum("nfi,nfj->nij",weighted,weighted)
    nn,nc,cc = fisher[:,:4,:4],fisher[:,:4,4:],fisher[:,4:,4:]
    nuisance_solution,info = x.linalg.solve_ex(nn,nc,check_errors=False)
    precision = cc-nc.transpose(1,2)@nuisance_solution
    precision = (precision+precision.transpose(1,2))/2
    finite = x.isfinite(precision).all(dim=(1,2)) & (info==0)
    identity = x.eye(8,dtype=e.real_dtype,device=e.device).expand(len(p),-1,-1)
    precision = x.where(finite[:,None,None],precision,identity)
    eigenvalues = x.linalg.eigvalsh(precision)
    identifiable = (eigenvalues[:,0] > eigenvalues[:,-1]*1e-10) & (eigenvalues[:,-1]>0)
    valid &= finite & identifiable & x.isfinite(p).all(dim=1)
    precision = x.where(valid[:,None,None],precision,identity)
    return {"parameters":p,"precision":precision,"valid":valid,
            "converged":converged,"iterations":iteration,"deviance":loss}


def recover_field(e, lines, precision, physical_start):
    """Four-parameter numerical inversion: three field coordinates plus unknown D.

    Known-bias nonoverlapping envelopes establish the labels. No true field,
    true D, or target line association enters this calculation.
    """
    x = e.xp
    p = physical_start.clone()
    p[:,4] = lines[:,2]
    p[:,5] = -8*lines[:,3]/lines[:,0]
    p[:,6] = lines[:,0]
    p[:,7] = lines[:,1]
    target = lines[:,4:] + 2870.
    damping = e.array(np.full(len(p),.01))
    scale = e.scale[:4]
    valid = x.ones(len(p),device=e.device,dtype=x.bool)
    converged = x.zeros_like(valid)
    def objective(params):
        residual = target-e.transitions(params)
        return x.einsum("ni,nij,nj->n",residual,precision,residual)
    loss = objective(p)
    for iteration in range(1,CFG["iterations"]+1):
        predicted,jac = e.transitions(p,True)
        jac = jac*scale[None,None,:]
        normal = x.einsum("nli,nlm,nmj->nij",jac,precision,jac)
        rhs = x.einsum("nli,nlm,nm->ni",jac,precision,target-predicted)
        delta,solved = _solve(e,normal,rhs,damping)
        valid &= solved
        trial = p.clone()
        trial[:,:4] = e.clamp(p[:,:4]+delta*scale,e.lower[:4],e.upper[:4])
        trial_loss = objective(trial)
        accept = solved & x.isfinite(trial_loss) & (trial_loss<=loss)
        step = x.amax(x.abs((trial[:,:4]-p[:,:4])/scale),dim=1)
        converged |= accept & (step<=CFG["relative_step_tolerance"])
        p = x.where(accept[:,None],trial,p)
        loss = x.where(accept,trial_loss,loss)
        damping = e.clamp(x.where(accept,damping/3,damping*10),1e-8,1e12)
        if bool(converged.all()):
            break
    return {"parameters":p,"valid":valid,"converged":converged,
            "iterations":iteration,"frequency_objective":loss}


def policy_device(e,counts,*,chunk_size=1024):
    """Include identical physical guard and inherited bounded three-width fallback."""
    if type(chunk_size) is not int or chunk_size != 1024:
        raise ValueError("Only the prospective 1024-row chunk is registered")
    x = e.xp
    parts = {k:[] for k in ("parameters","accepted","fallback","reduced_deviance",
                           "line_valid","line_converged","inverse_valid","inverse_converged")}
    for start in range(0,len(counts),chunk_size):
        batch = counts[start:start+chunk_size]
        initial = initialize(e,batch,"affine")
        fitted = fit_lines(e,batch,initial)
        inverse = recover_field(e,fitted["parameters"],fitted["precision"],initial)
        p = inverse["parameters"]
        accepted,reduced = observed_check(e,batch,p)
        accepted &= fitted["valid"] & inverse["valid"]
        fallback = ~accepted
        if bool(fallback.any()):
            repaired = full_fallback(e,batch[fallback])
            p[fallback] = repaired["parameters"]
            accepted[fallback] = repaired["accepted"]
            reduced[fallback] = repaired["reduced_deviance"]
        row = dict(parameters=p,accepted=accepted,fallback=fallback,reduced_deviance=reduced,
            line_valid=fitted["valid"],line_converged=fitted["converged"],
            inverse_valid=inverse["valid"],inverse_converged=inverse["converged"])
        for key in parts:
            parts[key].append(row[key])
    if not parts["parameters"]:
        raise ValueError("Empty input")
    return {key:x.cat(values,dim=0) for key,values in parts.items()}


def fit_counts(counts,device="cpu",dtype="float64",*,chunk_size=1024):
    """Host-in/host-out route; timing must include setup, both fits and fallback."""
    e = Engine("torch",device,dtype)
    result = policy_device(e,e.array(validate_counts(counts)),chunk_size=chunk_size)
    e.sync()
    return {key:e.numpy(value) for key,value in result.items()}
