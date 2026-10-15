"""Hash-bound custody contracts. Metadata checks never open spectrum payloads."""
import importlib.metadata,json,subprocess,os
from pathlib import Path
from models import sha,records,interpreter_contract
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEPENDENCIES=("numpy","scipy","torch","tensorflow")
def data_contract(manifest):
    keys=("single_orientation","frequency_grid_hz","field_prior","nuisance_distribution",
          "noise_reference_fraction","generator_sha256","stress_generator_sha256","source_sha256")
    result={k:manifest[k] for k in keys}
    cell_keys=("intrinsic_fwhm_mhz","contrast","reference_snr","slope","frequency_offset_hz","photons_per_point")
    result["cells"]={name:{k:record[k] for k in cell_keys} for name,record in manifest["cells"].items()}
    return result

def source_map(root=ROOT):
    root=Path(root)
    names=list((root/"experiments/scalar_repair_cycle").glob("*.py"))
    names += [root/"experiments/scalar_repair_cycle/PROTOCOL.md",root/"tests/test_scalar_repair_cycle.py",
        root/"src/odmr_edge_ml/models/fcnn_v2.py",root/"src/odmr_edge_ml/models/fcnn.py",
        root/"src/odmr_edge_ml/evaluation/pid_proxy.py",root/"experiments/scalar_fit_baseline.py",
        root/"experiments/fcnn_v2_int8_float_equivalence.py"]
    return {str(p.relative_to(root)):sha(p) for p in sorted(names)}
def versions():
    return {**{p:importlib.metadata.version(p) for p in DEPENDENCIES},"int8_interpreter":interpreter_contract()}
def reject_symlink_path(path):
    p=Path(path)
    if any(candidate.is_symlink() for candidate in (p,*p.parents)):
        raise ValueError("symlinked custody evidence path")
def read_pinned(path,expected):
    p=Path(path)
    reject_symlink_path(p)
    if not expected or sha(p)!=expected:raise ValueError("pinned receipt hash mismatch")
    return json.loads(p.read_text())
def verify_sources(frozen):
    if frozen.get("source_hashes")!=source_map():raise ValueError("frozen source set/hash drift")
    if frozen.get("versions")!=versions():raise ValueError("frozen numerical dependency drift")
def authorize(data,partition,freeze,freeze_hash,release,release_hash,gate_document,access_receipt):
    if partition not in ("val","final"):raise ValueError("custody authorization applies to val/final only")
    if Path(gate_document).is_symlink() or Path(access_receipt).is_symlink():raise ValueError("symlinked custody artifact")
    frozen=read_pinned(freeze,freeze_hash)
    if frozen.get("schema")!=1 or frozen.get("stage")!=(1 if partition=="val" else 2):
        raise ValueError("wrong freeze stage")
    verify_sources(frozen)
    if partition=="final":verify_parent_chain(freeze,frozen)
    manifest=json.loads((Path(data)/"manifest.json").read_text())
    if data_contract(manifest)!=frozen.get("data_contract"):raise ValueError("frozen generator/distribution drift")
    if manifest.get("gate_document_sha256")!=sha(gate_document):raise ValueError("generated manifest gate binding mismatch")
    if freeze_hash not in Path(gate_document).read_text():raise ValueError("custody gate lacks freeze hash")
    permit=read_pinned(release,release_hash)
    required={"schema":1,"partition":partition,"approved":True,
        "data_manifest_sha256":sha(Path(data)/"manifest.json"),"freeze_receipt_sha256":freeze_hash,
        "gate_document_sha256":sha(gate_document),"exclusive_access_receipt_sha256":sha(access_receipt)}
    if any(permit.get(k)!=v for k,v in required.items()):raise ValueError("custody release binding mismatch")
    access=json.loads(Path(access_receipt).read_text())
    for k in ("schema","partition","data_manifest_sha256","freeze_receipt_sha256"):
        if access.get(k)!=required[k]:raise ValueError("exclusive access receipt binding mismatch")
    if access.get("status") not in ("authorized","in_progress"):raise ValueError("custody access is not authorized")
    if partition=="final" and (Path(access_receipt).name!="exclusive-access-receipt.json"
        or Path(access_receipt).resolve().parent!=Path(data).resolve().parent):
        raise ValueError("final receipt must be the data-root exclusive receipt")
    return frozen
def completed_validation(previous,prior_hash,validation):
    root=Path(previous["evaluation_root"])
    canonical=root/"results-val"/"SUMMARY.json"
    if Path(validation).is_symlink() or Path(validation).resolve()!=canonical.resolve():
        raise ValueError("validation summary is not canonical")
    paths=[canonical,canonical.parent/"RECEIPT.json",root/"VAL_EVALUATOR_ACCESS.json"]
    for p in paths:reject_symlink_path(p)
    summary,receipt,access=[json.loads(p.read_text()) for p in paths]
    digest=sha(canonical)
    if receipt.get("summary_sha256")!=digest or access.get("summary_sha256")!=digest:
        raise ValueError("completed validation summary hash mismatch")
    for obj in (summary,receipt,access):
        if obj.get("status")!="complete" or obj.get("partition")!="val" or obj.get("freeze_sha256")!=prior_hash:
            raise ValueError("validation completion/freeze binding mismatch")
        if obj.get("manifest_sha256")!=summary.get("manifest_sha256") or not obj.get("manifest_sha256"):
            raise ValueError("validation data binding mismatch")
    from decisions import decide
    selection=decide(summary["cells"])
    if summary.get("selection")!=selection or summary.get("validation_can_proceed")!=selection["can_proceed"]:
        raise ValueError("validation selection does not match frozen decision rule")
    return summary

def verify_parent_chain(freeze_path,frozen):
    reference=frozen.get("parent_freeze_reference")
    if not isinstance(reference,str) or not reference or Path(reference).is_absolute() or os.path.normpath(reference)!=reference:
        raise ValueError("parent freeze reference must be normalized and relative")
    parent_path=Path(freeze_path).parent/reference
    prior_hash=frozen.get("parent_freeze_sha256")
    previous=read_pinned(parent_path,prior_hash)
    if previous.get("schema")!=1 or previous.get("stage")!=1:
        raise ValueError("final requires pinned stage-1 parent")
    verify_sources(previous)
    for key in ("source_hashes","versions","model_records","primary_implementation","claim_route",
                "bootstrap_seed","protocol_sha256","evaluation_root","data_contract","development_manifest_sha256"):
        if key not in previous or key not in frozen or previous[key]!=frozen[key]:
            raise ValueError("parent/child frozen contract mismatch: "+key)
    validation=Path(previous["evaluation_root"])/"results-val"/"SUMMARY.json"
    evidence={"validation_summary_sha256":validation,
        "validation_receipt_sha256":validation.parent/"RECEIPT.json",
        "validation_access_sha256":Path(previous["evaluation_root"])/"VAL_EVALUATOR_ACCESS.json"}
    for key,path in evidence.items():
        reject_symlink_path(path)
        if not frozen.get(key) or sha(path)!=frozen[key]:
            raise ValueError("Freeze 2 validation evidence hash mismatch: "+key)
    summary=completed_validation(previous,prior_hash,validation)
    if not summary.get("validation_can_proceed") or frozen.get("selection")!=summary.get("selection"):
        raise ValueError("Freeze 2 selection or continuation mismatch")
    return previous

def create_freeze(stage,path,model_manifest,prior=None,prior_hash=None,validation=None,evaluation_root=None,development_manifest=None,development_manifest_hash=None):
    if Path(path).exists():raise ValueError("freeze receipt already exists")
    obj=dict(schema=1,stage=stage,source_commit=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),source_hashes=source_map(),versions=versions(),
        evaluation_root=str(Path(evaluation_root).resolve()) if evaluation_root else None,
        model_records=records(model_manifest),primary_implementation="int8",claim_route="accuracy",
        bootstrap_seed=202610152001,protocol_sha256=sha(HERE/"PROTOCOL.md"))
    if stage==1:
        if not evaluation_root or not development_manifest:raise ValueError("Freeze 1 needs evaluation root and accepted development manifest")
        dev=read_pinned(development_manifest,development_manifest_hash)
        if dev.get("partition") not in ("dev","dev-r2"):raise ValueError("Freeze 1 requires explicit accepted development metadata")
        obj.update(data_contract=data_contract(dev),development_manifest_sha256=sha(development_manifest))
    if stage==2:
        previous=read_pinned(prior,prior_hash);verify_sources(previous)
        if previous.get("schema")!=1 or previous.get("stage")!=1:raise ValueError("Freeze 2 requires Freeze 1")
        v=completed_validation(previous,prior_hash,validation)
        if not v.get("validation_can_proceed") or v.get("partition")!="val":
            raise ValueError("validation does not permit a final campaign")
        if v.get("freeze_sha256")!=prior_hash:raise ValueError("validation belongs to another freeze")
        if previous["model_records"]!=obj["model_records"]:raise ValueError("model set drift")
        obj.update(development_manifest_sha256=previous["development_manifest_sha256"],data_contract=previous["data_contract"],evaluation_root=previous["evaluation_root"],parent_freeze_reference=os.path.relpath(Path(prior).absolute(),Path(path).absolute().parent),parent_freeze_sha256=prior_hash,validation_summary_sha256=sha(validation),
            validation_receipt_sha256=sha(Path(validation).parent/"RECEIPT.json"),
            validation_access_sha256=sha(Path(previous["evaluation_root"])/"VAL_EVALUATOR_ACCESS.json"),selection=v["selection"])
    if stage==2:verify_parent_chain(path,obj)
    with Path(path).open("x") as f:json.dump(obj,f,indent=2)
    return sha(path)
def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage",type=int,choices=[1,2],required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--model-manifest",type=Path,required=True)
    p.add_argument("--evaluation-root",type=Path);p.add_argument("--development-manifest",type=Path);p.add_argument("--development-manifest-sha256")
    p.add_argument("--prior",type=Path);p.add_argument("--prior-sha256");p.add_argument("--validation",type=Path)
    a=p.parse_args();print(json.dumps(dict(path=str(a.out),sha256=create_freeze(a.stage,a.out,a.model_manifest,a.prior,a.prior_sha256,a.validation,a.evaluation_root,a.development_manifest,a.development_manifest_sha256))))
if __name__=="__main__":main()
