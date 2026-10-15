"""One fixed CUDA initializer; no architecture search, early stopping, or CPU training."""
import argparse,json,os
from pathlib import Path
import numpy as np
from guard import authorize,seed,sha,output,write,qualification
def main():
    p=argparse.ArgumentParser()
    for k in ("approval","data","qualification","out"):p.add_argument("--"+k,required=True)
    a=p.parse_args();auth=authorize(a.approval,"train")
    qualification(a.qualification,auth)
    out=output(a.out)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG",":4096:8")
    import torch
    if not torch.cuda.is_available():raise RuntimeError("CUDA required; no CPU fallback")
    data=Path(a.data);manifest=json.loads((data/"manifest.json").read_text())
    if manifest["split"]!="train":raise ValueError("training split required")
    for name,h in manifest["files"].items():
        if sha(data/name)!=h:raise ValueError("training artifact drift")
    with np.load(data/"inputs.npz",allow_pickle=False) as z:x=np.array((z["spectra"]-1)/.03,dtype=np.float32)
    with np.load(data/"truth.npz",allow_pickle=False) as z:y=z["parameters"]
    from physics import LOW,HIGH
    y=np.array((y-LOW)/(HIGH-LOW),dtype=np.float32)
    if auth["prior_seed_certificate"]["old_integer_upper_exclusive"]>2**63:
        raise RuntimeError("derived Torch seed needs separate range proof")
    torch_seed=2**63+seed(auth,"training_rng")%(2**63)
    if torch_seed!=auth.get("derived_torch_seed"):
        raise RuntimeError("derived Torch seed must match the audited supplement")
    torch.manual_seed(torch_seed);torch.cuda.manual_seed_all(torch_seed)
    torch.use_deterministic_algorithms(True)
    net=torch.nn.Sequential(torch.nn.Linear(100,32),torch.nn.ReLU(),torch.nn.Linear(32,16),torch.nn.ReLU(),torch.nn.Linear(16,6)).cuda()
    optimizer=torch.optim.Adam(net.parameters(),lr=.001,weight_decay=0)
    X=torch.from_numpy(x).cuda();Y=torch.from_numpy(y).cuda();losses=[]
    for epoch in range(20):
        order=torch.randperm(len(X),device="cuda");total=0.
        for ix in order.split(256):
            optimizer.zero_grad();loss=torch.mean((net(X[ix])-Y[ix])**2);loss.backward();optimizer.step()
            total+=float(loss.detach())*len(ix)
        losses.append(total/len(X))
    torch.cuda.synchronize();weights={}
    for i,layer in enumerate((net[0],net[2],net[4])):
        weights[f"W{i}"]=layer.weight.detach().cpu().numpy();weights[f"b{i}"]=layer.bias.detach().cpu().numpy()
    np.savez(out/"initializer.npz",**weights)
    write(out/"training.json",{"losses":losses,"epochs":20,"parameters":sum(p.numel() for p in net.parameters()),
        "torch":torch.__version__,"cuda":torch.version.cuda,"torch_seed":torch_seed,"device":torch.cuda.get_device_name(0),
        "peak_cuda_bytes":torch.cuda.max_memory_allocated(),"weights_sha256":sha(out/"initializer.npz"),
        "approval_sha256":auth["approval_sha256"],"qualification_sha256":sha(a.qualification),"training_manifest_sha256":sha(data/"manifest.json")})
if __name__=="__main__":main()
