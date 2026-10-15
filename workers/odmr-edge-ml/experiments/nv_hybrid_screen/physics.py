"""Source-faithful axial two-line mean and analytic derivatives; no old data."""
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scalar_information_limit"))
from forward import Point,forward,FREQUENCIES_MHZ,GAMMA_MHZ_UT
F=FREQUENCIES_MHZ;BIAS=250.;FACTOR=.9957299574916568;PHOTONS=(10/(.30*.015))**2
LOW=np.array([20,2865,.5,.001,.9,-.08]);HIGH=np.array([70,2878,12,.06,1.1,.08])
SCALE=np.array([45,1,5,.015,1,.02]);X=(F-2870)/100
SAT=.1*np.linspace(1-.196875/2,1+.196875/2,10)**2
AMP=.03*(SAT/(1+SAT))/(.1/1.1)
def mean_jac(p):
    B,c,w,C,b,s=p
    h=w*np.sqrt(1+SAT)/2
    centers=c+GAMMA_MHZ_UT*(B+BIAS)*np.array([-1.,1.])
    distance=F[None,None,:]-centers[None,:,None]
    den=distance**2+h[:,None,None]**2
    L=h[:,None,None]**2/den
    dc=2*h[:,None,None]**2*distance/den**2
    dw=2*h[:,None,None]*distance**2/den**2*(h[:,None,None]/w)
    average=lambda q:np.mean(AMP[:,None]*np.sum(.5*q,axis=1),axis=0)
    depth=average(L)
    deriv=np.column_stack((average(dc*GAMMA_MHZ_UT*np.array([-1.,1.])[None,:,None]),
                           average(dc),average(dw)))
    interp=lambda v:np.interp(F-.3,F,v,left=v[0],right=v[-1])
    dip=interp(depth)
    jac=np.zeros((100,6));jac[:,:3]=-FACTOR*(C/.015)*np.column_stack([interp(deriv[:,i]) for i in range(3)])
    jac[:,3]=-FACTOR/.015*dip;jac[:,4]=1;jac[:,5]=X
    return b-FACTOR*(C/.015)*dip+s*X,jac
def center(y):
    ix=np.r_[0:15,85:100];trend=np.polyval(np.polyfit(F[ix],y[ix],1),F)
    dip=np.maximum(trend-y,0)
    return float(np.clip(np.dot(F,dip)/dip.sum()-.3,2868,2875)) if dip.sum()>0 else 2871.50827
def fixed_starts(y):
    return [np.array([B,c,5,.015,1,.0]) for B in (25,45,65) for c in (2871.50827,center(y))]
def refine(y,start):
    weight=1/np.sqrt(np.clip(y,.8,1.2))
    result=least_squares(lambda p:(mean_jac(p)[0]-y)*weight,np.clip(start,LOW+1e-9,HIGH-1e-9),
        jac=lambda p:mean_jac(p)[1]*weight[:,None],bounds=(LOW,HIGH),x_scale=SCALE,
        method="trf",loss="linear",max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
    chi=float(2*result.cost*PHOTONS/94)
    return {"parameters":result.x,"score":chi,"success":bool(result.success and np.isfinite(result.x).all()),
            "nfev":int(result.nfev),"boundary":bool(np.any(result.active_mask))}
def choose(results):
    valid=[r for r in results if r["success"] and np.isfinite(r["score"])]
    return min(valid,key=lambda r:r["score"]) if valid else None
