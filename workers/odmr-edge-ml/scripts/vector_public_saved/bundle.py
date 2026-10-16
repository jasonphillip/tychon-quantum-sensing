"""Exact-byte public artifact access. No experiment or numerical imports."""
import argparse,hashlib,io,json,re
from pathlib import Path,PurePosixPath
MAX_PART_BYTES=10*1024*1024
SOURCE_ROOT=Path(__file__).resolve().parents[2]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def valid_sha(value):return isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value) is not None

def safe_path(root,name):
    if not isinstance(name,str) or not name or "\\" in name:raise ValueError("Invalid relative path")
    rel=PurePosixPath(name)
    if rel.is_absolute() or any(part in (".","..") for part in rel.parts) or str(rel)!=name:raise ValueError("Unsafe relative path")
    path=root.joinpath(*rel.parts)
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError("Path escapes bundle")
    return path

def checkout_boundary(source_root):
    """Find the enclosing Git checkout, including a worktree .git pointer file."""
    source_root=source_root.resolve()
    for parent in (source_root,*source_root.parents):
        marker=parent/".git"
        if marker.is_file() or marker.is_dir():return parent
    return source_root

def outside_output(path,source_root=SOURCE_ROOT):
    if not path.is_absolute() or path.exists():raise ValueError("Output must be an unused absolute directory")
    if path.resolve().is_relative_to(checkout_boundary(source_root)):raise ValueError("Output must be outside the entire source checkout")

def parse_args():
    if not __debug__:raise RuntimeError("Verification must run without Python -O")
    parser=argparse.ArgumentParser();parser.add_argument("--bundle",required=True,type=Path)
    parser.add_argument("--expected-manifest-sha256",required=True);parser.add_argument("--config",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path);a=parser.parse_args()
    if not a.bundle.is_absolute() or not a.config.is_absolute():raise ValueError("Use absolute bundle and config paths")
    outside_output(a.out)
    if a.out.resolve().is_relative_to(a.bundle.resolve()):raise ValueError("Output cannot be inside evidence bundle")
    return a

class LogicalFile(io.BytesIO):
    def read_bytes(self):return self.getvalue()
    def read_text(self):return self.getvalue().decode("utf-8")

class PublicBundle:
    def __init__(self,root,expected_sha,config,kind,verifier_path,verifier_sha):
        self.root=root.resolve();manifest_path=self.root/"PUBLIC-MANIFEST.json"
        if not valid_sha(expected_sha) or digest(manifest_path)!=expected_sha:raise ValueError("Wrong public manifest")
        self.public_manifest_sha256=expected_sha
        self.manifest=json.loads(manifest_path.read_text());m=self.manifest
        if m.get("schema")!=1 or m.get("kind")!=kind:raise ValueError("Wrong public bundle schema or kind")
        if m.get("original_verifier")!={"repo_path":verifier_path,"sha256":verifier_sha}:raise ValueError("Wrong original verifier identity")
        if digest(safe_path(SOURCE_ROOT,verifier_path))!=verifier_sha:raise ValueError("Original verifier source changed")
        if digest(config)!=m["config"]["sha256"]:raise ValueError("Wrong physics configuration")
        self.config=json.loads(config.read_text())
        own=Path(__file__).resolve().parent
        required={"bundle.py","verify_p1_saved.py","verify_challenge_saved.py","export_bundle.py","PORTABILITY.json","README.md"}
        if set(m["checker_sources"])!=required:raise ValueError("Incomplete public checker source map")
        for name,value in m["checker_sources"].items():
            if not valid_sha(value) or digest(own/name)!=value:raise ValueError("Changed public checker source")
        rec=m["original_manifest"];origin=safe_path(self.root,rec["file"])
        if origin.stat().st_size>MAX_PART_BYTES or digest(origin)!=rec["sha256"]:raise ValueError("Wrong original manifest")
        self.original_bytes=origin.read_bytes();self.original=json.loads(self.original_bytes)
        if self.original.get("status")!="complete" or self.original["source_sha256"]!=m["frozen_source"]["pins"]:raise ValueError("Wrong original completion/source identities")
        expected_commit={"p1":"c4c59ad97b78b43c6e4c936e9ff89e45b8efaf2e","challenge":"869ad0f3c7ea881fd462ef1134a4159d5135bee2"}[kind]
        if m["frozen_source"]["commit"]!=expected_commit:raise ValueError("Wrong frozen source commit")
        omitted=["checkpoint-progress.pt"] if kind=="p1" else []
        if m["omitted_original_files"]!=omitted:raise ValueError("Only documented progress checkpoint omission is permitted")
        if set(m["payloads"])!=set(self.original["files"])-set(omitted):raise ValueError("Missing or extra original artifacts")
        if m["model_tensor_inspection"]!="not repeated; exact checkpoint bytes retained; original independent inspection is recorded provenance":raise ValueError("Weight inspection boundary missing")
        for name,record in m["payloads"].items():
            if PurePosixPath(name).name!=name or name=="manifest.json":raise ValueError("Invalid logical filename")
            if record["sha256"]!=self.original["files"][name]:raise ValueError("Changed logical artifact hash")
            self._read(name,materialize=False)
        if kind=="p1":
            for i in range(8):
                if f"train-counts-{i:02d}.npz" not in m["payloads"]:raise ValueError("All training count blocks required")
        else:
            if set(m["frozen_p1_inputs"])!={"model-final.pt","scaling.npz","setup.json"}:raise ValueError("Wrong frozen P1 inputs")
            for name,value in m["frozen_p1_inputs"].items():
                if value!=m["payloads"]["p1-"+name]["sha256"]:raise ValueError("Changed frozen P1 input")

    def _read(self,name,materialize=True):
        record=self.manifest["payloads"][name];size=record["size_bytes"]
        if type(size) is not int or size<1 or not valid_sha(record["sha256"]):raise ValueError("Invalid logical size/hash")
        parts=record["parts"]
        if not isinstance(parts,list) or not parts:raise ValueError("Missing byte parts")
        total=0;combined=hashlib.sha256();data=[]
        for part in parts:
            path=safe_path(self.root,part["file"]);n=part["size_bytes"]
            if type(n) is not int or not 0<n<=MAX_PART_BYTES or path.stat().st_size!=n or not valid_sha(part["sha256"]):raise ValueError("Part size/hash contract failed")
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=part["sha256"]:raise ValueError("Changed byte part")
            total+=n;combined.update(raw)
            if materialize:data.append(raw)
        if total!=size or combined.hexdigest()!=record["sha256"]:raise ValueError("Wrong concatenated original bytes")
        return b"".join(data) if materialize else None

    def __truediv__(self,name):
        if name=="manifest.json":return LogicalFile(self.original_bytes)
        if name not in self.manifest["payloads"]:raise ValueError("Undeclared logical artifact")
        return LogicalFile(self._read(name))
