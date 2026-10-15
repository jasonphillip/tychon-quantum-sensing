"""Fixed classical initializers and one learned proposal share refinement/fallback."""
import time
import numpy as np
from physics import LOW,HIGH,F,X,mean_jac,fixed_starts,refine,choose
class Estimator:
    def __init__(self,method,weights=None):
        self.method=method
        if method in ("coarse_grid","lookup"):
            self.points=np.array([[b,c,w,.015,1,0] for b in np.linspace(20,70,11)
                for c in np.linspace(2868,2875,9) for w in (4,5,6)])
            means=np.stack([mean_jac(p)[0] for p in self.points])
            self.design=np.stack((1-means,np.ones_like(means),np.broadcast_to(X,means.shape)),axis=2)
            self.pinv=np.linalg.pinv(self.design)
        if method=="hybrid":
            if weights is None:raise ValueError("frozen trained weights required")
            with np.load(weights,allow_pickle=False) as z:self.weights={k:z[k] for k in z.files}
    def grid_starts(self,y):
        linear=np.einsum("gkn,n->gk",self.pinv,y)
        linear[:,0]=np.clip(-linear[:,0],.001/.015,.06/.015)
        linear[:,1]=np.clip(linear[:,1],.9,1.1);linear[:,2]=np.clip(linear[:,2],-.08,.08)
        # Linear initialization is unweighted; every physical refinement is weighted.
        predicted=-self.design[:,:,0]*linear[:,0,None]+linear[:,1,None]+linear[:,2,None]*X
        score=np.sum((predicted-y)**2/np.clip(y,.8,1.2),axis=1)
        order=np.argsort(score)[:4];starts=self.points[order].copy()
        starts[:,3]=.015*linear[order,0];starts[:,4:]=linear[order,1:]
        if self.method=="lookup":
            weights=1/np.maximum(score[order],1e-12);weights/=weights.sum()
            return [np.sum(starts*weights[:,None],axis=0),starts[0]]
        return list(starts[:2])
    def neural_start(self,y):
        x=(y-1)/.03
        for i in range(3):
            x=x@self.weights[f"W{i}"].T+self.weights[f"b{i}"]
            if i<2:x=np.maximum(x,0)
        return LOW+(np.clip(x,0,1))*(HIGH-LOW)
    def __call__(self,y):
        start=time.perf_counter();fallback=False;results=[]
        if y.shape!=(100,) or not np.isfinite(y).all():
            return {"estimate":45.,"failed":True,"accepted":False,"fallback":False,"boundary":False,"seconds":time.perf_counter()-start,"score":None,"nfev":0}
        if self.method=="analytic_multistart":starts=fixed_starts(y)
        elif self.method in ("coarse_grid","lookup"):starts=self.grid_starts(y)
        elif self.method=="hybrid":starts=[self.neural_start(y)]
        else:raise ValueError("unknown method")
        def attempt(p):
            try:return refine(y,p)
            except (ValueError,FloatingPointError,np.linalg.LinAlgError) as exc:
                return {"parameters":np.full(6,np.nan),"score":float("inf"),"success":False,
                        "nfev":0,"boundary":False,"reason":type(exc).__name__}
        results=[attempt(p) for p in starts];best=choose(results)
        if best is None or best["score"]>2:
            fallback=True;results += [attempt(p) for p in fixed_starts(y)];best=choose(results)
        accepted=best is not None and best["score"]<=2
        return {"estimate":float(best["parameters"][0]) if accepted else 45.,
          "failed":not accepted,"accepted":accepted,"fallback":fallback,
          "boundary":bool(best["boundary"]) if best else False,"seconds":time.perf_counter()-start,
          "score":float(best["score"]) if best else None,"nfev":sum(r["nfev"] for r in results)}
