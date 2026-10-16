"""One fixed CPU/GPU64 manufactured parity pass, never a population benchmark."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.vector_line_comparator.access import authorize,source_pins


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--gate",type=Path,required=True)
    parser.add_argument("--approval-sha256",required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    gate,context=authorize(args.gate,args.approval_sha256,"parity")
    expected={"phase":"parity","backend":"torch","device":"cuda","dtype":"float64","cases":5,"chunk_size":1024}
    if gate.get("execution")!=expected:
        raise PermissionError("Exact fixed parity execution required")
    args.out.mkdir(parents=True,exist_ok=False)
    import numpy as np
    import torch
    from experiments.vector_direct_screen.physics import CFG,Engine
    from experiments.vector_line_comparator.comparator import TiedLines,fit_counts
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; no CPU substitution permitted")
    # Five deterministic cases. All variation is fixed before any numerical output.
    params=np.broadcast_to(CFG["nominal"],(5,8)).copy()
    patterns=((0,0,0,0),(1,1,1,1),(0,1,0,1),(1,0,1,0))
    for row,sides in enumerate(patterns,1):
        for column,side in enumerate(sides):
            params[row,column]=(CFG["lower"] if side==0 else CFG["upper"])[column]
        for column in range(4,8):
            params[row,column]=(CFG["lower"] if row%2 else CFG["upper"])[column]
    cpu,gpu=Engine("torch","cpu","float64"),Engine("torch","cuda","float64")
    cmodel,gmodel=TiedLines(cpu),TiedLines(gpu)
    cp,gp=cpu.array(params),gpu.array(params)
    cvalue,cjac=cmodel.spectrum(cmodel.from_physical(cp),True)
    gvalue,gjac=gmodel.spectrum(gmodel.from_physical(gp),True)
    cf,gf=cpu.transitions(cp),gpu.transitions(gp)
    arrays={"parameters":params,"cpu_values":cpu.numpy(cvalue),"gpu_values":gpu.numpy(gvalue),
            "cpu_jacobian":cpu.numpy(cjac),"gpu_jacobian":gpu.numpy(gjac),
            "cpu_transitions":cpu.numpy(cf),"gpu_transitions":gpu.numpy(gf)}
    counts=cpu.numpy(cpu.spectrum(cp))*CFG["photons_per_bin"]
    arrays["counts"]=counts
    # Complete host-in/host-out policy once per device, including every fallback.
    cr=fit_counts(counts,device="cpu",dtype="float64",chunk_size=1024)
    gr=fit_counts(counts,device="cuda",dtype="float64",chunk_size=1024)
    arrays.update({"cpu_"+k:v for k,v in cr.items()})
    arrays.update({"gpu_"+k:v for k,v in gr.items()})
    values_error=float(np.max(np.abs(arrays["cpu_values"]-arrays["gpu_values"])))
    jac_error=float(np.max(np.abs(arrays["cpu_jacobian"]-arrays["gpu_jacobian"])))
    center_error=float(np.max(np.abs(arrays["cpu_transitions"]-arrays["gpu_transitions"])))
    scaled_error=float(np.max(np.abs(cr["parameters"]-gr["parameters"])/np.asarray(CFG["scales"])))
    flags={k:bool(np.array_equal(cr[k],gr[k])) for k in cr if cr[k].dtype==np.dtype(bool)}
    physical_errors={device:float(np.max(np.linalg.norm(result["parameters"][:,:3]-params[:,:3],axis=1)))
                     for device,result in (("cpu",cr),("gpu",gr))}
    checks={"values":values_error<=1e-11,"jacobian":jac_error<=1e-10,
            "transitions":center_error<=CFG["fidelity_float64_MHz"],
            "complete_parameters":scaled_error<=CFG["relative_step_tolerance"],
            "complete_flags":all(flags.values()),
            "cpu_accepted":bool(cr["accepted"].all()),"gpu_accepted":bool(gr["accepted"].all()),
            "cpu_noiseless_accuracy":physical_errors["cpu"]<=CFG["noiseless_field_tolerance_uT"],
            "gpu_noiseless_accuracy":physical_errors["gpu"]<=CFG["noiseless_field_tolerance_uT"],
            "finite_outputs":all(bool(np.isfinite(v).all()) for v in arrays.values())}
    np.savez_compressed(args.out/"parity.npz",**arrays)
    result={"passed":all(checks.values()),"checks":checks,"flag_agreement":flags,
            "values_max_abs":values_error,"jacobian_max_abs":jac_error,
            "transitions_max_abs_MHz":center_error,"parameter_max_scaled_abs":scaled_error,
            "parameter_tolerance_basis":"existing relative_step_tolerance applied in fixed parameter scales",
            "noiseless_field_max_error_uT":physical_errors,
            "source_sha256":source_pins(),"approval_sha256":args.approval_sha256,
            "reservation_id":context["central_reservation_id"],
            "scope":"five fixed noiseless manufactured cases; no native speed or population evidence"}
    (args.out/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return 0 if result["passed"] else 2


if __name__=="__main__":
    raise SystemExit(main())
