"""Reuse the released direct model and its existing INT8 preprocessing."""
import hashlib, importlib.util, json, sys
from pathlib import Path
import numpy as np

SEEDS=(42,20261014,20261015)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj)
    return obj
def records(manifest):
    all_rows=json.loads(Path(manifest).read_text())["candidates"]
    chosen=[r for r in all_rows if r["arm"]=="C_direct"]
    if len(chosen)!=3 or {r["seed"] for r in chosen}!=set(SEEDS):
        raise ValueError("expected exactly the three frozen direct seeds")
    for r in chosen:
        for key in ("checkpoint","export"):
            if sha(r[key])!=r[key+"_sha256"]:raise ValueError("frozen model artifact changed")
    return sorted(chosen,key=lambda r:r["seed"])
class DirectModels:
    def __init__(self,repo,chosen):
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        self.torch=torch
        self.helpers=module("scalar_repair_export_helpers",Path(repo)/"experiments/fcnn_v2_int8_float_equivalence.py")
        arch=module("scalar_repair_arch",Path(repo)/"src/odmr_edge_ml/models/fcnn_v2.py")
        try:from tflite_runtime.interpreter import Interpreter
        except ImportError:from tensorflow.lite.python.interpreter import Interpreter
        self.items=[]
        for r in chosen:
            ckpt=torch.load(r["checkpoint"],map_location="cpu",weights_only=True)
            if ckpt["arm"]!="C_direct" or ckpt["seed"]!=r["seed"]:raise ValueError("checkpoint identity mismatch")
            sigma=float(ckpt["state_dict"]["sigma"])
            if not np.isfinite(sigma) or sigma<.1:raise ValueError("invalid anchor sigma")
            model=arch.OdmrFCNNv2();model.load_state_dict(ckpt["state_dict"],strict=True);model.eval()
            interp=Interpreter(model_path=r["export"],num_threads=1);interp.allocate_tensors()
            for d in (interp.get_input_details()[0],interp.get_output_details()[0]):
                scale,_=d["quantization"]
                if d["dtype"]!=np.int8 or not np.isfinite(scale) or scale<=0:raise ValueError("invalid INT8 contract")
            self.items.append((r["name"],model,interp,sigma))
    def predict(self,spectra,locks):
        y=np.asarray(spectra,float);locks=np.asarray(locks)
        low=y.min(1,keepdims=True);high=y.max(1,keepdims=True)
        norm=2*(y-low)/np.where(high==low,1,high-low)-1
        packed=self.torch.from_numpy(np.concatenate((norm,locks[:,None]),axis=1).astype(np.float32))
        result={};quant={}
        for name,model,interp,sigma in self.items:
            with self.torch.inference_mode():result[name+"__fp32"]=model(packed).numpy().ravel().astype(float)
            flat=self.helpers.preprocess(y,locks,sigma)
            pred,stats=self.helpers.run_tflite(interp,flat)
            result[name+"__int8"]=pred.astype(float);quant[name]=stats
        return result,quant

    def predict_one(self,row,lock,name,precision):
        item=next(item for item in self.items if item[0]==name)
        _,model,interp,sigma=item
        y=np.asarray(row,float)[None,:]
        if precision=="int8":
            flat=self.helpers.preprocess(y,np.array([lock]),sigma)
            return float(self.helpers.run_tflite(interp,flat)[0][0])
        if precision!="fp32":raise ValueError("unknown precision")
        norm=2*(y-y.min())/(np.ptp(y) if np.ptp(y) else 1)-1
        packed=self.torch.from_numpy(np.column_stack((norm,np.array([lock]))).astype(np.float32))
        with self.torch.inference_mode():return float(model(packed).item())
