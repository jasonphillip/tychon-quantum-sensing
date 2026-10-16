"""Prospective development metrics and timing. No confirmation or adoption."""
import math
import numpy as np
METHODS=("lm","affine1","affine3","affine5","neural1")
BATCHES=(1,64,4096)
REPEATS=3

def metrics(parameters,truth,accepted,fallback):
    error=np.linalg.norm(np.asarray(parameters)[:,:3]-np.asarray(truth)[:,:3],axis=1)
    return {"n":len(error),"mean_uT":float(error.mean()),"p95_uT":float(np.quantile(error,.95)),
        "rmse_uT":float(np.sqrt(np.mean(error**2))),"max_uT":float(error.max()),
        "rejections":int((~np.asarray(accepted,dtype=bool)).sum()),"fallbacks":int(np.asarray(fallback,dtype=bool).sum())}

def opportunity_gate(all_metrics,timings,setup_seconds,method_setup=None):
    method_setup={} if method_setup is None else method_setup
    full=all_metrics["lm"]
    classical=[m for m in METHODS[:-1] if all_metrics[m]["mean_uT"]<=1.05*full["mean_uT"]
        and all_metrics[m]["p95_uT"]<=1.05*full["p95_uT"] and all_metrics[m]["rejections"]<=full["rejections"]]
    n=all_metrics["neural1"]
    accuracy=(n["mean_uT"]<=1.05*min(all_metrics[m]["mean_uT"] for m in classical)
        and n["p95_uT"]<=1.05*min(all_metrics[m]["p95_uT"] for m in classical)
        and n["rejections"]<=min(all_metrics[m]["rejections"] for m in classical))
    comparisons={}
    for batch in BATCHES:
        median=lambda m:float(np.median(timings[m][str(batch)]["host_to_host_seconds"]))
        best=min(classical,key=lambda m:(median(m),METHODS.index(m)))
        base,learned=median(best),median("neural1");saving=(base-learned)/batch
        comparisons[str(batch)]={"fastest_adequate_classical":best,"classical_seconds":base,
            "neural_seconds":learned,"speedup":base/learned,"seconds_saved_per_million":saving*1000000,
            "break_even_spectra":math.ceil(setup_seconds/saving) if saving>0 else None}
    passed=accuracy and comparisons["4096"]["speedup"]>=2 and comparisons["4096"]["break_even_spectra"] is not None
    timing4096=lambda m:float(np.median(timings[m]["4096"]["host_to_host_seconds"]))
    fastest=min(timing4096(m) for m in classical)
    steps={"affine1":1,"affine3":3,"affine5":5,"lm":120}
    selected=min((m for m in classical if timing4096(m)<=1.05*fastest),key=lambda m:(steps[m],m))
    classic_saving=(timing4096("lm")-timing4096(selected))/4096
    classical_opportunity={"selected":selected,"selection":"4096 host timing; within5percent tie favors fewer steps",
        "speedup_vs_full_lm":timing4096("lm")/timing4096(selected),
        "provisional_vs_full_lm":selected!="lm" and timing4096("lm")>=2*timing4096(selected),
        "seconds_saved_per_million":classic_saving*1000000,
        "calibration_setup_seconds":method_setup.get(selected,0.),
        "break_even_spectra_conservative_calibration":math.ceil(method_setup.get(selected,0.)/classic_saving) if classic_saving>0 else None,
        "adequate_tied_line_comparison":"PENDING_REQUIRED","engineering_opportunity_pass":None,
        "neural_win":False,"algorithmic_novelty_claim":False}
    return {"adequate_classical":classical,"classical_engineering_opportunity":classical_opportunity,"matched_accuracy_pass":accuracy,"comparisons":comparisons,
        "continuation_pass":passed,"scope":"synthetic computational development only",
        "practical_adoption":False,"confirmation_authorized":False,"tied12_comparator_pending":True}
