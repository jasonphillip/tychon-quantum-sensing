"""Input-only background, bounded two-line fitting, and declared-prior inference."""
from dataclasses import asdict, dataclass, field
import time
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import find_peaks

GAMMA_MHZ_UT = 0.028035
TRAIN_MEDIAN = 44.90404360960018
TRAIN_MEAN = 45.064080128749545
GRID = np.linspace(2.82e9, 2.92e9, 100)
EDGE = np.r_[np.arange(20), np.arange(80, 100)]
LOWER = np.array([0.5, -0.002, -10., 0., 0., 0., 0.30])
UPPER = np.array([1.5, 0.002, 10., 4.20, 0.10, 0.10, 6.00])

@dataclass
class FitResult:
    raw_projection_uT: float = float("nan")
    raw_magnitude_uT: float = float("nan")
    prediction_uT: float = TRAIN_MEDIAN
    lock_bin: int = 50
    slope_per_MHz: float = 0.
    hard_invalid: bool = True
    ambiguous: bool = True
    reasons: list = field(default_factory=list)
    params: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)
    seconds: float = 0.
    def as_dict(self):
        return asdict(self)

def validate(row, freqs):
    y, f = np.asarray(row, dtype=float), np.asarray(freqs, dtype=float)
    if y.shape != (100,) or f.shape != (100,) or not np.isfinite(y).all():
        raise ValueError("need a finite 100-point spectrum")
    if not np.isfinite(f).all() or not np.allclose(f, GRID, rtol=0, atol=1e-6):
        raise ValueError("frequency grid differs from frozen model contract")
    return y, (f - (f[0]+f[-1])/2)/1e6

def edge_ols(row, freqs=GRID):
    y, x = validate(row, freqs)
    coef = np.linalg.lstsq(np.column_stack((np.ones(40), x[EDGE])), y[EDGE], rcond=None)[0]
    return y - coef[1]*x, float(coef[1]), float(coef[0])

def noise_scale(y):
    d = np.r_[np.diff(y[:20]), np.diff(y[-20:])]
    return max(1e-5, float(1.4826*np.median(abs(d-np.median(d)))/np.sqrt(2)))

def profile(x, p):
    b, slope, center, split, a, c, width = p
    u = (x-center+split/2)/width
    v = (x-center-split/2)/width
    return b+slope*x-a/(1+u*u)-c/(1+v*v)

def jacobian(x, p):
    _, _, center, split, a, c, width = p
    u = (x-center+split/2)/width
    v = (x-center-split/2)/width
    uu, vv = 1+u*u, 1+v*v
    d1, d2 = -2*a*u/(width*uu*uu), -2*c*v/(width*vv*vv)
    return np.column_stack((np.ones_like(x),x,d1+d2,(-d1+d2)/2,
        -1/uu,-1/vv,-2*(a*u*u/(uu*uu)+c*v*v/(vv*vv))/width))

def prior_median(projection):
    if not np.isfinite(projection) or projection < 0 or projection > 70:
        raise ValueError("projection outside declared prior support")
    return float(np.sqrt(70*max(20, projection)))

def robust_fit(row, freqs=GRID):
    started = time.perf_counter()
    out = FitResult()
    try:
        y, x = validate(row, freqs)
        corrected, slope, baseline = edge_ols(y, freqs)
    except ValueError as exc:
        out.reasons = [str(exc)]
        out.seconds = time.perf_counter()-started
        return out
    noise = noise_scale(corrected)
    if np.ptp(corrected) <= max(1e-9, 3*noise):
        out.reasons = ["flat_or_low_signal"]
        out.seconds = time.perf_counter()-started
        return out
    roi = np.flatnonzero(abs(x) <= 10)
    low = roi[np.argmin(corrected[roi])]
    center = float(x[low])
    peaks, props = find_peaks(-corrected, prominence=3*noise)
    peaks = peaks[abs(x[peaks]) <= 10]
    if len(peaks) >= 2:
        selected = np.sort(peaks[np.argsort(corrected[peaks])[:2]])
        c0 = float(np.mean(x[selected])); s0 = float(np.diff(x[selected])[0])
    else:
        c0, s0 = center, 1.5
    depth = float(np.clip(np.median(corrected[EDGE])-corrected[low], 0.001, 0.08))
    specs = [(c0,s0,.8),(center,1.,2.5),(center,3.5,2.5),(0.,2.,.8)]
    fits = []
    for cen, split, width in specs:
        p0 = np.clip([baseline,slope,cen,split,depth/2,depth/2,width], LOWER+1e-9, UPPER-1e-9)
        fit = least_squares(lambda p:(profile(x,p)-y)/noise, p0,
            jac=lambda p:jacobian(x,p)/noise, bounds=(LOWER,UPPER),
            loss="soft_l1", f_scale=1., max_nfev=200, ftol=1e-8, xtol=1e-8, gtol=1e-8)
        if np.isfinite(fit.x).all() and np.isfinite(fit.cost):
            fits.append(fit)
    out.diagnostics["starts_attempted"] = 4
    if not fits:
        out.reasons=["no_finite_fit"]; out.seconds=time.perf_counter()-started
        return out
    best = min([z for z in fits if z.success] or fits, key=lambda z:z.cost)
    p = best.x
    residual = y-profile(x,p)
    rms = float(np.sqrt(np.mean(residual**2)))
    dip = float(np.max(p[0]+p[1]*x-profile(x,p)))
    projection = float(p[3]/(2*GAMMA_MHZ_UT))
    bound = (p-LOWER)/(UPPER-LOWER)
    # A zero splitting/depth is an ambiguity, not automatically an invalid prediction.
    boundary = bool(np.any((bound[[0,1,2,6]]<1e-4)|(bound[[0,1,2,6]]>1-1e-4)))
    outside = projection > 70 or projection < 0
    fit_reasons = []
    if not best.success: fit_reasons.append("optimizer_failed")
    if boundary: fit_reasons.append("baseline_center_width_boundary")
    if max(p[4],p[5])>=.10*(1-1e-4):fit_reasons.append("depth_upper_boundary")
    if outside: fit_reasons.append("projection_out_of_support")
    if rms > max(3*noise, .15*dip): fit_reasons.append("poor_residual")
    if dip < 5*noise: fit_reasons.append("low_dip_snr")
    separation_floor = max(float(np.median(np.diff(x))), float(p[6]))
    unresolved = bool(p[3] < separation_floor or min(p[4],p[5]) < 3*noise)
    out.raw_projection_uT = projection
    out.raw_magnitude_uT = prior_median(projection) if not outside else float("nan")
    out.hard_invalid = bool(fit_reasons)
    out.ambiguous = unresolved
    out.prediction_uT = TRAIN_MEDIAN if out.hard_invalid else out.raw_magnitude_uT
    out.lock_bin = int(np.argmin(abs(x-p[2])))
    out.slope_per_MHz = float(p[1])
    out.reasons = fit_reasons
    out.params = p.tolist()
    out.diagnostics.update(converged=bool(best.success),nfev=int(best.nfev),
        total_nfev=int(sum(z.nfev for z in fits)),rms=rms,noise_sigma=noise,
        dip_depth=dip,boundary=boundary,projection_out_of_support=outside,
        unresolved=unresolved,ambiguity_separation_floor_MHz=separation_floor,
        centers_MHz=[float(p[2]-p[3]/2),float(p[2]+p[3]/2)],
        fwhm_MHz=float(2*p[6]),residual_limit=max(3*noise,.15*dip))
    out.seconds=time.perf_counter()-started
    return out

def likelihood_magnitude(row, fit, freqs=GRID, points=64):
    """Conditional splitting likelihood, with fixed fitted center/width.

    Linear nuisance parameters are re-fitted at every splitting. This is NOT
    full nuisance marginalization; intervals are conditional, uncalibrated.
    """
    if points != 64: raise ValueError("the frozen splitting grid has 64 points")
    y, x = validate(row, freqs)
    if fit.hard_invalid:
        return dict(raw_prediction_uT=float("nan"),prediction_uT=TRAIN_MEDIAN,
            hard_invalid=True,ambiguous=True,interval90_uT=[20.,70.],
            reason="invalid_joint_fit",grid_points=64)
    b = np.column_stack((np.ones(len(x)),x))
    q, _ = np.linalg.qr(b)
    project = lambda a:a-q@(q.T@a)
    target=project(y)
    z=np.linspace(0.,70.,points)
    p=np.asarray(fit.params)
    s=2*GAMMA_MHZ_UT*z
    l1=-1/(1+((x[:,None]-p[2]+s[None,:]/2)/p[6])**2)
    l2=-1/(1+((x[:,None]-p[2]-s[None,:]/2)/p[6])**2)
    a1,a2=project(l1),project(l2)
    # Exact two-variable NNLS after eliminating the unrestricted affine baseline.
    aa=(a1*a1).sum(0);bb=(a2*a2).sum(0);ab=(a1*a2).sum(0)
    ay=a1.T@target;by=a2.T@target;det=aa*bb-ab*ab
    d1=np.divide(ay*bb-by*ab,det,out=np.zeros(points),where=det>1e-18)
    d2=np.divide(by*aa-ay*ab,det,out=np.zeros(points),where=det>1e-18)
    options=[(np.maximum(d1,0),np.maximum(d2,0)),
             (np.maximum(ay/np.maximum(aa,1e-30),0),np.zeros(points)),
             (np.zeros(points),np.maximum(by/np.maximum(bb,1e-30),0)),
             (np.zeros(points),np.zeros(points))]
    cost=np.stack([((target[:,None]-a1*u[None,:]-a2*v[None,:])**2).sum(0) for u,v in options])
    invalid_interior=(d1<0)|(d2<0)|(det<=1e-18)
    cost[0,invalid_interior]=np.inf
    rss=cost.min(0)
    sigma=max(fit.diagnostics["noise_sigma"],fit.diagnostics["rms"],1e-5)
    logl=-(rss-rss.min())/(2*sigma*sigma)
    like=np.exp(np.maximum(logl,-745))
    # p(B|data) proportional to integral_0^B L(z) dz / B for the stated prior.
    cumulative=np.r_[0.,np.cumsum((like[1:]+like[:-1])*np.diff(z)/2)]
    bg=np.linspace(20.,70.,501)
    density=np.interp(bg,z,cumulative)/bg
    cdf=np.r_[0.,np.cumsum((density[1:]+density[:-1])*np.diff(bg)/2)]
    if not np.isfinite(cdf[-1]) or cdf[-1]<=0:
        return dict(raw_prediction_uT=float("nan"),prediction_uT=TRAIN_MEDIAN,
            hard_invalid=True,ambiguous=True,interval90_uT=[20.,70.],reason="zero_evidence",grid_points=64)
    cdf/=cdf[-1]
    qs=np.interp([.05,.5,.95],cdf,bg)
    return dict(raw_prediction_uT=float(qs[1]),prediction_uT=float(qs[1]),
        hard_invalid=False,ambiguous=fit.ambiguous,interval90_uT=[float(qs[0]),float(qs[2])],
        grid_points=64,conditional_nuisance=True,calibrated=False)

def metrics(pred, truth):
    p,t=np.asarray(pred,dtype=float),np.asarray(truth,dtype=float)
    if p.shape != t.shape or p.ndim!=1 or len(p)==0 or not np.isfinite(p-t).all():
        raise ValueError("metrics require finite complete paired predictions")
    e=p-t;a=abs(e)
    return dict(n=len(e),mae_uT=float(a.mean()),rmse_uT=float(np.sqrt(np.mean(e*e))),
        median_abs_uT=float(np.median(a)),p90_abs_uT=float(np.quantile(a,.9)),
        worst_uT=float(a.max()),bias_uT=float(e.mean()))

def paired_ci(loss_difference, group_ids, draws=10000, seed=202610152001):
    d,g=np.asarray(loss_difference,float),np.asarray(group_ids)
    if d.ndim!=1 or d.shape!=g.shape or not np.isfinite(d).all():
        raise ValueError("invalid paired losses/groups")
    groups=np.unique(g)
    if len(groups)<2: raise ValueError("need at least two independent groups")
    sums=np.array([d[g==v].sum() for v in groups])
    counts=np.array([(g==v).sum() for v in groups])
    rng=np.random.default_rng(seed);values=[]
    for start in range(0,draws,100):
        ids=rng.integers(0,len(groups),size=(min(100,draws-start),len(groups)))
        values.extend(sums[ids].sum(1)/counts[ids].sum(1))
    return dict(mean_difference_uT=float(d.mean()),ci95_uT=np.quantile(values,[.025,.975]).tolist(),
        groups=len(groups),draws=draws,seed=seed)

def checked_fallback(raw, hard_invalid):
    raw=np.asarray(raw,float);bad=np.asarray(hard_invalid,bool)|~np.isfinite(raw)|(raw<20)|(raw>70)
    return np.where(bad,TRAIN_MEDIAN,raw),bad
