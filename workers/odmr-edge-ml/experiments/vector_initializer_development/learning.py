"""One deterministic fixed MLP recipe. No validation-selected checkpoint."""
import hashlib
import numpy as np
from experiments.vector_direct_screen.physics import CFG,Engine
from experiments.vector_noise_qualification.core import poisson_draw,independent_rates
SEED_NAMES=("train_parameter_seed","train_noise_seed","validation_parameter_seed","validation_noise_seed","training_seed")
TRAIN_N=32768
VALIDATION_N=2048
EPOCHS=20
BATCH=512

def seed_values(certificate):
    if certificate.get("purpose")!="vector_p1" or certificate.get("status")!="ISSUED" or certificate.get("freshness_attestation")!="ROOT_CONFIRMED_NOT_PREVIOUSLY_USED":raise ValueError("Fresh P1 custody required")
    values=[certificate.get(n) for n in SEED_NAMES]
    if any(not isinstance(v,str) or not v.isdecimal() or not 0<=int(v)<2**128 for v in values):raise ValueError("Five unsigned128-bit streams required")
    values=list(map(int,values))
    if len(set(values))!=5:raise ValueError("Streams must differ")
    return values

def generate(certificate):
    tp,tn,vp,vn,_=seed_values(certificate);result={};seen=set()
    for label,n,ps,ns in (("train",TRAIN_N,tp,tn),("validation",VALIDATION_N,vp,vn)):
        parameters=np.random.Generator(np.random.PCG64(ps)).uniform(CFG["lower"],CFG["upper"],size=(n,8))
        hashes=[hashlib.sha256(p.astype("<f8").tobytes()).hexdigest() for p in parameters]
        if len(set(hashes))!=n or seen.intersection(hashes):raise ValueError("Latent overlap or duplicate")
        seen.update(hashes);rates=np.empty((n,512));engine=Engine()
        for start in range(0,n,256):rates[start:start+256]=engine.spectrum(parameters[start:start+256])
        indexes=np.linspace(0,n-1,32,dtype=int)
        reference=independent_rates(parameters[indexes])
        if not np.allclose(rates[indexes],reference,rtol=0,atol=1e-11):raise AssertionError("Independent physical mean mismatch")
        result[label+"_parameters"]=parameters;result[label+"_counts"]=poisson_draw(rates,ns)
        result[label+"_mean_check_indices"]=indexes;result[label+"_independent_rates"]=reference
        result[label+"_rates_at_checks"]=rates[indexes]
    return result

def feature_scaling(train_counts):
    rates=np.asarray(train_counts,dtype=np.float64)/CFG["photons_per_bin"]
    return rates.mean(axis=0),np.maximum(rates.std(axis=0,ddof=0),1e-6)

def target_scaling():
    low=np.asarray(CFG["lower"]);high=np.asarray(CFG["upper"])
    return (low+high)/2,(high-low)/2

def build_model(torch):
    return torch.nn.Sequential(torch.nn.Linear(512,256),torch.nn.ReLU(),torch.nn.Linear(256,128),
        torch.nn.ReLU(),torch.nn.Linear(128,64),torch.nn.ReLU(),torch.nn.Linear(64,8))

def train(torch,data,seed,out,progress):
    torch.manual_seed(seed%(2**63));torch.cuda.manual_seed_all(seed%(2**63))
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    mean,std=feature_scaling(data["train_counts"]);center,scale=target_scaling()
    features=torch.as_tensor((data["train_counts"]/CFG["photons_per_bin"]-mean)/std,dtype=torch.float32,device="cuda")
    targets=torch.as_tensor((data["train_parameters"]-center)/scale,dtype=torch.float32,device="cuda")
    model=build_model(torch).to(device="cuda",dtype=torch.float32)
    optimizer=torch.optim.Adam(model.parameters(),lr=.001,betas=(.9,.999),eps=1e-8,weight_decay=0)
    history=[]
    for epoch in range(EPOCHS):
        permutation=torch.randperm(len(features),device="cuda");total=0.
        for start in range(0,len(features),BATCH):
            rows=permutation[start:start+BATCH];optimizer.zero_grad(set_to_none=True)
            loss=torch.mean((model(features[rows])-targets[rows])**2)
            if not bool(torch.isfinite(loss)):raise RuntimeError("Nonfinite training objective")
            loss.backward();optimizer.step();total+=float(loss.detach())*len(rows)
        history.append({"epoch":epoch+1,"train_normalized_mse":total/len(features)})
        torch.save({"epoch":epoch+1,"model":model.state_dict(),"optimizer":optimizer.state_dict(),
            "rng_state":torch.get_rng_state(),"cuda_rng_state":torch.cuda.get_rng_state()},out/"checkpoint-progress.pt")
        progress(history)
    torch.save(model.state_dict(),out/"model-final.pt")
    np.savez_compressed(out/"scaling.npz",feature_mean=mean,feature_std=std,target_center=center,target_scale=scale)
    return model,mean,std,center,scale,history

def initializer(torch,model,mean,std,center,scale,*,device="cuda"):
    # Dense inference stays float32; only eight outputs cross into float64 physics.
    model=model.eval().to(device=device,dtype=torch.float32)
    mean,std=[torch.as_tensor(a,dtype=torch.float32,device=device) for a in (mean,std)]
    center,scale=[torch.as_tensor(a,dtype=torch.float64,device=device) for a in (center,scale)]
    def predict(counts):
        features=(counts.to(dtype=torch.float32)/CFG["photons_per_bin"]-mean)/std
        normalized=model(features)
        return normalized.to(dtype=torch.float64)*scale+center
    return predict


def count_blocks(n):
    """Predetermined rows; maximum raw int64 count array is16MiB per file."""
    return [(start,min(start+4096,n)) for start in range(0,n,4096)]


def save_data(data,out):
    import json
    np.savez_compressed(out/"data.npz",**{k:v for k,v in data.items() if not k.endswith("_counts")})
    blocks={}
    for split,n in (("train",TRAIN_N),("validation",VALIDATION_N)):
        counts=data[split+"_counts"]
        if counts.shape!=(n,512):raise ValueError("Wrong split count shape")
        blocks[split]=[]
        for number,(start,stop) in enumerate(count_blocks(n)):
            filename=f"{split}-counts-{number:02d}.npz"
            np.savez_compressed(out/filename,counts=counts[start:stop])
            blocks[split].append({"file":filename,"start":start,"stop":stop})
    (out/"data-schema.json").write_text(json.dumps({"schema":1,"counts_per_file_max_rows":4096,
        "frequency_bins":512,"counts_dtype":"int64","blocks":blocks},indent=2)+"\n")
