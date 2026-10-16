"""Finite synthetic challenge gate; never a practical adoption decision."""
import math
import numpy as np
from .methods import METHODS,CLASSICAL,NEURAL
from experiments.vector_initializer_development.evaluation import metrics

def decide(stats,timings,setup):
    full=stats["lm"]
    adequate=[n for n in CLASSICAL if all(stats[n][k]<=1.05*full[k] for k in ("mean_uT","p95_uT")) and stats[n]["rejections"]<=full["rejections"]]
    median=lambda n:float(np.median(timings[n]["host_to_host_seconds"]))
    best=min(adequate,key=lambda n:(median(n),CLASSICAL.index(n)))
    routes={}
    for name in NEURAL:
        accuracy=all(stats[name][k]<=1.05*min(stats[n][k] for n in adequate) for k in ("mean_uT","p95_uT")) and stats[name]["rejections"]<=min(stats[n]["rejections"] for n in adequate)
        saving=(median(best)-median(name))/4096
        # Count full original training/data cost again, conservatively, not only loading.
        cost=setup["original_p1_candidate_setup_seconds"]+setup["method_setup_seconds"][name]
        routes[name]={"matched_accuracy_pass":accuracy,"speedup":median(best)/median(name),
            "host_seconds":median(name),"seconds_per_million":median(name)/4096*1e6,
            "seconds_saved_per_million":saving*1e6,"setup_cost_seconds":cost,
            "break_even_spectra":math.ceil(cost/saving) if saving>0 else None,
            "continuation_pass":accuracy and median(best)/median(name)>=2 and saving>0}
    return {"adequate_classical":adequate,"fastest_adequate_classical":best,
        "classical_host_seconds":median(best),"classical_seconds_per_million":median(best)/4096*1e6,
        "neural_routes":routes,"any_neural_continuation":any(v["continuation_pass"] for v in routes.values()),
        "scope":"fresh synthetic baseline challenge only","practical_adoption":False,"confirmation_authorized":False,
        "selection_rule":"minimum median; exact timing ties use declared classical order; no post-hoc route changes"}
