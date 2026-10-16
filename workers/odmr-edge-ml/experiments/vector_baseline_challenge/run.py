"""Supervised fixtures or one fresh challenge. No training entry point."""
import argparse,json,sys,time,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.vector_baseline_challenge.access import authorize,source_pins,sha,frozen_inputs
from experiments.vector_initializer_development.access import assert_cuda_environment

def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--gate",required=True,type=Path);parser.add_argument("--approval-sha256",required=True)
    parser.add_argument("--out",required=True,type=Path);parser.add_argument("--phase",required=True,choices=("challenge_fixtures","challenge_development"));a=parser.parse_args()
    gate,context=authorize(a.gate,a.approval_sha256,a.phase)
    a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/"started.json",{"phase":a.phase,"approval_sha256":a.approval_sha256,"reservation_id":context["central_reservation_id"]})
    def manifest(status):write(a.out/"manifest.json",{"status":status,"source_sha256":source_pins(),"files":{p.name:sha(p) for p in sorted(a.out.iterdir()) if p.is_file() and p.name!="manifest.json"}})
    if a.phase=="challenge_fixtures":
        import unittest
        from experiments.vector_baseline_challenge import test_contracts
        with (a.out/"fixtures.txt").open("w") as stream:r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_contracts))
        write(a.out/"result.json",{"passed":r.wasSuccessful(),"tests":r.testsRun,"failures":len(r.failures),"errors":len(r.errors)})
        manifest("complete" if r.wasSuccessful() else "failed");return 0 if r.wasSuccessful() else 2
    if "Status: FROZEN_BASELINE_CHALLENGE" not in (Path(__file__).parent/"protocol.md").read_text():raise PermissionError("Challenge is not frozen")
    inputs=frozen_inputs(gate);certificate=Path(gate["seed_certificate_path"])
    if sha(certificate)!=gate["seed_certificate_sha256"]:raise PermissionError("Seed custody mismatch")
    cublas=assert_cuda_environment()
    import numpy as np
    import torch
    from experiments.vector_baseline_challenge import data,methods,evaluation
    from experiments.vector_initializer_development import learning
    from experiments.vector_direct_screen.physics import Engine,CFG
    if not torch.cuda.is_available():raise RuntimeError("CUDA required")
    torch.cuda.set_per_process_memory_fraction(min(1.,16*1024**3/torch.cuda.get_device_properties(0).total_memory),0)
    torch.use_deterministic_algorithms(True);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    start=time.perf_counter();fresh,identities=data.generate(json.loads(certificate.read_text()))
    np.savez_compressed(a.out/"counts-00.npz",counts=fresh["counts"])
    np.savez_compressed(a.out/"labels.npz",**{k:v for k,v in fresh.items() if k!="counts"})
    write(a.out/"records.json",[{"row":i,"record_id":f"B{i:04d}","parameter_sha256":h} for i,h in enumerate(identities)])
    write(a.out/"data-schema.json",{"schema":1,"n":4096,"bins":512,"counts_dtype":"int64","blocks":[{"file":"counts-00.npz","start":0,"stop":4096}],"noise":"Poisson(2000000 * frozen fluorescence)","regime":"full_B"})
    generation=time.perf_counter()-start
    for name,path in inputs.items():shutil.copyfile(path,a.out/("p1-"+name))
    original=json.loads(inputs["setup.json"].read_text())["total_candidate_setup_seconds"]
    stats={};timings={};setup={"fresh_generation_and_save_seconds":generation,"original_p1_candidate_setup_seconds":original,"method_setup_seconds":{}}
    manifest("data_complete")
    with torch.no_grad():
        for name in methods.METHODS:
            start=time.perf_counter();engine=Engine("torch","cuda","float64");engine.affine_calibration()
            mixed=None;neural=None
            if name.endswith("f32"):
                mixed=Engine("torch","cuda","float32");mixed.affine_calibration()
            if name in methods.NEURAL:
                model=learning.build_model(torch);model.load_state_dict(torch.load(inputs["model-final.pt"],map_location="cpu",weights_only=True))
                with np.load(inputs["scaling.npz"],allow_pickle=False) as z:
                    neural=learning.initializer(torch,model,z["feature_mean"],z["feature_std"],z["target_center"],z["target_scale"])
            engine.sync();setup["method_setup_seconds"][name]=time.perf_counter()-start
            # Each method owns the same persistent calibration allowance and one warmup.
            methods.policy(engine,engine.array(fresh["counts"]),name,neural,mixed);engine.sync()
            elapsed=[];outputs=[];last=None
            for repetition in range(3):
                engine.sync();start=time.perf_counter()
                last=methods.policy(engine,engine.array(fresh["counts"]),name,neural,mixed);engine.sync()
                output={k:engine.numpy(last[k]) for k in methods.COMMON};engine.sync()
                elapsed.append(time.perf_counter()-start);outputs.append(output)
            # Diagnostic exports and fitted-rate recomputation are outside service timing.
            saved={k:engine.numpy(v) for k,v in last.items()}
            def guard_rates(params):
                chunks=[]
                for offset in range(0,len(params),1024):
                    q=params[offset:offset+1024]
                    good=torch.isfinite(q).all(1)&((q>=engine.lower)&(q<=engine.upper)).all(1)
                    safe=torch.where(good[:,None],q,engine.array([CFG["nominal"]]))
                    chunks.append(engine.numpy(engine.spectrum(safe)))
                return np.concatenate(chunks)
            saved["fitted_rates"]=guard_rates(last["parameters"])
            if "proposal_parameters" in last:saved["proposal_guard_rates"]=guard_rates(last["proposal_parameters"])
            saved["field_error_uT"]=np.linalg.norm(saved["parameters"][:,:3]-fresh["parameters"][:,:3],axis=1)
            np.savez_compressed(a.out/(name+"-predictions.npz"),**saved)
            np.savez_compressed(a.out/(name+"-timing.npz"),indices=np.arange(4096),**{k:np.stack([v[k] for v in outputs]) for k in methods.COMMON})
            if not np.isfinite(saved["parameters"]).all():manifest("scientific_failure");raise RuntimeError("Nonfinite outputs preserved; no case exclusion")
            stats[name]=evaluation.metrics(saved["parameters"],fresh["parameters"],saved["accepted"],saved["fallback"])
            timings[name]={"host_to_host_seconds":elapsed,"batch":4096,"chunk":1024,"warmups":1,"repeats":3,
                "model_dtype":"float32" if name in methods.NEURAL else None,"refinement_dtype":"float32" if name.endswith("f32") else (None if name=="neural0" else "float64"),
                "guard_dtype":"float64","fallback_dtype":"float64","output_dtype":"float64",
                "service_outputs":list(methods.COMMON),"includes_transfer_cast_guard_fallback":True,
                "host_repeat_metrics":[evaluation.metrics(v["parameters"],fresh["parameters"],v["accepted"],v["fallback"]) for v in outputs]}
            write(a.out/"metrics.json",stats);write(a.out/"timings.json",timings);write(a.out/"setup.json",setup);manifest("evaluating")
            del engine,mixed,neural,last
        write(a.out/"result.json",evaluation.decide(stats,timings,setup))
    write(a.out/"provenance.json",{"p1_frozen_commit":gate["p1_frozen_commit"],"frozen_input_sha256":{k:sha(v) for k,v in inputs.items()},
        "seed_certificate_sha256":sha(certificate),"challenge_source_sha256":source_pins(),"cublas_workspace_config":cublas,
        "python":sys.version,"numpy":np.__version__,"torch":torch.__version__,"cuda":torch.version.cuda,"gpu":torch.cuda.get_device_name(0),
        "new_latents":4096,"new_candidates":["affine2_f64","affine2_f32","affine3_f32","neural0"],"training":False,"old_p1_case_access":False,
        "guard_dtype":"float64","fallback_dtype":"float64","no_case_exclusions":True})
    manifest("complete");return 0
if __name__=="__main__":raise SystemExit(main())
