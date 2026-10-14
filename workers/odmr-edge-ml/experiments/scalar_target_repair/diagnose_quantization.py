#!/usr/bin/env python3
"""Post-hoc arithmetic on saved predictions; never opens spectra or a model."""
import argparse
import json
from pathlib import Path
import numpy as np

p=argparse.ArgumentParser()
p.add_argument("--evaluation",type=Path,required=True)
p.add_argument("--out",type=Path,required=True)
args=p.parse_args()
result={"scope":"Post-hoc saved-prediction calculation. No new inference, test-data read, calibration, or model selection.","cohorts":{}}
for cohort in ["original_test_seen","fresh_synthetic_holdout"]:
    report=json.loads((args.evaluation/(cohort+"_metrics.json")).read_text())
    rows=[]
    with np.load(args.evaluation/(cohort+"_predictions.npz"),allow_pickle=False) as a:
        truth,pid=a["truth"],a["pid"]
        for seed in [42,20261014,20261015]:
            name=f"B_full_residual_seed{seed}"
            f,q=a[name+"__fp32"],a[name+"__int8"]
            quant=report["models"][name+"__int8"]["quantization"]
            scale,zp=quant["output_scale"],quant["output_zero_point"]
            low,high=(-128-zp)*scale,(127-zp)*scale
            delta=f-pid
            range_only=pid+np.clip(delta,low,high)
            fm,rm,qm=[float(np.mean(np.abs(v-truth))) for v in [f,range_only,q]]
            rows.append({"seed":seed,"output_min_uT":low,"output_max_uT":high,
                "float_correction_min_uT":float(delta.min()),"float_correction_max_uT":float(delta.max()),
                "fraction_float_below_int8_min":float(np.mean(delta<low)),
                "fraction_float_above_int8_max":float(np.mean(delta>high)),
                "float_mae_uT":fm,"range_clipped_float_mae_uT":rm,"int8_mae_uT":qm,
                "range_only_mae_increase_uT":rm-fm,"actual_int8_mae_increase_uT":qm-fm,
                "range_only_fraction_of_mae_increase":(rm-fm)/(qm-fm),
                "mean_abs_int8_vs_range_clipped_float_uT":float(np.mean(np.abs(q-range_only)))})
    result["cohorts"][cohort]=rows
args.out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
