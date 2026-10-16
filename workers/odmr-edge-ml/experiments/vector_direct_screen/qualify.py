"""Run only under a hash-pinned root approval and direct accounting supervisor."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

# Direct-file invocation supports the supervisor's absolute-script policy.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from experiments.vector_direct_screen.access import authorize, source_pins

def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--gate",type=Path,required=True)
    parser.add_argument("--approval-sha256",required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--phase",choices=["fixtures","fidelity","solver","profile"],required=True)
    parser.add_argument("--backend",choices=["numpy","torch"],default="numpy")
    parser.add_argument("--device",choices=["cpu","cuda"],default="cpu")
    parser.add_argument("--dtype",choices=["float64","float32"],default="float64")
    parser.add_argument("--variant",choices=["affine","peaks","calibrated","lm"],default="affine")
    parser.add_argument("--batch",type=int,choices=[64,4096],default=64)
    args=parser.parse_args()
    gate,context=authorize(args.gate,args.approval_sha256,args.phase)
    signature={k:getattr(args,k) for k in ("phase","backend","device","dtype","variant","batch")}
    if gate.get("execution") != signature:
        raise PermissionError("Command does not match frozen execution")
    args.out.mkdir(parents=True,exist_ok=False)
    write_json(args.out/"started.json",{"status":"running","execution":signature,
        "source_sha256":source_pins(),"approval_sha256":args.approval_sha256,
        "reservation_id":context["central_reservation_id"]})
    if args.device=="cuda":
        if args.backend!="torch":
            raise ValueError("CUDA needs PyTorch")
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("Approved CUDA target is unavailable")
        # Source contract: one PyTorch allocator, one process, no loaders or children.
        available=torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1.,16*1024**3/available),0)
    import numpy as np
    from experiments.vector_direct_screen.physics import CFG,Engine
    from experiments.vector_direct_screen.independent import reference_transitions,manufactured_parameters
    p=manufactured_parameters()
    if args.phase=="fixtures":
        import unittest
        from experiments.vector_direct_screen import test_manufactured
        with (args.out/"fixtures.txt").open("w") as stream:
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromModule(test_manufactured))
        write_json(args.out/"result.json",{"passed":result.wasSuccessful(),"tests":result.testsRun,
            "failures":len(result.failures),"errors":len(result.errors),"scope":"manufactured only"})
        return 0 if result.wasSuccessful() else 2
    e=Engine(args.backend,args.device,args.dtype)
    target=reference_transitions(p,CFG["bias_uT"],CFG["gamma_MHz_per_uT"])
    got=e.numpy(e.transitions(e.array(p)))
    reference_spectra=Engine().spectrum(p)
    if args.phase=="fidelity":
        maximum=float(np.max(np.abs(got-target)))
        tolerance=CFG["fidelity_"+args.dtype+"_MHz"]
        values,jac=e.spectrum(e.array(p),True)
        ref_values,ref_jac=Engine().spectrum(p,True)
        spectrum_error=float(np.max(np.abs(e.numpy(values)-ref_values)))
        jac_error=float(np.max(np.abs(e.numpy(jac)-ref_jac)))
        spectral_tolerance=2e-5 if args.dtype=="float32" else 1e-11
        jac_tolerance=2e-4 if args.dtype=="float32" else 1e-10
        passed=maximum<=tolerance and spectrum_error<=spectral_tolerance and jac_error<=jac_tolerance
        np.savez_compressed(args.out/"fidelity.npz",parameters=p,frequencies=e.numpy(e.freq),
            reference_transitions=target,transitions=got,reference_spectra=ref_values,
            spectra=e.numpy(values),reference_jacobian=ref_jac,jacobian=e.numpy(jac))
        write_json(args.out/"result.json",{"passed":passed,"transition_max_abs_MHz":maximum,
            "transition_tolerance_MHz":tolerance,"spectrum_max_abs":spectrum_error,
            "spectrum_tolerance":spectral_tolerance,"jacobian_max_abs":jac_error,
            "jacobian_tolerance":jac_tolerance,"scope":"manufactured implementation fidelity"})
        return 0 if passed else 2
    from experiments.vector_direct_screen.baseline import fit_chunk,fit_counts,policy_device
    counts=reference_spectra*CFG["photons_per_bin"]
    if args.phase=="solver":
        fitted=fit_chunk(e,e.array(counts),mode="affine",width=2.)
        predicted=e.numpy(fitted["parameters"])
        error=np.linalg.norm(predicted[:,:3]-p[:,:3],axis=1)
        residual=np.max(np.abs(e.numpy(e.spectrum(fitted["parameters"]))-reference_spectra),axis=1)
        passed=bool(np.isfinite(predicted).all() and (error<=CFG["noiseless_field_tolerance_uT"]).all()
            and (residual<=CFG["noiseless_spectrum_max_abs"]).all())
        np.savez_compressed(args.out/"solver.npz",parameters=p,counts=counts,predictions=predicted,
            field_error_uT=error,spectrum_error=residual,accepted=e.numpy(fitted["accepted"]),
            converged=e.numpy(fitted["converged"]))
        write_json(args.out/"result.json",{"passed":passed,"max_field_error_uT":float(error.max()),
            "max_spectrum_error":float(residual.max()),"iterations":fitted["iterations"],
            "accepted":e.numpy(fitted["accepted"]).tolist(),"converged":e.numpy(fitted["converged"]).tolist(),
            "scope":"five fixed noiseless manufactured cases; no population evidence"})
        return 0 if passed else 2
    # Profile only repeats manufactured cases. This is never a field-accuracy evaluation.
    index=np.arange(args.batch)%len(p)
    batch=counts[index]
    setup_start=time.perf_counter()
    device_counts=e.array(batch)
    e.affine_calibration()
    e.sync()
    setup_seconds=time.perf_counter()-setup_start
    policy_device(e,device_counts,args.variant) # one separately disclosed warm-up
    e.sync()
    timings=[]
    last=None
    for repetition in range(3):
        e.sync()
        start=time.perf_counter()
        resident=policy_device(e,device_counts,args.variant)
        e.sync()
        resident_seconds=time.perf_counter()-start
        start=time.perf_counter()
        last=fit_counts(batch,backend=args.backend,device=args.device,dtype=args.dtype,variant=args.variant)
        e.sync()
        host_seconds=time.perf_counter()-start
        row={"repetition":repetition,"resident_seconds":resident_seconds,"end_to_end_seconds":host_seconds,
             "resident_spectra_per_second":args.batch/resident_seconds,
             "end_to_end_spectra_per_second":args.batch/host_seconds,
             "million_spectra_seconds_extrapolated":host_seconds*1000000/args.batch}
        timings.append(row)
        write_json(args.out/("timing-"+str(repetition)+".json"),row)
    np.savez_compressed(args.out/"profile.npz",parameters=p[index],counts=batch,
        predictions=last["parameters"],accepted=last["accepted"],fallback=last["fallback"],
        reduced_deviance=last["reduced_deviance"])
    write_json(args.out/"result.json",{"status":"profile_only_no_population_verdict","timings":timings,
        "calibration_and_initial_transfer_seconds":setup_seconds,"warmup_calls":1,
        "fallback_count":int(last["fallback"].sum()),"accepted_count":int(last["accepted"].sum()),
        "million_spectra_note":"Linear extrapolation from fixed batch, not a measured million-spectrum run",
        "scope":"manufactured repeated inputs; caches and nuisance diversity require later population check"})
    return 0

if __name__=="__main__":
    raise SystemExit(main())
