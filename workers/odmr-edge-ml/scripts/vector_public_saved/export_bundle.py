"""Byte-only publication export; no array decoding, inference, or training."""
import argparse,hashlib,json
from pathlib import Path
from bundle import SOURCE_ROOT,MAX_PART_BYTES,safe_path,digest,outside_output
PART_BYTES=6*1024*1024
IDENTITIES={
    "p1":("c4c59ad97b78b43c6e4c936e9ff89e45b8efaf2e","experiments/vector_initializer_development/verify_saved.py"),
    "challenge":("869ad0f3c7ea881fd462ef1134a4159d5135bee2","experiments/vector_baseline_challenge/verify_saved.py")}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--input",required=True,type=Path);parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--kind",required=True,choices=("p1","challenge"));parser.add_argument("--config",required=True,type=Path)
    parser.add_argument("--expected-original-manifest-sha256",required=True);a=parser.parse_args()
    if not a.input.is_absolute() or not a.config.is_absolute():raise ValueError("Use absolute paths")
    outside_output(a.out)
    if a.out.resolve().is_relative_to(a.input.resolve()):raise ValueError("Export cannot be inside original evidence")
    original_path=a.input/"manifest.json"
    if digest(original_path)!=a.expected_original_manifest_sha256:raise ValueError("Wrong original manifest")
    original=json.loads(original_path.read_text())
    if original.get("status")!="complete":raise ValueError("Only complete original bundles can be exported")
    if any(Path(name).name!=name or name=="manifest.json" for name in original["files"]):raise ValueError("Invalid original filenames")
    for name,value in original["files"].items():
        if digest(safe_path(a.input,name))!=value:raise ValueError("Changed original artifact")
    omit=["checkpoint-progress.pt"] if a.kind=="p1" else []
    if any(name not in original["files"] for name in omit):raise ValueError("Unexpected original schema")
    a.out.mkdir(parents=True,exist_ok=False);(a.out/"parts").mkdir()
    (a.out/"ORIGINAL-MANIFEST.json").write_bytes(original_path.read_bytes())
    payloads={}
    for name in sorted(set(original["files"])-set(omit)):
        parts=[];total=0;combined=hashlib.sha256()
        with (a.input/name).open("rb") as stream:
            number=0
            while True:
                raw=stream.read(PART_BYTES)
                if not raw:break
                rel=f"parts/{name}.part-{number:03d}"
                safe_path(a.out,rel).write_bytes(raw)
                parts.append({"file":rel,"size_bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
                combined.update(raw);total+=len(raw);number+=1
        if total!=(a.input/name).stat().st_size or combined.hexdigest()!=original["files"][name]:raise ValueError("Input changed during export; preserve partial output")
        payloads[name]={"sha256":combined.hexdigest(),"size_bytes":total,"parts":parts}
    commit,verifier=IDENTITIES[a.kind];own=Path(__file__).resolve().parent
    names=("bundle.py","verify_p1_saved.py","verify_challenge_saved.py","export_bundle.py","PORTABILITY.json","README.md")
    manifest={"schema":1,"kind":a.kind,"original_manifest":{"file":"ORIGINAL-MANIFEST.json","sha256":a.expected_original_manifest_sha256},
        "config":{"sha256":digest(a.config)},"original_verifier":{"repo_path":verifier,"sha256":digest(SOURCE_ROOT/verifier)},
        "frozen_source":{"commit":commit,"pins":original["source_sha256"]},"payloads":payloads,"omitted_original_files":omit,
        "checker_sources":{name:digest(own/name) for name in names},
        "model_tensor_inspection":"not repeated; exact checkpoint bytes retained; original independent inspection is recorded provenance"}
    if a.kind=="challenge":
        provenance=json.loads((a.input/"provenance.json").read_text())
        manifest["frozen_p1_inputs"]=provenance["frozen_input_sha256"]
    output=a.out/"PUBLIC-MANIFEST.json";output.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"public_manifest_sha256":digest(output),"logical_files":len(payloads),"parts":sum(len(r["parts"]) for r in payloads.values()),"max_part_bytes":PART_BYTES,"no_array_decoding":True}))
    return 0
if __name__=="__main__":raise SystemExit(main())
