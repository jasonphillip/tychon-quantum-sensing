"""Bounded runtime-only profile: never reads labels or evaluates accuracy."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from run_development import preflight,CELLS,dump
from models import records,DirectModels,module,sha
from estimators import GRID,edge_ols,robust_fit,likelihood_magnitude
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--data",type=Path,required=True);p.add_argument("--model-manifest",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True);a=p.parse_args()
 m=preflight(a.data);chosen=records(a.model_manifest)
 if a.out.exists():raise ValueError("profile output already exists")
 a.out.mkdir(parents=True)
 models=DirectModels(HERE.parents[1],chosen)
 pid=module("runtime_pid",HERE.parents[1]/"src/odmr_edge_ml/evaluation/pid_proxy.py").DerivativeZeroCrossingPID(GRID)
 n=0;fit_times=[];grid_times=[];model_times=[];start=time.perf_counter()
 for ci,cell in enumerate(CELLS):
  take=(128-n)//(len(CELLS)-ci);path=a.data/m["cells"][cell]["file"]
  if sha(path)!=m["cells"][cell]["sha256"]:raise ValueError("profile payload hash mismatch")
  with np.load(path,allow_pickle=False) as z:
   np.testing.assert_array_equal(z["frequencies_hz"],GRID)
   spectra=z["spectra"][:take]
  for y in spectra:
   f=robust_fit(y);fit_times.append(f.seconds)
   t=time.perf_counter();likelihood_magnitude(y,f);grid_times.append(time.perf_counter()-t)
   edge=edge_ols(y)[0];joint=y-f.slope_per_MHz*(GRID-2.87e9)/1e6
   t=time.perf_counter()
   for sig,lock in [(y,pid.estimate(y).lock_bin),(edge,pid.estimate(edge).lock_bin),(joint,f.lock_bin)]:
    models.predict(sig[None,:],np.array([lock]))
   model_times.append(time.perf_counter()-t)
  n+=take
 result=dict(scope="runtime only; first development revision has known OU distribution defect",
  labels_opened=False,accuracy_computed=False,spectra=n,manifest_sha256=sha(a.data/"manifest.json"),
  seconds=time.perf_counter()-start,fit_total_s=sum(fit_times),grid_total_s=sum(grid_times),
  all_policies_six_models_total_s=sum(model_times),fit_median_s=float(np.median(fit_times)),
  fit_p95_s=float(np.quantile(fit_times,.95)),
  projected_final_numerical_s=7168*sum(fit_times+grid_times+model_times)/n,
  caveat="projection excludes bootstrap, process setup, final timing, and review")
 dump(a.out/"runtime.json",result);print(json.dumps(result),flush=True)
if __name__=="__main__":main()
