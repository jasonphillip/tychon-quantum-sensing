"""Run frozen calibration/shot-budget sweep and export exact board replay vectors."""
import argparse
import ctypes
import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from nv_model import (ROOT, config, probabilities, probability_features,
                      count_features, quantize, integer_match, golden_minimize)
from nv_stress import (NUISANCE_KEYS, choose_nuisance, stress_probabilities,
                       stress_counts, profiled_scores)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def error_summary(prediction,truth,groups,bootstrap_rng,draws):
    err = np.abs(np.asarray(prediction)-truth)*1e6
    unique = np.unique(groups)
    group_mae = np.array([err[groups==k].mean() for k in unique])
    sample = bootstrap_rng.choice(group_mae,size=(draws,len(unique)),replace=True).mean(axis=1)
    return {"mae_hz":float(err.mean()),"p95_absolute_error_hz":float(np.quantile(err,.95)),
            "max_absolute_error_hz":float(err.max()),
            "fraction_over_25khz":float(np.mean(err>25000)),
            "mae_cluster_bootstrap_95_hz":np.quantile(sample,[.025,.975]).tolist()}


def boundary_vectors(templates):
    cases = [
        ("zeros",np.zeros(128,dtype=np.int16)),
        ("signed_max",np.full(128,32767,dtype=np.int16)),
        ("signed_min",np.full(128,-32768,dtype=np.int16)),
        ("alternating_extremes",np.tile(np.array([-32768,32767],dtype=np.int16),64)),
        ("ones",np.ones(128,dtype=np.int16)),
        ("minus_ones",np.full(128,-1,dtype=np.int16)),
        ("ramp",np.linspace(-32768,32767,128).astype(np.int16)),
        ("reverse_ramp",np.linspace(32767,-32768,128).astype(np.int16)),
        ("template_0",templates[0].copy()),
        ("template_60",templates[60].copy()),
        ("template_120",templates[120].copy())]
    positive,negative = np.zeros(128,dtype=np.int16),np.zeros(128,dtype=np.int16)
    positive[0] = 32767
    negative[127] = -32768
    return cases+[("positive_impulse",positive),("negative_impulse",negative)]


def c_function(output):
    compiler = shutil.which("clang") or shutil.which("cc")
    if compiler is None:
        raise RuntimeError("C compiler required for board export")
    libpath = output/"nv_match_host.so"
    command = [compiler,"-std=c99","-O2","-Wall","-Wextra","-Werror","-shared","-fPIC",str(ROOT/"nv_match.c"),"-o",str(libpath)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    lib = ctypes.CDLL(str(libpath))
    ptr = ctypes.POINTER(ctypes.c_int16)
    lib.nv_match.argtypes = [ptr,ptr,ctypes.POINTER(ctypes.c_uint64)]
    lib.nv_match.restype = ctypes.c_uint16
    def call(q,bank):
        result = ctypes.c_uint64()
        index = lib.nv_match(q.ctypes.data_as(ptr),bank.ctypes.data_as(ptr),ctypes.byref(result))
        return int(index),int(result.value)
    return call,command


def run(output):
    started = time.perf_counter()
    cfg = config()
    stress_path = ROOT/"stress_config_v2.json"
    stress = json.loads(stress_path.read_text())
    original = ROOT/"artifacts"/"cpu_frozen_v1"
    assert sha(ROOT/"config.json")==stress["base_config_sha256"]
    assert sha(ROOT/"nv_match.c")==stress["fixed_core_sha256"]
    assert sha(original/"templates_i16le.bin")==stress["fixed_rom_sha256"]
    output.mkdir(parents=True,exist_ok=False)
    dump(output/"frozen_config.json",stress)
    base_bank = np.load(original/"templates.npz")
    templates = base_bank["features"].copy()
    qtemplates = np.ascontiguousarray(base_bank["quantized"],dtype=np.int16)
    grid = base_bank["detuning_mhz"].copy()
    assert qtemplates.shape==(121,128)
    n = stress["configurations"]
    true_frequency = np.random.default_rng(stress["parameter_seed"]).uniform(*stress["detuning_range_mhz"],n)
    group_split = np.array([0]*stress["development_configurations"]+[1]*stress["final_configurations"],dtype=np.int8)
    group_split = np.random.default_rng(stress["split_seed"]).permutation(group_split)
    stress_rng = np.random.default_rng(stress["stress_seed"])
    nuisance_values = [{key:float(stress_rng.uniform(*stress["ranges"][key])) for key in NUISANCE_KEYS} for _ in range(n)]
    t = np.linspace(0,cfg["maximum_delay_us"],cfg["delay_points"])
    phases = cfg["phases_rad"]
    probabilities_all = np.empty((len(stress["scenarios"]),n,4,64))
    nuisance_arrays = np.empty((len(stress["scenarios"]),n,len(NUISANCE_KEYS)))
    counts_all,features_all,metadata = [],[],[]
    for scenario_id,scenario in enumerate(stress["scenarios"]):
        for group in range(n):
            nuisance = choose_nuisance(scenario,nuisance_values[group])
            nuisance_arrays[scenario_id,group] = [nuisance[k] for k in NUISANCE_KEYS]
            probabilities_all[scenario_id,group] = stress_probabilities(true_frequency[group],t,phases,cfg["model"],nuisance)
            for budget_id,repetitions in enumerate(stress["repetitions"]):
                row_cfg = {**cfg,"repetitions":repetitions}
                for realization in range(stress["realizations"]):
                    seed = np.random.SeedSequence([stress["noise_seed"],scenario_id,group,budget_id,realization])
                    counts = stress_counts(probabilities_all[scenario_id,group],repetitions,nuisance,np.random.default_rng(seed))
                    counts_all.append(counts)
                    features_all.append(count_features(counts,row_cfg))
                    metadata.append((scenario_id,group,budget_id,realization,group_split[group]))
    counts_all = np.asarray(counts_all,dtype=np.int32)
    features_all = np.asarray(features_all,dtype=np.float64)
    metadata = np.asarray(metadata,dtype=np.int32)
    if not np.all(np.isfinite(features_all)):
        raise ArithmeticError("nonfinite generated features")
    np.savez_compressed(output/"synthetic_stress_data.npz",counts=counts_all,features=features_all,
                        probabilities=probabilities_all,metadata=metadata,detuning_mhz=true_frequency,
                        configuration_split=group_split,nuisance_truth=nuisance_arrays,
                        nuisance_keys=np.array(NUISANCE_KEYS),delays_us=t,phases_rad=np.asarray(phases))
    final_ids = np.flatnonzero(metadata[:,4]==1)
    predict = {k:[] for k in ["fixed_grid","nominal_grid","nominal_refined","profiled_refined"]}
    fixed_indices,fixed_scores,qinputs,clip_values = [],[],[],[]
    start_fit = time.perf_counter()
    for sample_id in final_ids:
        x = features_all[sample_id]
        coarse = int(np.argmin(np.sum((templates-x)**2,axis=1)))
        nominal_objective = lambda f:float(np.sum((probability_features(probabilities(f,t,phases,cfg["model"]))-x)**2))
        nominal = golden_minimize(nominal_objective,grid[max(0,coarse-1)],grid[min(120,coarse+1)],stress["fit"]["golden_iterations"])
        profiled_idx = int(np.argmin(profiled_scores(x,templates,stress["fit"]["profile_gain_bounds"])))
        profile_objective = lambda f:float(profiled_scores(x,probability_features(probabilities(f,t,phases,cfg["model"])),stress["fit"]["profile_gain_bounds"])[0])
        profiled = golden_minimize(profile_objective,grid[max(0,profiled_idx-1)],grid[min(120,profiled_idx+1)],stress["fit"]["golden_iterations"])
        q,clipped = quantize(x,cfg["fractional_bits"])
        idx,score = integer_match(q,qtemplates)
        predict["fixed_grid"].append(grid[idx])
        predict["nominal_grid"].append(grid[coarse])
        predict["nominal_refined"].append(nominal)
        predict["profiled_refined"].append(profiled)
        fixed_indices.append(idx); fixed_scores.append(score); qinputs.append(q); clip_values.append(clipped)
    fit_seconds = time.perf_counter()-start_fit
    predict = {k:np.asarray(v) for k,v in predict.items()}
    qinputs = np.asarray(qinputs,dtype=np.int16)
    clip_values = np.asarray(clip_values,dtype=np.int32)
    np.savez_compressed(output/"final_predictions.npz",sample_id=final_ids,metadata=metadata[final_ids],
                        fixed_index=np.asarray(fixed_indices,dtype=np.uint16),fixed_score=np.asarray(fixed_scores,dtype=np.uint64),
                        clipped_values=clip_values,quantized_inputs=qinputs,**predict)
    constant = float(true_frequency[group_split==0].mean())
    bootstrap_rng = np.random.default_rng(stress["bootstrap_seed"])
    rows = []
    for scenario_id,scenario in enumerate(stress["scenarios"]):
        for budget_id,repetitions in enumerate(stress["repetitions"]):
            selected = (metadata[final_ids,0]==scenario_id)&(metadata[final_ids,2]==budget_id)
            groups = metadata[final_ids,1][selected]
            truth = true_frequency[groups]
            row = {"scenario":scenario,"repetitions_per_phase_delay":repetitions,
                   "total_repetitions":repetitions*4*64,
                   "modeled_acquisition_seconds":float(repetitions*4*np.sum(t+2/(4*cfg["model"]["rabi_mhz"])+stress["timing"]["optical_and_relaxation_us"])*1e-6),
                   "physical_configurations":len(np.unique(groups)),"readouts":int(selected.sum()),
                   "clipped_readouts":int(np.count_nonzero(clip_values[selected])),
                   "clipped_values":int(clip_values[selected].sum()),
                   "fixed_float_grid_agreement":float(np.mean(predict["fixed_grid"][selected]==predict["nominal_grid"][selected]))}
            for key,value in predict.items():
                row[key]=error_summary(value[selected],truth,groups,bootstrap_rng,stress["bootstrap_draws"])
            row["development_constant"]=error_summary(np.full(len(truth),constant),truth,groups,bootstrap_rng,stress["bootstrap_draws"])
            rows.append(row)
    board = output/"board_vectors"
    board.mkdir()
    vectors = [x for x in qinputs]
    ids = []
    for idx,sample_id in enumerate(final_ids):
        scenario_id,group,budget_id,realization,_ = metadata[sample_id]
        ids.append({"case_id":f"v2/{stress['scenarios'][scenario_id]}/r{stress['repetitions'][budget_id]}/cfg{group}/rep{realization}",
                    "sample_id":int(sample_id),"configuration_id":int(group),"clipped_values":int(clip_values[idx]),"kind":"synthetic_final"})
    for label,q in boundary_vectors(qtemplates):
        vectors.append(q)
        ids.append({"case_id":"abi/"+label,"sample_id":None,"configuration_id":None,"clipped_values":None,"kind":"abi_boundary"})
    board_inputs = np.ascontiguousarray(vectors,dtype=np.int16)
    expected = [integer_match(q,qtemplates) for q in board_inputs]
    c_call,compile_command = c_function(output)
    for i,(q,expected_pair) in enumerate(zip(board_inputs,expected)):
        actual = c_call(q,qtemplates)
        if actual != expected_pair:
            raise AssertionError(f"C mismatch case {ids[i]['case_id']}: {actual} != {expected_pair}")
    board_inputs.astype("<i2").tofile(board/"inputs_i16.bin")
    np.array([a[0] for a in expected],dtype="<u2").tofile(board/"expected_indices_u16.bin")
    np.array([a[1] for a in expected],dtype="<u8").tofile(board/"expected_scores_u64.bin")
    manifest = {"schema":"nv_board_replay_v2","evidence":"synthetic inputs and host integer reference; no board execution",
                "count":len(expected),"synthetic_final_count":len(final_ids),"boundary_count":len(expected)-len(final_ids),
                "abi":{"input_shape":[len(expected),128],"input_dtype":"int16","input_endianness":"little",
                       "ordering":"quadrature-major: 64 I then 64 Q","fractional_bits":14,
                       "expected_index_dtype":"uint16 little-endian","expected_score_dtype":"uint64 little-endian",
                       "score_word_order":"when using 32-bit MMIO, low 32 bits followed by high 32 bits; runner must map actual ports",
                       "template_count":121,"template_bytes":30976,"tie_break":"lowest template index",
                       "detuning_hz":"-750000 + 12500*index","preprocessing":"shot count known; photon contrast fixed nominal0.14; saturation flagged"},
                "core_sha256":sha(ROOT/"nv_match.c"),"rom_sha256":sha(original/"templates_i16le.bin"),
                "stress_config_sha256":sha(stress_path),"host_c_parity":{"passed":len(expected),"total":len(expected),"compile_command":compile_command},
                "files":{p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in board.iterdir() if p.is_file()},
                "cases":ids}
    dump(board/"manifest.json",manifest)
    by_cell={(row["scenario"],row["repetitions_per_phase_delay"]):row for row in rows}
    matched500=by_cell[("matched",500)]
    combined2000=by_cell[("combined_mismatch",2000)]
    gates={"c_integer_parity":True,
           "matched_500_fixed_mae":matched500["fixed_grid"]["mae_hz"]<=stress["gates"]["matched_500_mae_hz"],
           "combined_2000_fixed_mae":combined2000["fixed_grid"]["mae_hz"]<=stress["gates"]["combined_2000_mae_hz"],
           "all_cells_fixed_float_grid_agreement":all(r["fixed_float_grid_agreement"]>=stress["gates"]["nominal_float_grid_agreement"] for r in rows)}
    metrics={"schema":stress["schema"],"status":"completed","synthetic_only":True,"final_split_consumed":True,
             "config_sha256":sha(stress_path),"samples":len(metadata),"physical_configurations":n,
             "final_readouts":len(final_ids),"final_physical_configurations":stress["final_configurations"],
             "final_cells":rows,"gates":gates,"board_replay_vectors":len(expected),"fit_seconds":fit_seconds,
             "wall_seconds":time.perf_counter()-started,"python":sys.version,"numpy":np.__version__,"platform":platform.platform(),
             "source_sha256":{p.name:sha(p) for p in [ROOT/"nv_stress.py",ROOT/"run_stress_v2.py",ROOT/"nv_model.py",ROOT/"nv_match.c"]},
             "artifact_sha256":{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.suffix!=".so"},
             "limitations":["No measured sensor or apparatus timing", "Unknown nuisance values do not enter estimators",
                            "V1 core and ROM unchanged", "Final data are consumed; no retuning allowed",
                            "Confidence intervals cluster paired readouts by configuration, not total sample count",
                            "Higher shot counts do not repair model mismatch", "Board replay requires independent coordinator execution"]}
    dump(output/"metrics.json",metrics)
    assert sha(ROOT/"nv_match.c")==stress["fixed_core_sha256"]
    assert sha(original/"templates_i16le.bin")==stress["fixed_rom_sha256"]
    print(json.dumps({"status":"completed","output":str(output),"samples":len(metadata),
                     "board_vectors":len(expected),"gates":gates,"wall_seconds":metrics["wall_seconds"],
                     "cells":[{"scenario":r["scenario"],"repetitions":r["repetitions_per_phase_delay"],
                               "fixed_mae_hz":r["fixed_grid"]["mae_hz"],"nominal_refined_mae_hz":r["nominal_refined"]["mae_hz"],
                               "profiled_mae_hz":r["profiled_refined"]["mae_hz"],"clipped_readouts":r["clipped_readouts"],
                               "grid_agreement":r["fixed_float_grid_agreement"]} for r in rows]},indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    run(args.output.resolve())
