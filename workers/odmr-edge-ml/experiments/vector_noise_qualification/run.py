"""Registered P0 diagnostic only. No held data, selection, or training."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.vector_noise_qualification.access import authorize,source_pins


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--gate",required=True,type=Path)
    parser.add_argument("--approval-sha256",required=True)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--phase",required=True,choices=("fixtures","p0"))
    args=parser.parse_args();gate,context=authorize(args.gate,args.approval_sha256,args.phase)
    if gate.get("execution")!={"phase":args.phase}:raise PermissionError("Wrong execution")
    args.out.mkdir(parents=True,exist_ok=False)
    write(args.out/"started.json",{"phase":args.phase,"approval_sha256":args.approval_sha256,
        "reservation_id":context["central_reservation_id"],"p0_source_sha256":source_pins(),"frozen_source_sha256":gate["source_sha256"],
        "classical_source_sha256":gate["additive_source_sha256"]})
    if args.phase=="fixtures":
        import unittest
        from experiments.vector_noise_qualification import test_contracts
        with (args.out/"fixtures.txt").open("w") as stream:
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromModule(test_contracts))
        write(args.out/"result.json",{"passed":result.wasSuccessful(),"tests":result.testsRun,
            "failures":len(result.failures),"errors":len(result.errors)})
        return 0 if result.wasSuccessful() else 2
    certificate=Path(gate["seed_certificate_path"])
    if sha(certificate)!=gate["seed_certificate_sha256"]:raise PermissionError("Seed custody hash mismatch")
    import numpy as np
    import torch
    if not torch.cuda.is_available():raise RuntimeError("Approved CUDA host unavailable")
    torch.cuda.set_per_process_memory_fraction(min(1.,16*1024**3/torch.cuda.get_device_properties(0).total_memory),0)
    from experiments.vector_noise_qualification.core import generate,information,errors,summarize,METHODS,EXPOSURE
    from experiments.vector_direct_screen.physics import Engine
    from experiments.vector_classical_qualification.adapter import fit_counts
    generation_start=time.perf_counter()
    data,records=generate(json.loads(certificate.read_text()))
    generation_seconds=time.perf_counter()-generation_start
    np.savez_compressed(args.out/"data.npz",**data)
    write(args.out/"records.json",records)
    write(args.out/"provenance.json",{"noise_law":"independent Poisson(EXPOSURE * fluorescence)",
        "exposure_photons_per_bin":EXPOSURE,"numpy_version":np.__version__,"bit_generator":"PCG64",
        "seed_certificate_sha256":sha(certificate),"generation_seconds":generation_seconds,
        "latent_rows":64,"A_latents":32,"B_latents":32,"replicates_per_latent":2,"spectra":128,
        "field_units":"microtesla","frequency_units":"MHz","selection":"none","p0_source_sha256":source_pins(),"frozen_source_sha256":gate["source_sha256"],
        "classical_source_sha256":gate["additive_source_sha256"]})
    true_info=information(data["true_rates"],data["true_jacobian"])
    np.savez_compressed(args.out/"true_information.npz",**true_info)
    summaries={};completed=[]
    def manifest(status):
        write(args.out/"manifest.json",{"status":status,"approval_sha256":args.approval_sha256,
            "source_sha256":source_pins(),"completed_methods":completed,"method_order":[m[0] for m in METHODS],
            "files":{f.name:sha(f) for f in sorted(args.out.iterdir()) if f.is_file() and f.name!="manifest.json"}})
    manifest("running")
    regimes=np.repeat(np.array([0]*32+[1]*32),2)
    for name,dtype,chunk in METHODS:
        start=time.perf_counter()
        result=fit_counts(data["counts"],backend="torch",device="cuda",dtype=dtype,
                          variant=name,chunk_size=chunk)
        torch.cuda.synchronize();elapsed=time.perf_counter()-start
        np.savez_compressed(args.out/(name+"-prediction.npz"),**result)
        if not np.isfinite(result["parameters"]).all():raise AssertionError("Nonfinite prediction; preserve and stop")
        diagnostic_start=time.perf_counter()
        rates,jacobian=Engine().spectrum(result["parameters"].astype(float),True)
        expected=information(rates,jacobian)
        observed=information(rates,jacobian,data["counts"])
        delta,norm=errors(result["parameters"],data["parameters"])
        output={"fitted_rates":rates,"fitted_jacobian":jacobian,"field_delta_uT":delta,"field_error_uT":norm}
        output.update({"plugin_expected_"+k:v for k,v in expected.items()})
        output.update({"observed_gn_"+k:v for k,v in observed.items()})
        np.savez_compressed(args.out/(name+"-diagnostics.npz"),**output)
        summaries[name]={"dtype":dtype,"chunk":chunk,"host_to_host_seconds":elapsed,
            "diagnostic_seconds":time.perf_counter()-diagnostic_start,
            "errors":summarize(norm,result["accepted"],result["fallback"],regimes),
            "plugin_expected_rank_deficient":int((expected["rank"]<8).sum()),
            "observed_gn_rank_deficient":int((observed["rank"]<8).sum())}
        write(args.out/(name+"-summary.json"),summaries[name]);completed.append(name);manifest("running")
    write(args.out/"result.json",{"status":"diagnostic_only_no_adoption","spectra":128,
        "all_cases_retained":True,"true_expected_rank_deficient":int((true_info["rank"]<8).sum()),
        "methods":summaries,"practical_adoption":False,"neural_model":False})
    manifest("complete")
    return 0


if __name__=="__main__":raise SystemExit(main())
