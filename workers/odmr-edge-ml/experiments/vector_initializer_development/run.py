"""One registered P1 job. Imports and signals occur after the numerical guard."""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.vector_initializer_development.access import authorize,source_pins,assert_cuda_environment

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+"\n")

def main():
    p=argparse.ArgumentParser();p.add_argument("--gate",required=True,type=Path)
    p.add_argument("--approval-sha256",required=True);p.add_argument("--out",required=True,type=Path)
    p.add_argument("--phase",required=True,choices=("p1_fixtures","p1_development"));a=p.parse_args()
    gate,context=authorize(a.gate,a.approval_sha256,a.phase)
    cublas_config=assert_cuda_environment();a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/"started.json",{"phase":a.phase,"approval_sha256":a.approval_sha256,
        "reservation_id":context["central_reservation_id"],"p1_source_sha256":source_pins()})
    def manifest(status):write(a.out/"manifest.json",{"status":status,"source_sha256":source_pins(),
        "files":{f.name:sha(f) for f in sorted(a.out.iterdir()) if f.is_file() and f.name!="manifest.json"}})
    if a.phase=="p1_fixtures":
        import unittest
        from experiments.vector_initializer_development import test_contracts
        with (a.out/"fixtures.txt").open("w") as stream:
            r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_contracts))
        write(a.out/"result.json",{"passed":r.wasSuccessful(),"tests":r.testsRun,"failures":len(r.failures),"errors":len(r.errors)})
        manifest("complete" if r.wasSuccessful() else "failed");return 0 if r.wasSuccessful() else 2
    certificate=Path(gate["seed_certificate_path"])
    if sha(certificate)!=gate["seed_certificate_sha256"]:raise PermissionError("Wrong seed custody")
    import numpy as np
    import torch
    from experiments.vector_initializer_development import learning,methods,evaluation
    from experiments.vector_direct_screen.physics import Engine
    if not torch.cuda.is_available():raise RuntimeError("CUDA is mandatory")
    torch.cuda.set_per_process_memory_fraction(min(1.,16*1024**3/torch.cuda.get_device_properties(0).total_memory),0)
    torch.use_deterministic_algorithms(True);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    setup_start=time.perf_counter();data=learning.generate(json.loads(certificate.read_text()))
    learning.save_data(data,a.out);generation_seconds=time.perf_counter()-setup_start
    manifest("data_complete")
    train_start=time.perf_counter()
    model,mean,std,center,scale,history=learning.train(torch,data,learning.seed_values(json.loads(certificate.read_text()))[-1],a.out,
        lambda history:write(a.out/"training-history.json",history))
    torch.cuda.synchronize();training_seconds=time.perf_counter()-train_start
    model_setup_start=time.perf_counter();model=learning.build_model(torch)
    model.load_state_dict(torch.load(a.out/"model-final.pt",map_location="cpu",weights_only=True))
    neural=learning.initializer(torch,model,mean,std,center,scale)
    torch.cuda.synchronize();model_setup_seconds=time.perf_counter()-model_setup_start
    setup_seconds=time.perf_counter()-setup_start
    setup={"generation_and_save_seconds":generation_seconds,"training_and_checkpoint_seconds":training_seconds,
        "neural_load_scaling_seconds":model_setup_seconds,"total_candidate_setup_seconds":setup_seconds}
    write(a.out/"setup.json",setup);manifest("trained")
    stats={};timings={};method_setup={};counts=data["validation_counts"]
    with torch.no_grad():
        for name in methods.METHODS:
            setup_clock=time.perf_counter();engine=Engine("torch","cuda","float64")
            engine.affine_calibration();engine.sync();method_setup[name]=time.perf_counter()-setup_clock
            result=methods.policy(engine,engine.array(counts),name,neural)
            engine.sync();saved={k:engine.numpy(v) for k,v in result.items()}
            if not np.isfinite(saved["parameters"]).all():raise RuntimeError("Nonfinite predictions")
            rates=[]
            for start in range(0,len(counts),1024):rates.append(engine.numpy(engine.spectrum(result["parameters"][start:start+1024])))
            saved["fitted_rates"]=np.concatenate(rates)
            saved["field_error_uT"]=np.linalg.norm(saved["parameters"][:,:3]-data["validation_parameters"][:,:3],axis=1)
            np.savez_compressed(a.out/(name+"-predictions.npz"),**saved)
            stats[name]=evaluation.metrics(saved["parameters"],data["validation_parameters"],saved["accepted"],saved["fallback"])
            timings[name]={}
            for batch in evaluation.BATCHES:
                indexes=np.arange(batch)%len(counts);host_counts=counts[indexes]
                # Warm all paths equally before measuring. No target labels are provided.
                methods.policy(engine,engine.array(host_counts),name,neural);engine.sync()
                host_times=[];host_outputs=[]
                for _ in range(evaluation.REPEATS):
                    torch.cuda.synchronize();start=time.perf_counter()
                    e=engine
                    r=methods.policy(e,e.array(host_counts),name,neural);e.sync()
                    output={k:e.numpy(v) for k,v in r.items()};torch.cuda.synchronize()
                    host_times.append(time.perf_counter()-start);host_outputs.append(output)
                e=engine;device_counts=e.array(host_counts)
                methods.policy(e,device_counts,name,neural);e.sync();resident=[]
                for _ in range(evaluation.REPEATS):
                    start=time.perf_counter();methods.policy(e,device_counts,name,neural);e.sync();resident.append(time.perf_counter()-start)
                np.savez_compressed(a.out/(name+f"-timing-{batch}.npz"),indices=indexes,
                    **{k:np.stack([r[k] for r in host_outputs]) for k in host_outputs[0]})
                timings[name][str(batch)]={"host_to_host_seconds":host_times,"resident_seconds":resident,
                    "host_repeat_metrics":[evaluation.metrics(r["parameters"],data["validation_parameters"][indexes],r["accepted"],r["fallback"]) for r in host_outputs],
                    "unique_validation_inputs":min(batch,len(counts)),"repeats_for_timing_only":batch>len(counts),"model_dtype":"float32" if name=="neural1" else None,"physical_dtype":"float64","output_dtype":"float64","chunk":1024}
            write(a.out/"metrics.json",stats);write(a.out/"timings.json",timings);manifest("evaluating")
    setup["persistent_engine_calibration_seconds"]=method_setup;write(a.out/"setup.json",setup)
    result=evaluation.opportunity_gate(stats,timings,setup_seconds+method_setup["neural1"],method_setup)
    write(a.out/"result.json",result)
    write(a.out/"provenance.json",{"seed_certificate_sha256":sha(certificate),"python":sys.version,
        "numpy":np.__version__,"torch":torch.__version__,"cuda":torch.version.cuda,"gpu":torch.cuda.get_device_name(0),
        "data_counts":{"train":32768,"validation":2048},"noise":"Poisson(2000000 * frozen fluorescence)",
        "cublas_workspace_config":cublas_config,"train_dtype":"float32","model_dtype":"float32","input_normalization_dtype":"float32","physical_dtype":"float64","output_dtype":"float64","epochs":20,"checkpoint_selection":"final only",
        "all_validation_cases_retained":True,"source_sha256":source_pins(),"no_p0_inputs":True})
    manifest("complete");return 0

if __name__=="__main__":raise SystemExit(main())
