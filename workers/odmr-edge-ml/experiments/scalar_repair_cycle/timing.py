"""Single-thread, batch-one complete pipeline timing on retained input rows."""
import time
import numpy as np
from estimators import GRID,TRAIN_MEDIAN,robust_fit,edge_ols,likelihood_magnitude,checked_fallback
def measure(spectra,models,detector,warmup_spectra,count=16):
    rows=np.asarray(spectra)[:count]
    if not len(rows):raise ValueError("timing requires inputs")
    warmups=np.asarray(warmup_spectra)
    if warmups.shape!=(4,100):raise ValueError("exactly four frozen development warm-up rows required")
    methods=["robust_prior_fit","conditional_likelihood"]+[
        f"{policy}__C_direct_seed{seed}__{precision}"
        for policy in ("edge_ols","joint_fit") for seed in (42,20261014,20261015)
        for precision in ("fp32","int8")]
    def one(label,row):
        fit=robust_fit(row)
        if label=="robust_prior_fit":return fit.prediction_uT
        if label=="conditional_likelihood":return likelihood_magnitude(row,fit)["prediction_uT"]
        policy,name,precision=label.split("__")
        if fit.hard_invalid:return TRAIN_MEDIAN
        if policy=="edge_ols":signal=edge_ols(row)[0];lock=detector.estimate(signal).lock_bin
        else:signal=row-fit.slope_per_MHz*(GRID-2.87e9)/1e6;lock=fit.lock_bin
        raw=models.predict_one(signal,lock,name,precision)
        return float(checked_fallback([raw],[False])[0][0])
    result={}
    for label in methods:
        for row in warmups:one(label,row)
        times=[]
        for row in rows:
            start=time.perf_counter();one(label,row);times.append(time.perf_counter()-start)
        result[label]=dict(median_pipeline_seconds=float(np.median(times)),p95_pipeline_seconds=float(np.quantile(times,.95)),
            n=len(times),warmup=4,warmup_source="frozen development",batch_size=1,threads=1,
            scope="full preprocessing, common quality fit, inference/conversion, and fallback")
    return result
