"""Predict from inputs only; truth is never opened by this process."""
import argparse,json,time
from pathlib import Path
import numpy as np
from budget import sha,write_json,runtime,bindings
from fit import fit_one

def run(args):
    started=time.perf_counter()
    manifest=args.data/"manifest.json"
    record,bound=bindings(args,manifest,"prediction")
    if sha(args.data/"inputs.npz")!=record["files"]["inputs.npz"]:raise ValueError("input hash mismatch")
    args.out.mkdir(parents=True,exist_ok=False)
    receipt={"status":"running",**bound,"protocol_sha256":sha(args.protocol),"runtime":runtime()}
    try:
        with np.load(args.data/"inputs.npz",allow_pickle=False) as archive:
            if set(archive.files)!={"spectra","frequencies_mhz","bias_uT","row_ids"}:
                raise ValueError("input archive has unexpected content")
            data={k:archive[k] for k in archive.files}
        if len(data["row_ids"])!=record["rows"] or len(set(data["row_ids"]))!=record["rows"]:
            raise ValueError("row cardinality")
        answers=[fit_one(y,data["frequencies_mhz"],float(bias))
                 for y,bias in zip(data["spectra"],data["bias_uT"])]
        if len(answers)!=record["rows"]:raise ValueError("prediction count mismatch")
        np.savez_compressed(args.out/"predictions.npz",row_ids=data["row_ids"],
            estimate_uT=np.array([x["estimate_uT"] for x in answers]),
            failed=np.array([x["failed"] for x in answers]),
            boundary=np.array([x["boundary"] for x in answers]),
            elapsed_seconds=np.array([x["elapsed_seconds"] for x in answers]))
        write_json(args.out/"starts.json",answers)
        receipt.update(status="complete",rows=len(answers),
            prediction_sha256=sha(args.out/"predictions.npz"),starts_sha256=sha(args.out/"starts.json"))
    except Exception as exc:
        receipt.update(status="failed",error=type(exc).__name__+": "+str(exc));raise
    finally:
        receipt["total_process_seconds"]=time.perf_counter()-started
        write_json(args.out/"receipt.json",receipt)
    write_json(args.out/"commitment.json",{"prediction_sha256":receipt["prediction_sha256"],
        "prediction_receipt_sha256":sha(args.out/"receipt.json"),**bound})
    print(json.dumps({"status":"complete","rows":receipt["rows"],
        "commitment_sha256":sha(args.out/"commitment.json")}))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("data","out","registration","protocol"):p.add_argument("--"+name,type=Path,required=True)
    for name in ("freeze","access","code-root"):p.add_argument("--"+name,type=Path)
    run(p.parse_args())
