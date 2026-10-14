#!/usr/bin/env python3
"""Independently recompute saved prediction summaries and write the handoff."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--evaluation",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    freeze=json.loads((args.run/"FROZEN_CHOICES.json").read_text())
    receipt=json.loads((args.evaluation/"evaluation_receipt.json").read_text())
    exports=json.loads((args.evaluation/"exports.json").read_text())
    assert digest(args.run/"FROZEN_CHOICES.json")==receipt["frozen_choices_sha256"]
    assert receipt["status"]=="complete"
    results={}
    count=0
    for cohort in ["original_test_seen","fresh_synthetic_holdout"]:
        report=json.loads((args.evaluation/(cohort+"_metrics.json")).read_text())
        predfile=args.evaluation/(cohort+"_predictions.npz")
        assert digest(predfile)==report["prediction_file_sha256"]
        with np.load(predfile,allow_pickle=False) as a:
            truth=a["truth"]
            pid=a["pid"]
            for name,row in report["models"].items():
                raw=a[name]
                bounded=pid+np.maximum(-2.25,np.minimum(2.25,raw-pid))
                np.testing.assert_array_equal(bounded,a[name+"__bounded"])
                for label,pred in [("raw",raw),("bounded_correction",bounded)]:
                    difference=pred-truth
                    abs_error=np.abs(difference)
                    recomputed={"mae_uT":np.mean(abs_error),"rmse_uT":np.sqrt(np.mean(difference*difference)),
                        "median_abs_uT":np.median(abs_error),"p90_abs_uT":np.percentile(abs_error,90),"bias_uT":np.mean(difference)}
                    for k,value in recomputed.items():
                        np.testing.assert_allclose(value,row[label][k],rtol=0,atol=1e-12)
                        count+=1
            for name,row in report["baselines"].items():
                np.testing.assert_allclose(np.mean(np.abs(a[name]-truth)),row["mae_uT"],rtol=0,atol=1e-12)
                count+=1
            for precision in ["fp32","int8"]:
                errors={}
                for arm in ["A_clipped","B_full_residual","C_direct"]:
                    errors[arm]=np.mean([np.abs(a[f"{arm}_seed{s}__{precision}"]-truth) for s in [42,20261014,20261015]],axis=0)
                    np.testing.assert_allclose(errors[arm].mean(),report["arm_summary"][arm+"__"+precision]["mean_seed_mae_uT"],rtol=0,atol=1e-12)
                    count+=1
                constant=np.abs(a["training_mean"]-truth)
                differences={"B_minus_A":errors["B_full_residual"]-errors["A_clipped"],
                    "B_minus_training_mean":errors["B_full_residual"]-constant,
                    "C_minus_B":errors["C_direct"]-errors["B_full_residual"],
                    "C_minus_training_mean":errors["C_direct"]-constant}
                for key,difference in differences.items():
                    rng=np.random.default_rng(20261014)
                    draws=np.empty(10000)
                    for offset in range(0,10000,100):
                        indices=rng.integers(0,len(difference),size=(100,len(difference)))
                        draws[offset:offset+100]=difference[indices].mean(axis=1)
                    ci=np.percentile(draws,[2.5,97.5])
                    recorded=report["paired_comparisons_"+precision][key]
                    np.testing.assert_allclose(ci,recorded["ci95_uT"],rtol=0,atol=1e-12)
                    np.testing.assert_allclose(difference.mean(),recorded["mean_difference_uT"],rtol=0,atol=1e-12)
                    count+=3
        results[cohort]=report
    audit={"status":"pass","numeric_values_recomputed":count,"saved_prediction_files_verified":2,
        "freeze_hash_verified":True,"holdout_reopened":False,"all_reload_max_abs_differences":
        [r["reload_prediction_max_abs_difference"] for r in freeze["choices"]]}
    (args.out/"independent-recomputation.json").write_text(json.dumps(audit,indent=2)+"\n")
    fresh=results["fresh_synthetic_holdout"]
    original=results["original_test_seen"]
    def score(r,arm,precision="fp32"):
        return r["arm_summary"][arm+"__"+precision]["mean_seed_mae_uT"]
    bsuccess=all(fresh["paired_comparisons_fp32"][k]["ci95_uT"][1]<0 for k in ["B_minus_A","B_minus_training_mean"])
    csuccess=all(fresh["paired_comparisons_fp32"][k]["ci95_uT"][1]<0 for k in ["C_minus_B","C_minus_training_mean"])
    lines=["# Scalar training-target repair: synthetic results", "", "Date: 2026-10-14.", "",
        f"The predeclared full-residual success criterion {'passed' if bsuccess else 'did not pass'}.",
        f"The secondary direct-regression criterion {'passed' if csuccess else 'did not pass'}.", "",
        "All models were frozen before model evaluation on the fresh 5,000-row synthetic holdout.",
        "The coordinator exposed the holdout PID baseline and label summary before the freeze. No model scores were exposed.",
        "The original 5,000-row test results are exploratory because that split was already used.", "",
        "## Total-field mean absolute error", "",
        "Lower is better. New model rows average the same three fixed training seeds.", "",
        "| Estimator | Fresh holdout, µT | Original seen test, µT |", "|---|---:|---:|"]
    def row(name,f,o):
        lines.append(f"| {name} | {f:.6f} | {o:.6f} |")
    for name in ["PID","training_mean","training_median"]:
        row(name,fresh["baselines"][name]["mae_uT"],original["baselines"][name]["mae_uT"])
    row("Deployed INT8, runtime clamp",fresh["models"]["deployed__int8"]["bounded_correction"]["mae_uT"],original["models"]["deployed__int8"]["bounded_correction"]["mae_uT"])
    row("Deployed FP32, runtime clamp",fresh["models"]["deployed__fp32"]["bounded_correction"]["mae_uT"],original["models"]["deployed__fp32"]["bounded_correction"]["mae_uT"])
    for arm,label in [("A_clipped","A: clipped targets"),("B_full_residual","B: full residual targets"),("C_direct","C: direct magnitude")]:
        row(label+", FP32",score(fresh,arm),score(original,arm))
        row(label+", INT8 CPU",score(fresh,arm,"int8"),score(original,arm,"int8"))
    lines += ["", "## Paired differences on the fresh holdout", "",
        "Negative values favor the first named model. Intervals resample rows, not training seeds or real sensors.", "",
        "| Comparison | Mean difference, µT | Paired 95% interval, µT |", "|---|---:|---:|"]
    for name,record in fresh["paired_comparisons_fp32"].items():
        lo,hi=record["ci95_uT"]
        lines.append(f"| {name} | {record['mean_difference_uT']:.6f} | [{lo:.6f}, {hi:.6f}] |")
    lines += ["", "## What retaining the runtime limit does", "",
        "These rows apply PID + clip(predicted field - PID, +/-2.25 µT).",
        "For C, this is a hypothetical bounded correction derived from its direct estimate.", "",
        "| Arm | FP32 bounded-correction MAE, µT | INT8 bounded-correction MAE, µT |", "|---|---:|---:|"]
    for arm in ["A_clipped","B_full_residual","C_direct"]:
        lines.append(f"| {arm} | {fresh['arm_summary'][arm+'__fp32']['mean_seed_bounded_mae_uT']:.6f} | {fresh['arm_summary'][arm+'__int8']['mean_seed_bounded_mae_uT']:.6f} |")
    lines += ["", "## Checkpoints, seed variation, and conversion", "",
        "The matched control shares the new training settings; it is not an exact historical replay.",
        "Every fit used 100 epochs, the same batches per seed, canonical QAT, and FP32 arithmetic.",
        "Checkpoint selection used only original validation total-field MAE.",
        "Every saved clean checkpoint reproduced its validation predictions exactly after reload.", "",
        "| Model | Selected epoch | Validation MAE, µT | Fresh FP32 MAE, µT | Fresh INT8 MAE, µT | Keras/Torch max gap, µT |", "|---|---:|---:|---:|---:|---:|"]
    export_map={r["name"]:r for r in exports}
    for r in freeze["choices"]:
        name=f"{r['arm']}_seed{r['seed']}"
        lines.append(f"| {name} | {r['selected_epoch']} | {r['val_mae_uT']:.6f} | {fresh['models'][name+'__fp32']['raw']['mae_uT']:.6f} | {fresh['models'][name+'__int8']['raw']['mae_uT']:.6f} | {export_map[name]['keras_vs_torch_max_abs_uT']:.9f} |")
    lines += ["", "## INT8 output encoding", "",
        "Endpoint occupancy is a saturation indicator; it does not prove that every endpoint value was clipped.", "",
        "| Model | Output step, µT | Representable output range, µT | Endpoint occupancy on fresh holdout |",
        "|---|---:|---:|---:|"]
    for name,row in fresh["models"].items():
        if "quantization" not in row:
            continue
        q=row["quantization"]
        scale,zp=q["output_scale"],q["output_zero_point"]
        lines.append(f"| {name} | {scale:.6f} | [{(-128-zp)*scale:.3f}, {(127-zp)*scale:.3f}] | {100*q['output_saturation_fraction']:.3f}% |")
    lines += ["", "## Limits and handoff", "",
        "- Results use the existing simulator and distribution. They do not establish real-sensor accuracy.",
        "- The new estimates use broad output ranges. The current controller still has its original limit.",
        "- No deployed checkpoint, INT8 artifact, controller setting, or kit image changed.",
        "- INT8 inference was tested on CPU. No new VectorBlox compile or hardware run occurred.",
        "- Training seed 20261015 and the holdout master seed share a number, but use separate RNG streams.",
        "- Fresh sample seeds have zero overlap with all original train, validation, and test sample seeds.",
        f"- Training wall time: {freeze['training_wall_seconds']/60:.2f} minutes.",
        f"- Conversion and evaluation time: {receipt['evaluation_seconds']/60:.2f} minutes.",
        f"- Independent saved-prediction recomputation checked {count} numeric values and both file hashes.",
        "- Integration and public release belong to the coordinating session.", ""]
    (args.out/"REPORT.md").write_text("\n".join(lines))
    (args.out/"RESULTS.json").write_text(json.dumps({"full_residual_success":bsuccess,"direct_regression_success":csuccess,
        "fresh_holdout":fresh,"original_seen_test":original,"verification":audit,"evaluation_receipt":receipt},indent=2)+"\n")
    print(json.dumps({"report":str(args.out/"REPORT.md"),"full_residual_success":bsuccess,"direct_regression_success":csuccess,"values_verified":count}))


if __name__=="__main__":
    main()
