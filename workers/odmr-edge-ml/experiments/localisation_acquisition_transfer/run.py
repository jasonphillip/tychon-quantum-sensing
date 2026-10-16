"""One approved all-case acquisition transfer. Never fit a position model."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile
if __package__ in (None,""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    __package__="experiments.localisation_acquisition_transfer"
from .guard import PACKAGE, authorize, bind, read_json, write_json, sha256
from .contract import ROOT, check_geometry, check_saved_labels, decode_seed_bytes


def load_model(path):
    import numpy as np
    from experiments.localisation_redesign.models import Scaling
    with np.load(path,allow_pickle=False) as saved:
        state={k.removeprefix("state."):saved[k] for k in saved.files if k.startswith("state.")}
        scale=Scaling()
        for key in ("x_mean","x_scale","y_mean","y_scale"):
            setattr(scale,key,saved["scale."+key])
    return state,scale


def main():
    parser=argparse.ArgumentParser()
    for key in ("approval","archive","custody","qualification","small-checkpoint","full-checkpoint","member-manifest","seed-commitment","seed","consumption","output"):
        parser.add_argument("--"+key,required=True)
    args=parser.parse_args()
    approval=authorize(args.approval,"evaluate")
    protocol=read_json(PACKAGE/"protocol.json")
    for key in ("archive","custody","qualification","small_checkpoint","full_checkpoint","member_manifest","seed_commitment","seed"):
        bind(approval,key,getattr(args,key))
    for key in ("archive","custody","small_checkpoint","full_checkpoint","member_manifest","seed_commitment","seed"):
        if sha256(getattr(args,key))!=protocol[key+"_sha256"]:
            raise ValueError("protocol input drift: "+key)
    if (approval.get("signal_values_authorized")!="exact25_august4_members_only"
            or approval.get("one_shot_consumption_path")!=str(Path(args.consumption).resolve())
            or approval.get("independent_qualification_verified") is not True):
        raise RuntimeError("root release and independent compatibility verification required")
    qualification=read_json(args.qualification)
    if sha256(args.qualification)!=protocol["qualification_manifest_sha256"]:
        raise ValueError("qualified extractor result changed")
    report_path=Path(args.qualification).parent/"qualification.json"
    if sha256(report_path)!=qualification["files"]["qualification.json"]:
        raise ValueError("qualification report drift")
    prior=read_json(report_path)
    if (prior["status"]!="PASS" or prior["all_fits_valid"] is not True
            or prior["comparison"]["passed_elements"]!=192 or prior["samples"]!=8):
        raise ValueError("training-only compatibility gate not passed")
    commitment=read_json(args.seed_commitment)
    if (commitment["commitment_sha256"]!=protocol["seed_sha256"]
            or commitment["bound_member_manifest_sha256"]!=protocol["member_manifest_sha256"]
            or commitment["archive_sha256"]!=protocol["archive_sha256"]):
        raise ValueError("seed commitment binding differs")
    bootstrap=decode_seed_bytes(Path(args.seed).read_bytes(),protocol["seed_sha256"])
    seed={"study":protocol["study"],"bootstrap":bootstrap,
          "seed_commitment_sha256":sha256(args.seed_commitment),
          "released_seed_sha256":sha256(args.seed),
          "derivation":"int.from_bytes(32bytes,big);NumPy SeedSequence"}
    geometry=read_json(PACKAGE/"geometry.json")
    if sha256(PACKAGE/"geometry.json")!=protocol["geometry_sha256"]:
        raise ValueError("geometry drift")
    rows=check_geometry(geometry,read_json(args.custody))
    members=read_json(args.member_manifest)
    if (members["schema"]!=1 or members["member_count"]!=25
            or members["status"]!="SEALED_BEFORE_SIGNAL_ACCESS"
            or members["archive_sha256"]!=protocol["archive_sha256"]
            or members["custody_record_sha256"]!=protocol["custody_sha256"]
            or sorted(members["members"],key=lambda r:tuple(r["position_um"])) !=
               [{k:v for k,v in r.items() if k not in ("group_id","position_sha256")} for r in rows]):
        raise ValueError("exact separate-day member manifest differs")
    output=Path(args.output).resolve()
    if output==PACKAGE.parents[1] or PACKAGE.parents[1] in output.parents:
        raise ValueError("outputs must remain outside source checkout")
    output.mkdir(parents=True,exist_ok=False)
    # Exclusive creation precedes any raw signal access; never reopen after failure.
    write_json(args.consumption,{"study":protocol["study"],"approval_sha256":sha256(args.approval),
                                "geometry_sha256":sha256(PACKAGE/"geometry.json"),
                                "members":[r["member"] for r in rows],"status":"consumed_before_first_decode"})
    import numpy as np
    from experiments.localisation_raw_compatibility.extract import extract_payload
    from experiments.localisation_raw_compatibility.metadata import read_raw_header
    from experiments.localisation_redesign.models import predict_classical
    from .metrics import evaluate
    features=[];flags=[];member_receipts=[];parameters=[];deviations=[]
    with zipfile.ZipFile(args.archive) as archive:
        if len(archive.namelist())!=len(set(archive.namelist())):
            raise ValueError("duplicate archive member")
        for row in rows:
            name=ROOT+row["member"];info=archive.getinfo(name)
            if info.file_size!=row["size"] or format(info.CRC,"08x")!=row["crc32"]:
                raise ValueError("raw member metadata drift")
            with archive.open(name) as stream:
                header=read_raw_header(stream,info.file_size)
            if header["shape"]!=row["npy_shape"] or row["npy_dtype"]!="float64":
                raise ValueError("raw header differs from custody")
            payload=archive.read(name)
            p,s,x,f=extract_payload(payload)
            parameters.append(p);deviations.append(s);features.append(x);flags.append(f)
            member_receipts.append({"member":row["member"],"sha256":hashlib.sha256(payload).hexdigest()})
    x=np.asarray(features)
    labels=np.asarray([r["position_um"] for r in rows],dtype=float)
    check_saved_labels(labels,geometry)
    valid=np.array([all(f["valid"] for f in row) for row in flags]) & np.isfinite(x).all(1) & (x>0).all(1)
    predictions={}
    for name in ("small","full"):
        state,scale=load_model(getattr(args,name+"_checkpoint"))
        prediction=np.full((25,2),np.nan)
        if valid.any():
            prediction[valid]=scale.inverse(predict_classical(protocol["model"]["config"],state,scale.x(x[valid])))
        predictions[name]=prediction
    groups=np.asarray([r["group_id"] for r in rows])
    metrics=evaluate(labels,predictions["small"],predictions["full"],groups,protocol,seed["bootstrap"])
    np.savez(output/"predictions.npz",labels=labels,small=predictions["small"],full=predictions["full"],groups=groups,valid_raw=valid)
    for name,values in (("features_MHz.npy",x),("fit_parameters.npy",parameters),("fit_std.npy",deviations)):
        np.save(output/name,np.asarray(values),allow_pickle=False)
    for name,value in (("metrics.json",metrics),("fit_flags.json",flags),("member_receipts.json",member_receipts),
                       ("geometry.json",geometry),("protocol.json",protocol),("seed.json",seed)):
        write_json(output/name,value)
    write_json(output/"manifest.json",{"schema_version":1,"approval_sha256":sha256(args.approval),
               "source_sha256":approval["source_sha256"],"dependency_sha256":approval["dependency_sha256"],
               "inputs":{key:sha256(getattr(args,key)) for key in ("archive","custody","qualification","small_checkpoint","full_checkpoint","member_manifest","seed_commitment","seed")},
               "files":{p.name:sha256(p) for p in sorted(output.iterdir())},
               "position_model_refit":False,"original_spatial_verdict":"FAIL"})
    print(metrics["status"],metrics["criteria"])
    return 0 if metrics["status"]=="PASS" else 2


if __name__=="__main__":
    raise SystemExit(main())
