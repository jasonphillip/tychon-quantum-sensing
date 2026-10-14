#!/usr/bin/env python3
"""One frozen evaluation campaign, with CPU INT8 exports and access receipts."""
from __future__ import annotations
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")

import argparse
import datetime
import json
import stat
import sys
import time
from pathlib import Path
import h5py
import numpy as np
import torch
import run_experiment as exp

EXPECTED_HOLDOUT = {
    "dataset.h5":"45d7a6f9affff9878d6c00b72942332221bdb1deb0bcfe7d425a0092ce800796",
    "pid_residuals.npz":"4f7dc70adb2fdda60cb4450abbe5015bca5172a36226b631d4c0831a698b4505",
    "manifest.json":"94fc5094e903978ebfaf4829cf2e03b5f0b6df27ebb4e3acafbbd21607c5aa9f",
}
ORIGINAL_CHECKPOINT_SHA256 = "e0c314265017a999cd57c2b0c168c2d3dc229c9edbb3c630887ffb94ff57ed0a"
ORIGINAL_TFLITE_SHA256 = "e3b55da96ee633a58109007d4244304e2ad4a22853b10335fa41879e815b5371"


def export_int8(state, calibration, path):
    import tensorflow as tf
    inp=tf.keras.layers.Input(batch_shape=(1,1,100,2),name="odmr_input")
    x=inp
    names=["convs.0","convs.1","convs.2","conv_head"]
    layers=[]
    for i,name in enumerate(names):
        w=state[name+".weight"].cpu().numpy()
        layer=tf.keras.layers.Conv2D(w.shape[0],tuple(w.shape[2:]),strides=(1,1) if i==3 else (1,2),
            activation=None if i==3 else "relu",padding="valid",name="conv_head" if i==3 else f"conv_{i}")
        x=layer(x)
        layers.append(layer)
    model=tf.keras.Model(inputs=inp,outputs=x)
    for layer,name in zip(layers,names):
        w=state[name+".weight"].cpu().numpy().transpose(2,3,1,0)
        layer.set_weights([w,state[name+".bias"].cpu().numpy()])
    converter=tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations=[tf.lite.Optimize.DEFAULT]
    def representative():
        for i in range(len(calibration)):
            yield [calibration[i:i+1].astype(np.float32)]
    converter.representative_dataset=representative
    converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type=tf.int8
    converter.inference_output_type=tf.int8
    path.write_bytes(converter.convert())
    # Compare the floating Keras conversion against the clean PyTorch model later.
    return model


def read_cohort(path):
    with h5py.File(path/"dataset.h5","r") as f, np.load(path/"pid_residuals.npz",allow_pickle=False) as z:
        spectra=f["test/spectra"][:]
        truth=np.linalg.norm(f["test/labels"][:]*1e6,axis=1).astype(np.float64)
        seeds=f["test/seeds"][:]
        frequency=f["test/frequencies"][:]
        pid=z["test_b_pid_uT"].astype(np.float64)
        lock=z["test_lock_bins"]
        np.testing.assert_allclose(truth,z["test_b_mag_uT"],rtol=1e-7,atol=1e-6)
        np.testing.assert_allclose(truth-pid,z["test_delta_b_uT"],rtol=1e-7,atol=1e-6)
    lo,hi=spectra.min(1,keepdims=True),spectra.max(1,keepdims=True)
    norm=2*(spectra-lo)/np.where(hi==lo,1,hi-lo)-1
    x=np.concatenate([norm,lock[:,None]],axis=1).astype(np.float32)
    return dict(spectra=spectra,truth=truth,pid=pid,lock=lock,seeds=seeds,frequency=frequency,x=x)


def bootstrap_differences(error_by_arm, constant_error):
    a,b,c=[error_by_arm[k] for k in exp.ARMS]
    diffs={"B_minus_A":b-a,"B_minus_training_mean":b-constant_error,
           "C_minus_B":c-b,"C_minus_training_mean":c-constant_error}
    names=list(diffs)
    matrix=np.stack([diffs[k] for k in names],axis=1)
    rng=np.random.default_rng(20261014)
    draws=[]
    for _ in range(100):
        idx=rng.integers(0,len(matrix),size=(100,len(matrix)))
        draws.append(matrix[idx].mean(axis=1))
    draws=np.concatenate(draws)
    return {name:{"mean_difference_uT":float(matrix[:,i].mean()),
                   "ci95_uT":[float(v) for v in np.quantile(draws[:,i],[.025,.975])],
                   "resamples":10000,"bootstrap_seed":20261014} for i,name in enumerate(names)}


def summarize_cohort(label, data, candidates, deployed, helpers, config, out):
    truth,pid=data["truth"],data["pid"]
    x=torch.from_numpy(data["x"])
    predictions={"truth":truth,"pid":pid,"sample_seeds":data["seeds"]}
    baseline_preds={"PID":pid,"training_mean":np.full(len(truth),config["train_mean_uT"]),
                    "training_median":np.full(len(truth),config["train_median_uT"])}
    report={"cohort":label,"n":len(truth),"baselines":{k:exp.metrics(v,truth) for k,v in baseline_preds.items()},
            "models":{},"arm_summary":{},"input_hashes":{k:exp.sha_array(data[k]) for k in ["spectra","truth","pid","lock","seeds","frequency"]}}
    for key,pred in baseline_preds.items():
        predictions[key]=pred
    def record(name,pred,quant=None):
        pred=np.asarray(pred,dtype=np.float64)
        bounded=pid+np.clip(pred-pid,-2.25,2.25)
        predictions[name]=pred
        predictions[name+"__bounded"]=bounded
        entry={"raw":exp.metrics(pred,truth),"bounded_correction":exp.metrics(bounded,truth),
               "fraction_correction_exceeds_2p25":float(np.mean(np.abs(pred-pid)>2.25))}
        if quant is not None:
            entry["quantization"]=quant
        report["models"][name]=entry
    for item in candidates:
        name=item["name"]
        output=exp.predict(item["model"],x)
        record(name+"__fp32",exp.field_predictions(item["arm"],output,pid))
        flat=helpers.preprocess(data["spectra"],data["lock"],item["sigma"])
        quant_output,quant=helpers.run_tflite(item["interpreter"],flat)
        record(name+"__int8",exp.field_predictions(item["arm"],quant_output.astype(np.float64),pid),quant)
    flat=helpers.preprocess(data["spectra"],data["lock"],deployed["sigma"])
    float_output=exp.predict(deployed["model"],torch.from_numpy(flat))
    int8_output,quant=helpers.run_tflite(deployed["interpreter"],flat)
    record("deployed__fp32",pid+float_output)
    record("deployed__int8",pid+int8_output.astype(np.float64),quant)
    for precision in ["fp32","int8"]:
        errors={}
        for arm in exp.ARMS:
            names=[f"{arm}_seed{s}__{precision}" for s in exp.SEEDS]
            seed_maes=[report["models"][n]["raw"]["mae_uT"] for n in names]
            errors[arm]=np.mean([np.abs(predictions[n]-truth) for n in names],axis=0)
            report["arm_summary"][arm+"__"+precision]={"mean_seed_mae_uT":float(np.mean(seed_maes)),
                "seed_mae_uT":seed_maes,"seed_sd_uT":float(np.std(seed_maes,ddof=1)),
                "mean_seed_bounded_mae_uT":float(np.mean([report["models"][n]["bounded_correction"]["mae_uT"] for n in names]))}
        # Freeze-defined bootstrap is used on the fresh cohort; original is exploratory.
        report["paired_comparisons_"+precision]=bootstrap_differences(errors,np.abs(baseline_preds["training_mean"]-truth))
    pred_path=out/(label+"_predictions.npz")
    np.savez_compressed(pred_path,**predictions)
    report["prediction_file_sha256"]=exp.sha_file(pred_path)
    exp.dump(out/(label+"_metrics.json"),report)
    print(json.dumps({"event":"COHORT_COMPLETE","cohort":label,"arm_summary":report["arm_summary"],"baselines":{k:v["mae_uT"] for k,v in report["baselines"].items()}}),flush=True)
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--original",type=Path,required=True)
    p.add_argument("--holdout",type=Path,required=True)
    p.add_argument("--deployed-checkpoint",type=Path,required=True)
    p.add_argument("--deployed-tflite",type=Path,required=True)
    p.add_argument("--freeze-sha256",required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    started=time.monotonic()
    freeze_path=args.run/"FROZEN_CHOICES.json"
    if exp.sha_file(freeze_path)!=args.freeze_sha256:
        raise RuntimeError("Frozen choices do not match the hash sent to the coordinator")
    freeze=json.loads(freeze_path.read_text())
    if freeze["status"]!="complete" or freeze["fresh_holdout_accessed"]:
        raise RuntimeError("Invalid freeze state")
    if (args.run/"HOLDOUT_ACCESS.json").exists():
        raise RuntimeError("Fresh holdout already accessed; no repeat campaign")
    config=json.loads((args.run/"run_config.json").read_text())
    assert exp.sha_file(args.run/"run_config.json")==freeze["config_sha256"]
    assert len(freeze["choices"])==9
    if args.out.exists():
        raise RuntimeError("Evaluation directory exists; a second campaign is forbidden")
    args.out.mkdir(parents=True)
    arch,qat,source_hashes=exp.setup(args.repo)
    for name in ["src/odmr_edge_ml/models/fcnn_v2.py","src/odmr_edge_ml/training/qat.py"]:
        assert source_hashes[name]==config["source_hashes"][name]
    helpers=exp.load_module("deployed_equivalence_helpers",args.repo/"experiments/fcnn_v2_int8_float_equivalence.py")
    assert exp.sha_file(args.deployed_checkpoint)==ORIGINAL_CHECKPOINT_SHA256
    assert exp.sha_file(args.deployed_tflite)==ORIGINAL_TFLITE_SHA256
    original_ckpt=torch.load(args.deployed_checkpoint,map_location="cpu",weights_only=True)
    old_state=helpers.strip_compile_qat_keys(original_ckpt["model_state_dict"])
    sigma=float(old_state["sigma"])
    original_model=helpers.OdmrFCNN(input_dim=100,output_dim=1,in_channels=2,init_weights=False)
    original_model.load_state_dict({k:v for k,v in old_state.items() if k in original_model.state_dict()},strict=True)
    original_model.eval()
    deployed={"model":original_model,"sigma":sigma,"interpreter":helpers.load_interpreter(args.deployed_tflite)}

    # All exports use training-only calibration, before any test data is opened.
    with h5py.File(args.original/"dataset.h5","r") as f, np.load(args.original/"pid_residuals.npz",allow_pickle=False) as z:
        cal_spectra=f["train/spectra"][:1000]
        cal_locks=z["train_lock_bins"][:1000]
        all_original_seeds=np.concatenate([f[s]["seeds"][:] for s in ["train","val","test"]])
    export_records=[]
    candidates=[]
    for row in freeze["choices"]:
        ckpt_path=Path(row["checkpoint"])
        assert exp.sha_file(ckpt_path)==row["checkpoint_sha256"]
        ckpt=torch.load(ckpt_path,map_location="cpu",weights_only=True)
        model=exp.clean_model(arch,ckpt["state_dict"],torch.device("cpu"))
        name=f'{row["arm"]}_seed{row["seed"]}'
        sigma=float(ckpt["state_dict"]["sigma"])
        cal_flat=helpers.preprocess(cal_spectra,cal_locks,sigma)
        cal_nhwc=helpers.flat_to_nhwc(cal_flat)
        tflite_path=args.out/(name+".tflite")
        keras_model=export_int8(ckpt["state_dict"],cal_nhwc,tflite_path)
        lo,hi=cal_spectra.min(1,keepdims=True),cal_spectra.max(1,keepdims=True)
        normalized=2*(cal_spectra-lo)/np.where(hi==lo,1,hi-lo)-1
        packed=torch.from_numpy(np.concatenate([normalized,cal_locks[:,None]],axis=1).astype(np.float32))
        pt=exp.predict(model,packed)
        keras_pred=keras_model(cal_nhwc,training=False).numpy().reshape(-1).astype(np.float64)
        max_gap=float(np.max(np.abs(pt-keras_pred)))
        if max_gap>0.001:
            raise RuntimeError(f"Keras export mismatch: {name} {max_gap}")
        interp=helpers.load_interpreter(tflite_path)
        ops=interp._get_ops_details()
        op_names=sorted({v["op_name"] for v in ops})
        allowed={"CONV_2D","RELU","DELEGATE"}
        if set(op_names)-allowed:
            raise RuntimeError(f"Unexpected export operators: {op_names}")
        export_records.append({"name":name,"path":str(tflite_path),"sha256":exp.sha_file(tflite_path),
            "bytes":tflite_path.stat().st_size,"keras_vs_torch_max_abs_uT":max_gap,"operators":op_names,
            "checkpoint_sha256":row["checkpoint_sha256"],"sigma":sigma})
        candidates.append({"name":name,"arm":row["arm"],"sigma":sigma,"model":model,"interpreter":interp})
    exp.dump(args.out/"exports.json",export_records)

    # The immutable freeze stays unchanged. The separate exclusive receipt is the mutable access state.
    access_path=args.run/"HOLDOUT_ACCESS.json"
    if access_path.exists():
        raise RuntimeError("Fresh holdout already accessed; no repeat campaign")
    hashes={name:exp.sha_file(args.holdout/name) for name in EXPECTED_HOLDOUT}
    if hashes!=EXPECTED_HOLDOUT:
        raise RuntimeError("Sealed holdout hash mismatch")
    for name in EXPECTED_HOLDOUT:
        if (args.holdout/name).stat().st_mode & (stat.S_IWUSR|stat.S_IWGRP|stat.S_IWOTH):
            raise RuntimeError("Holdout is not read-only")
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt={"fresh_holdout_accessed":True,"first_read_utc":now,"frozen_choices_sha256":args.freeze_sha256,
        "holdout_hashes":hashes,"evaluation_script_sha256":exp.sha_file(__file__),"status":"in_progress",
        "baseline_peek_disclosed":True,"baseline_peek_scope":"coordinator printed PID MAE and label distribution before model freeze; no model prediction was evaluated"}
    with access_path.open("x") as f:
        json.dump(receipt,f,indent=2)
    fresh=read_cohort(args.holdout)
    original=read_cohort(args.original)
    assert len(fresh["truth"])==5000
    assert not set(fresh["seeds"].tolist()).intersection(all_original_seeds.tolist())
    np.testing.assert_array_equal(fresh["frequency"],original["frequency"])
    summaries={}
    for label,data in [("original_test_seen",original),("fresh_synthetic_holdout",fresh)]:
        summaries[label]=summarize_cohort(label,data,candidates,deployed,helpers,config,args.out)
    receipt["status"]="complete"
    receipt["completed_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt["evaluation_seconds"]=time.monotonic()-started
    exp.dump(access_path,receipt)
    exp.dump(args.out/"evaluation_receipt.json",{**receipt,"deployed_checkpoint_sha256":exp.sha_file(args.deployed_checkpoint),
        "deployed_tflite_sha256":exp.sha_file(args.deployed_tflite),"deployed_sigma":deployed["sigma"],
        "equivalence_helper_sha256":exp.sha_file(args.repo/"experiments/fcnn_v2_int8_float_equivalence.py"),
        "source_hashes":source_hashes,"evaluation_python":sys.version,"torch":torch.__version__,
        "all_original_seed_overlap":0,"row_count":5000,"training_seed_equals_holdout_master_seed_note":"Both contain 20261015, but use separate RNG streams for weights and simulated examples."})
    print(json.dumps({"event":"EVALUATION_COMPLETE","seconds":time.monotonic()-started,"output":str(args.out)}),flush=True)


if __name__=="__main__":
    main()
