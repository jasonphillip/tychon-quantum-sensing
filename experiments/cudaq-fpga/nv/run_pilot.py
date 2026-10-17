"""Generate a fresh frozen synthetic dataset and evaluate fixed baselines once."""
import argparse
import ctypes
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from nv_model import (ROOT, config, probabilities, probability_features, sample_counts,
                      count_features, quantize, integer_match, golden_minimize)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stats(estimate, truth):
    err = np.abs(np.asarray(estimate)-truth)*1e6
    return {"mae_hz": float(err.mean()), "p95_absolute_error_hz": float(np.quantile(err,.95)),
            "max_absolute_error_hz": float(err.max())}


def run(output):
    start = time.perf_counter()
    cfg = config()
    output.mkdir(parents=True, exist_ok=False)
    (output/"frozen_config.json").write_text(json.dumps(cfg,indent=2)+"\n")
    t = np.linspace(0,cfg["maximum_delay_us"],cfg["delay_points"])
    phases = cfg["phases_rad"]
    n = cfg["configurations"]
    rng = np.random.default_rng(cfg["parameter_seed"])
    f = rng.uniform(*cfg["detuning_range_mhz"], n)
    group_split = np.repeat(np.arange(3), cfg["configuration_split_counts"])
    group_split = np.random.default_rng(cfg["split_seed"]).permutation(group_split)
    rng = np.random.default_rng(cfg["noise_seed"])
    p_all = np.array([probabilities(x,t,phases,cfg["model"]) for x in f])
    counts, features, group = [], [], []
    for i in range(n):
        for _ in range(cfg["realizations_per_configuration"]):
            c = sample_counts(p_all[i],cfg,rng)
            counts.append(c)
            features.append(count_features(c,cfg))
            group.append(i)
    counts, features, group = np.array(counts), np.array(features), np.array(group)
    split = group_split[group]
    np.savez_compressed(output/"synthetic_data.npz", counts=counts, features=features,
                        probabilities=p_all, configuration_id=group, split=split,
                        configuration_split=group_split, detuning_mhz=f, delays_us=t,
                        phases_rad=np.asarray(phases))
    grid = np.linspace(*cfg["detuning_range_mhz"], cfg["template_count"])
    templates = np.array([probability_features(probabilities(x,t,phases,cfg["model"])) for x in grid])
    qt, template_clip = quantize(templates,cfg["fractional_bits"])
    qt.astype("<i2").tofile(output/"templates_i16le.bin")
    np.savez_compressed(output/"templates.npz", detuning_mhz=grid, features=templates, quantized=qt)
    test_ids = np.flatnonzero(split == 2)
    truth = f[group[test_ids]]
    coarse, refined, fixed, fixed_idx, scores, quantized_inputs = [], [], [], [], [], []
    clip_count = 0
    inference_start = time.perf_counter()
    for sample in test_ids:
        x = features[sample]
        idx = int(np.argmin(np.sum((templates-x)**2,axis=1)))
        coarse.append(grid[idx])
        left, right = grid[max(0,idx-1)], grid[min(len(grid)-1,idx+1)]
        def objective(value):
            pred = probability_features(probabilities(value,t,phases,cfg["model"]))
            return float(np.sum((pred-x)**2))
        refined.append(golden_minimize(objective,left,right))
        q, clipped = quantize(x,cfg["fractional_bits"])
        clip_count += clipped
        qidx, score = integer_match(q,qt)
        fixed.append(grid[qidx]); fixed_idx.append(qidx); scores.append(score); quantized_inputs.append(q)
    inference_seconds = time.perf_counter()-inference_start
    constant = np.mean(f[group_split==0])
    qinputs = np.array(quantized_inputs,dtype=np.int16)
    qinputs.astype("<i2").tofile(output/"test_inputs_i16le.bin")
    np.savez_compressed(output/"test_predictions.npz", sample_id=test_ids, truth_mhz=truth,
                        coarse_mhz=coarse, refined_mhz=refined, fixed_mhz=fixed,
                        fixed_index=fixed_idx, fixed_score=scores)
    compiler = shutil.which("clang") or shutil.which("cc")
    c_result = {"status":"not_run", "reason":"C compiler unavailable"}
    if compiler:
        libpath = output/"nv_match.so"
        command = [compiler,"-std=c99","-O2","-Wall","-Wextra","-Werror","-shared","-fPIC",str(ROOT/"nv_match.c"),"-o",str(libpath)]
        build = subprocess.run(command,capture_output=True,text=True,check=True)
        lib = ctypes.CDLL(str(libpath))
        ptr = ctypes.POINTER(ctypes.c_int16)
        lib.nv_match.argtypes = [ptr,ptr,ctypes.POINTER(ctypes.c_uint64)]
        lib.nv_match.restype = ctypes.c_uint16
        def call(q, bank):
            score = ctypes.c_uint64()
            i = lib.nv_match(q.ctypes.data_as(ptr),bank.ctypes.data_as(ptr),ctypes.byref(score))
            return i,score.value
        matched = sum(call(q,qt)==(i,s) for q,i,s in zip(qinputs,fixed_idx,scores))
        extreme_input = np.full(128,-32768,dtype=np.int16)
        extreme_bank = np.full((121,128),32767,dtype=np.int16)
        edge = call(extreme_input,extreme_bank)
        assert edge == (0,128*65535**2), edge
        assert matched == len(test_ids), matched
        c_result = {"status":"passed","compiler":compiler,"command":command,
                    "matched_cases":matched,"extreme_score":edge[1],"tie_index":edge[0],
                    "stdout":build.stdout,"stderr":build.stderr}
    coarse_stats, refined_stats, fixed_stats = (stats(a,truth) for a in (coarse,refined,fixed))
    agreement = float(np.mean(np.asarray(coarse)==np.asarray(fixed)))
    gates = {"refined_mae":refined_stats["mae_hz"]<=cfg["gates"]["refined_mae_hz"],
             "fixed_extra_mae":fixed_stats["mae_hz"]-refined_stats["mae_hz"]<=cfg["gates"]["fixed_extra_mae_hz"],
             "fixed_grid_agreement":agreement>=cfg["gates"]["fixed_grid_agreement_min"],
             "no_clipping":clip_count==0 and template_clip==0,
             "c_parity":c_result["status"]=="passed"}
    metrics = {"schema":cfg["schema"],"synthetic_only":True,"config_sha256":sha(ROOT/"config.json"),
       "python":sys.version,"numpy":np.__version__,"platform":platform.platform(),
       "samples":len(features),"configuration_counts":cfg["configuration_split_counts"],
       "heldout_samples":len(test_ids),"heldout_configurations":int(np.sum(group_split==2)),
       "float_coarse":coarse_stats,"float_refined":refined_stats,"fixed_grid":fixed_stats,
       "train_constant":stats(np.full(len(truth),constant),truth),"fixed_float_grid_agreement":agreement,
       "input_clipped_values":clip_count,"template_clipped_values":template_clip,
       "template_bytes":int(qt.nbytes),"input_bytes":256,"distance_terms_per_sample":121*128,
       "worst_case_score":128*65535**2,"c_reference":c_result,"gates":gates,
       "combined_baseline_evaluation_seconds":inference_seconds,"total_seconds":time.perf_counter()-start,
       "source_sha256":{p.name:sha(p) for p in [ROOT/"nv_model.py",ROOT/"run_pilot.py",ROOT/"nv_match.c"]},
       "artifact_sha256":{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.suffix!=".so"},
       "limitations":["No live sensor, FPGA execution, synthesis, power, radiation, or GPU performance evidence",
                      "All nuisance parameters known; only detuning varies", "Test split now consumed",
                      "One run timing includes generator, fit and host operations; not a performance study"]}
    (output/"metrics.json").write_text(json.dumps(metrics,indent=2)+"\n")
    print(json.dumps(metrics,indent=2))
    return all(gates.values())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",type=Path,required=True)
    args = ap.parse_args()
    sys.exit(0 if run(args.output.resolve()) else 2)
