"""One frozen practical estimator. This module never opens data or truth files."""
import time
import numpy as np
from scipy.optimize import least_squares

GAMMA = abs(-1.76085963023e11 * 1.000357)/(2*np.pi)*1e-12
FACTOR = 0.9957299574916568
LOW = np.array([20.,2865.,.5,.001,.9,-.08])
HIGH = np.array([70.,2878.,12.,.06,1.1,.08])
SCALE = np.array([45.,1.,5.,.015,1.,.02])
FREQ = np.linspace(2820.,2920.,100)
SATURATION = .1*np.linspace(1-.196875/2,1+.196875/2,10)**2
AMPLITUDE = .03*(SATURATION/(1+SATURATION))/(.1/1.1)

def mean(parameters,frequencies,bias):
    field,center,width,contrast,baseline,slope=parameters
    centers=center+np.array([-1.,1.])*GAMMA*(field+bias)
    half=width*np.sqrt(1+SATURATION)/2
    delta=frequencies[None,None,:]-centers[None,:,None]
    lines=half[:,None,None]**2/(delta**2+half[:,None,None]**2)
    dip=np.mean(AMPLITUDE[:,None]*np.sum(.5*lines,axis=1),axis=0)
    signal=baseline-FACTOR*(contrast/.015)*dip
    shifted=np.interp(frequencies-.3,frequencies,signal,left=signal[0],right=signal[-1])
    return shifted+slope*(frequencies-2870.)/100.

def center_start(observed,frequencies):
    outer=np.r_[np.arange(15),np.arange(len(frequencies)-15,len(frequencies))]
    baseline=np.polyval(np.polyfit(frequencies[outer]-2870.,observed[outer],1),frequencies-2870.)
    dips=np.maximum(baseline-observed,0.)
    if dips.sum()==0:return 2871.50827
    return float(np.clip(np.dot(dips,frequencies)/dips.sum()-.3,2868.,2875.))

def fit_one(observed,frequencies,bias):
    started=time.perf_counter()
    answer={"estimate_uT":45.,"failed":True,"boundary":False,"parameters":None,"starts":[]}
    if observed.shape!=(100,) or not np.isfinite(observed).all():
        answer["failure_reason"]="nonfinite or malformed observation"
        answer["elapsed_seconds"]=time.perf_counter()-started
        return answer
    if not np.array_equal(frequencies,FREQ) or bias not in (0.,250.):
        raise ValueError("unregistered frequencies or bias")
    weights=1/np.sqrt(np.clip(observed,.8,1.2))
    centers=(2871.50827,center_start(observed,frequencies))
    best=None
    for field in (25.,45.,65.):
        for center in centers:
            initial=np.array([field,center,5.,.015,1.,.02])
            before=time.perf_counter()
            record={"initial":initial.tolist()}
            try:
                result=least_squares(lambda p:(mean(p,frequencies,bias)-observed)*weights,
                    initial,bounds=(LOW,HIGH),method="trf",jac="3-point",loss="linear",
                    max_nfev=120,ftol=1e-8,xtol=1e-8,gtol=1e-8,x_scale=SCALE)
                finite=bool(np.isfinite(result.x).all() and np.isfinite(result.fun).all())
                objective=float(np.dot(result.fun,result.fun)) if finite else None
                record.update(success=bool(result.success and finite),status=int(result.status),
                    message=str(result.message),nfev=int(result.nfev),njev=int(result.njev or 0),
                    objective=objective,parameters=result.x.tolist() if finite else None,
                    active_mask=result.active_mask.tolist())
                if record["success"] and (best is None or objective<best["objective"]):best=record
            except (ValueError,FloatingPointError,np.linalg.LinAlgError) as exc:
                record.update(success=False,status=-99,message=type(exc).__name__+": "+str(exc),
                    nfev=None,njev=None,objective=None,parameters=None,active_mask=None)
            record["elapsed_seconds"]=time.perf_counter()-before
            answer["starts"].append(record)
    if best is not None:
        answer.update(estimate_uT=best["parameters"][0],failed=False,
            boundary=bool(any(best["active_mask"])),parameters=best["parameters"])
    else:answer["failure_reason"]="all six starts unsuccessful"
    answer["elapsed_seconds"]=time.perf_counter()-started
    return answer
