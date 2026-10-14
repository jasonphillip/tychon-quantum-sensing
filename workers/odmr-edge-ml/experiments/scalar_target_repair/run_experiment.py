#!/usr/bin/env python3
"""Bounded matched-target experiment; training opens only train and val groups."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import sys
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import h5py
import numpy as np
import torch
from torch import nn

ARMS = ("A_clipped", "B_full_residual", "C_direct")
SEEDS = (42, 20261014, 20261015)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha_array(a):
    a = np.ascontiguousarray(a)
    h = hashlib.sha256()
    h.update(str(a.dtype).encode())
    h.update(str(a.shape).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def state_hash(state):
    h = hashlib.sha256()
    for k, v in sorted(state.items()):
        h.update(k.encode())
        h.update(sha_array(v.detach().cpu().numpy()).encode())
    return h.hexdigest()


def dump(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def targets(arm, truth, pid):
    if arm == "A_clipped":
        return np.clip(truth - pid, -2.25, 2.25)
    if arm == "B_full_residual":
        return truth - pid
    if arm == "C_direct":
        return truth.copy()
    raise ValueError(arm)


def field_predictions(arm, output, pid):
    return output if arm == "C_direct" else pid + output


def metrics(pred, truth):
    e = np.asarray(pred, dtype=np.float64) - np.asarray(truth, dtype=np.float64)
    ae = np.abs(e)
    if not np.isfinite(e).all():
        raise ValueError("Nonfinite predictions")
    bins = {}
    for lo, hi in ((20,30),(30,40),(40,50),(50,60),(60,70.000001)):
        m = (truth >= lo) & (truth < hi)
        bins[f"{lo}-{min(70,hi):g}"] = {"n":int(m.sum()), "mae_uT":float(ae[m].mean()) if m.any() else None}
    return {"n":len(e), "mae_uT":float(ae.mean()), "rmse_uT":float(np.sqrt(np.mean(e**2))),
            "median_abs_uT":float(np.median(ae)), "p90_abs_uT":float(np.quantile(ae,.9)),
            "bias_uT":float(e.mean()), "magnitude_bins":bins}


def setup(repo):
    model_path = repo / "src/odmr_edge_ml/models/fcnn_v2.py"
    qat_path = repo / "src/odmr_edge_ml/training/qat.py"
    arch = load_module("canonical_fcnn_v2", model_path)
    qat = load_module("canonical_qat", qat_path)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    return arch, qat, {str(p.relative_to(repo)):sha_file(p) for p in [model_path,qat_path,
        repo/"experiments/scalar_residual_v2.py",repo/"src/odmr_edge_ml/cascade/train_stage.py"]}


def load_data(data_dir):
    arrays, hashes = {}, {}
    with np.load(data_dir / "pid_residuals.npz", allow_pickle=False) as z, h5py.File(data_dir / "dataset.h5", "r") as f:
        for split in ("train", "val"):
            spectra = f[split]["spectra"][:]
            vector = f[split]["labels"][:]
            truth = np.linalg.norm(vector * 1e6, axis=1).astype(np.float64)
            pid = z[split + "_b_pid_uT"].astype(np.float64)
            lock = z[split + "_lock_bins"]
            delta = z[split + "_delta_b_uT"]
            np.testing.assert_allclose(truth, z[split + "_b_mag_uT"], rtol=1e-7, atol=1e-6)
            np.testing.assert_allclose(delta, truth-pid, rtol=1e-7, atol=1e-6)
            lo, hi = spectra.min(1,keepdims=True), spectra.max(1,keepdims=True)
            normalized = 2*(spectra-lo)/np.where(hi==lo,1,hi-lo)-1
            x = np.concatenate([normalized,lock[:,None]],axis=1).astype(np.float32)
            assert x.shape == (len(truth), 101) and np.isfinite(x).all()
            arrays[split] = {"x":x,"truth":truth,"pid":pid,"lock":lock}
            hashes[split] = {"spectra":sha_array(spectra),"vector_labels":sha_array(vector),
                "pid":sha_array(pid),"lock_bins":sha_array(lock),"model_input":sha_array(x),
                "sample_seeds":sha_array(f[split]["seeds"][:])}
    return arrays, hashes


def initialize(arch, qat, seed, device):
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = arch.OdmrFCNNv2()
    for m in model.modules():
        if isinstance(m,(nn.Linear,nn.Conv2d)):
            nn.init.kaiming_normal_(m.weight,mode="fan_in",nonlinearity="relu")
            if m.bias is not None:
                nn.init.zeros_(m.bias)
    init_hash = state_hash(model.state_dict())
    model = qat.prepare_model_qat(model,example_input=torch.zeros(1,101)).to(device)
    return model, init_hash


def clean_state(qat, model):
    state = {k:v.detach().cpu().clone() for k,v in qat.extract_clean_state_dict(model).items()}
    # FX lifts bins[None, :] into a constant. Restore the canonical buffer name.
    if "bins" not in state and "_tensor_constant0" in state:
        bins = state.pop("_tensor_constant0").reshape(-1)
        torch.testing.assert_close(bins, torch.arange(100,dtype=torch.float32), rtol=0,atol=0)
        state["bins"] = bins
    return state


def clean_model(arch, state, device):
    model = arch.OdmrFCNNv2()
    model.load_state_dict(state,strict=True)
    return model.to(device).eval()


def predict(model, x):
    with torch.inference_mode():
        return torch.cat([model(x[i:i+512]).flatten() for i in range(0,len(x),512)]).cpu().numpy().astype(np.float64)


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize()


def fit(args):
    out = args.out
    out.mkdir(parents=True,exist_ok=True)
    if (out/"run_config.json").exists():
        raise RuntimeError("Run exists; do not overwrite or silently resume")
    start = time.monotonic()
    deadline = start + args.cap_seconds
    arch, qat, source_hashes = setup(args.repo)
    arrays, data_hashes = load_data(args.data)
    device = torch.device(args.device)
    x = {s:torch.from_numpy(a["x"]).to(device) for s,a in arrays.items()}
    criterion = nn.HuberLoss(delta=10.)
    ntrain = len(x["train"])
    nbatches = (ntrain+63)//64

    # Timing only. This model is discarded; no validation is evaluated here.
    pilot, _ = initialize(arch,qat,42,device)
    opt = torch.optim.AdamW(pilot.parameters(),lr=.001,weight_decay=.001)
    y = torch.from_numpy(targets("B_full_residual",arrays["train"]["truth"],arrays["train"]["pid"]).astype(np.float32)).to(device)
    steps = 200
    pilot.train()
    t100 = None
    for k in range(steps):
        if k == 100:
            sync(device)
            t100 = time.monotonic()
        lo = (k*64)%ntrain
        idx = torch.arange(lo,min(lo+64,ntrain),device=device)
        opt.zero_grad(set_to_none=True)
        loss = criterion(pilot(x["train"][idx]).flatten(),y[idx])
        loss.backward()
        nn.utils.clip_grad_norm_(pilot.parameters(),10.)
        opt.step()
    sync(device)
    step_seconds = (time.monotonic()-t100)/100
    del pilot,opt,y
    estimates = {e:step_seconds*nbatches*9*e*1.3 for e in [10,20,40,60,100]}
    eligible = [e for e,t in estimates.items() if t<=3000]
    if not eligible:
        dump(out/"compute_limit.json",{"step_seconds":step_seconds,"estimated_seconds":estimates})
        raise RuntimeError("Ten common epochs exceed the predeclared allowance")
    epochs = max(eligible)
    config = {"arms":ARMS,"seeds":SEEDS,"epochs":epochs,"val_every":max(1,epochs//10),
        "dtype":"FP32", "qat":"canonical symmetric per-tensor INT8 fake quantization",
        "device":str(device),"torch":torch.__version__,"numpy":np.__version__,"python":platform.python_version(),
        "source_hashes":source_hashes,"data_hashes":data_hashes,"runner_sha256":sha_file(__file__),
        "protocol_sha256":sha_file(args.protocol),"pilot_seconds_per_step":step_seconds,
        "estimated_training_seconds":estimates[epochs],"global_cap_seconds":args.cap_seconds,
        "train_mean_uT":float(arrays["train"]["truth"].mean()),"train_median_uT":float(np.median(arrays["train"]["truth"]))}
    dump(out/"run_config.json",config)
    print(json.dumps({"event":"CONFIG_FROZEN","epochs":epochs,"estimated_seconds":estimates[epochs],"device":str(device)}),flush=True)
    selected=[]
    saved_predictions={"truth":arrays["val"]["truth"],"pid":arrays["val"]["pid"]}
    for seed in SEEDS:
        paired_initial_hash = None
        for arm in ARMS:
            name=f"{arm}_seed{seed}"
            run_dir=out/name
            run_dir.mkdir()
            model,init_hash=initialize(arch,qat,seed,device)
            if paired_initial_hash is None:
                paired_initial_hash=init_hash
            assert init_hash==paired_initial_hash
            opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001,betas=(.9,.999))
            sched=torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=epochs,eta_min=1e-5)
            rng=torch.Generator(device="cpu").manual_seed(seed)
            order_hash=hashlib.sha256()
            y=torch.from_numpy(targets(arm,arrays["train"]["truth"],arrays["train"]["pid"]).astype(np.float32)).to(device)
            best=float("inf")
            best_epoch=None
            history=[]
            run_start=time.monotonic()
            for epoch in range(1,epochs+1):
                model.train()
                order_cpu=torch.randperm(ntrain,generator=rng)
                order_hash.update(order_cpu.numpy().tobytes())
                order=order_cpu.to(device)
                loss_sum=torch.zeros((),device=device)
                for lo in range(0,ntrain,64):
                    if lo%6400==0 and time.monotonic()>deadline:
                        dump(out/"INCOMPLETE.json",{"reason":"compute cap","run":name,"epoch":epoch,"completed":selected})
                        raise RuntimeError("Predeclared compute cap reached; primary study incomplete")
                    idx=order[lo:lo+64]
                    opt.zero_grad(set_to_none=True)
                    loss=criterion(model(x["train"][idx]).flatten(),y[idx])
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(),10.)
                    opt.step()
                    loss_sum+=loss.detach()*len(idx)
                sched.step()
                entry={"epoch":epoch,"train_huber":float(loss_sum.item()/ntrain),"elapsed_s":time.monotonic()-run_start}
                if epoch%config["val_every"]==0 or epoch==epochs:
                    state=clean_state(qat,model)
                    cm=clean_model(arch,state,device)
                    pred=field_predictions(arm,predict(cm,x["val"]),arrays["val"]["pid"])
                    val=metrics(pred,arrays["val"]["truth"])
                    entry["val"]=val
                    if val["mae_uT"]<best:
                        best=val["mae_uT"]
                        best_epoch=epoch
                        torch.save({"state_dict":state,"arm":arm,"seed":seed,"epoch":epoch,"val_mae_uT":best},run_dir/"best_clean.pt")
                        torch.save({"state_dict":{k:v.detach().cpu() for k,v in model.state_dict().items()},"arm":arm,"seed":seed,"epoch":epoch},run_dir/"best_qat.pt")
                        np.save(run_dir/"best_val_predictions.npy",pred)
                    del cm,state
                    print(json.dumps({"event":"VALIDATION","run":name,"epoch":epoch,"mae_uT":val["mae_uT"],"elapsed_s":time.monotonic()-start}),flush=True)
                history.append(entry)
                dump(run_dir/"history.json",history)
                if time.monotonic()>deadline:
                    dump(out/"INCOMPLETE.json",{"reason":"compute cap","run":name,"epoch":epoch,"completed":selected})
                    raise RuntimeError("Predeclared compute cap reached; primary study incomplete")
            checkpoint=torch.load(run_dir/"best_clean.pt",map_location="cpu",weights_only=True)
            reload_model=clean_model(arch,checkpoint["state_dict"],device)
            reloaded=field_predictions(arm,predict(reload_model,x["val"]),arrays["val"]["pid"])
            original=np.load(run_dir/"best_val_predictions.npy",allow_pickle=False)
            np.testing.assert_array_equal(reloaded,original)
            reload_mae=metrics(reloaded,arrays["val"]["truth"])["mae_uT"]
            assert reload_mae==best
            record={"arm":arm,"seed":seed,"epochs_completed":epochs,"selected_epoch":best_epoch,
                "val_mae_uT":best,"checkpoint":str(run_dir/"best_clean.pt"),"checkpoint_sha256":sha_file(run_dir/"best_clean.pt"),
                "qat_checkpoint_sha256":sha_file(run_dir/"best_qat.pt"),"initial_state_sha256":init_hash,
                "batch_order_sha256":order_hash.hexdigest(),"reload_prediction_max_abs_difference":float(np.max(np.abs(reloaded-original))),
                "training_seconds":time.monotonic()-run_start,"learned_sigma":float(checkpoint["state_dict"]["sigma"])}
            selected.append(record)
            saved_predictions[name]=reloaded
            dump(run_dir/"summary.json",record)
            dump(out/"completed_runs.json",selected)
            print(json.dumps({"event":"RUN_COMPLETE",**record}),flush=True)
            del model,opt,sched,reload_model,y
    for seed in SEEDS:
        same=[r for r in selected if r["seed"]==seed]
        assert len({r["initial_state_sha256"] for r in same})==1
        assert len({r["batch_order_sha256"] for r in same})==1
    np.savez_compressed(out/"validation_predictions.npz",**saved_predictions)
    freeze={"status":"complete","choices":selected,"config_sha256":sha_file(out/"run_config.json"),
        "protocol_sha256":config["protocol_sha256"],"training_wall_seconds":time.monotonic()-start,
        "test_accessed":False,"fresh_holdout_accessed":False,
        "validation_baselines":{"pid":metrics(arrays["val"]["pid"],arrays["val"]["truth"]),
          "training_mean":metrics(np.full(len(x["val"]),config["train_mean_uT"]),arrays["val"]["truth"]),
          "training_median":metrics(np.full(len(x["val"]),config["train_median_uT"]),arrays["val"]["truth"])}}
    dump(out/"FROZEN_CHOICES.json",freeze)
    print(json.dumps({"event":"ALL_CHOICES_FROZEN","path":str(out/"FROZEN_CHOICES.json"),"sha256":sha_file(out/"FROZEN_CHOICES.json"),"seconds":time.monotonic()-start}),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--protocol",type=Path,required=True)
    p.add_argument("--device",choices=("cpu","cuda"),default="cuda")
    p.add_argument("--cap-seconds",type=int,default=3600)
    args=p.parse_args()
    fit(args)


if __name__=="__main__":
    main()
