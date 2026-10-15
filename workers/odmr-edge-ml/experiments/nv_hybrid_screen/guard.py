"""Fail closed until root freezes shared screening rules and accounting."""
import hashlib,json,os
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def authorize(path,phase):
    path=Path(path);a=json.loads(path.read_text())
    if a.get("status")!="approved" or a.get("study")!="nv-hybrid-screen-2026-10-15":
        raise RuntimeError("root approval is not active")
    if phase not in a.get("phases",[]):raise RuntimeError("phase not authorized")
    if os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256")!=sha(path) or not os.environ.get("TYCHON_NUMERICAL_RUN_ID"):
        raise RuntimeError("shared accounting wrapper must supply approval hash and unique run ID")
    root=Path(__file__).resolve().parent
    if a.get("protocol_sha256")!=sha(root/"protocol.json"):raise RuntimeError("protocol drift")
    if not a.get("source_sha256"):raise RuntimeError("source freeze required")
    for name,h in a["source_sha256"].items():
        p=Path(name)
        if p.is_absolute() or ".." in p.parts or sha(root/p)!=h:raise RuntimeError("source freeze drift")
    renderer=root.parent/"scalar_information_limit/forward.py"
    if a.get("renderer_sha256")!=sha(renderer):raise RuntimeError("renderer source drift")
    required={p.name for p in root.glob("*.py")}|{"protocol.json"}
    if not required<=set(a["source_sha256"]):raise RuntimeError("incomplete source freeze")
    for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
        if os.environ.get(k)!="1":raise RuntimeError("one numerical thread required")
    a["approval_sha256"]=sha(path)
    return a
def seed(a,split):
    seeds=a["fresh_seeds"]
    values=list(seeds.values())
    if len(values)!=len(set(values)) or any(not 2**96<=x<2**128 for x in values):
        raise RuntimeError("fresh 128-bit seed namespace required")
    c=a["prior_seed_certificate"]
    if c.get("status")!="pass" or c.get("old_upper_exclusive",2**128)>2**96 or not c.get("sha256"):
        raise RuntimeError("root metadata-only prior-seed range certificate required")
    return seeds[split]
def output(path):
    p=Path(path);p.mkdir(parents=True,exist_ok=False);return p
def write(path,obj):
    with Path(path).open("x") as f:json.dump(obj,f,indent=2,allow_nan=False);f.write("\n")
