"""Independent saved arithmetic only: no generator, model loading, or inference."""
import argparse,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.vector_baseline_challenge.access import authorize,source_pins,sha
NAMES=("lm","affine3","tied12","neural1","affine2_f64","affine2_f32","affine3_f32","neural0")
CLASSICAL=("lm","affine3","tied12","affine2_f64","affine2_f32","affine3_f32")
NEW=("affine2_f64","affine2_f32","affine3_f32","neural0")

def close(a,b,tol=1e-10):
    if not math.isclose(float(a),float(b),abs_tol=tol,rel_tol=tol):raise AssertionError((a,b))

def label_identity(labels,records,lower,upper):
    import numpy as np
    if labels.shape!=(4096,8) or labels.dtype!=np.float64 or not np.isfinite(labels).all() or not np.all((labels>=lower)&(labels<=upper)):raise AssertionError("Wrong full-B labels")
    expected=[{"row":i,"record_id":f"B{i:04d}","parameter_sha256":hashlib.sha256(row.astype("<f8").tobytes()).hexdigest()} for i,row in enumerate(labels)]
    if records!=expected or len({r["parameter_sha256"] for r in expected})!=4096:raise AssertionError("Missing, duplicate or changed label identity")

def guard_from_saved(counts,parameters,rates,lower,upper):
    import numpy as np
    from scipy.special import xlogy
    if parameters.dtype!=np.float64 or rates.dtype!=np.float64 or rates.shape!=(len(counts),512) or not np.isfinite(rates).all() or np.any(rates<=0):raise AssertionError("Wrong saved physical precision or rates")
    mu=2000000*rates
    reduced=2*np.sum(xlogy(counts,counts/mu)-counts+mu,axis=1)/504
    valid=np.isfinite(parameters).all(1)&np.all((parameters>=lower)&(parameters<=upper),axis=1)
    return valid&np.isfinite(reduced)&(reduced<=2),reduced

def metric(parameters,truth,accepted,fallback):
    import numpy as np
    delta=parameters[:,:3]-truth[:,:3];error=np.sqrt(np.einsum("ni,ni->n",delta,delta))
    return {"n":len(error),"mean_uT":float(np.mean(error)),"p95_uT":float(np.percentile(error,95)),"rmse_uT":float(np.sqrt(np.mean(error*error))),"max_uT":float(np.max(error)),"rejections":int(np.count_nonzero(~accepted)),"fallbacks":int(np.count_nonzero(fallback))},error

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--gate",required=True,type=Path);parser.add_argument("--approval-sha256",required=True)
    parser.add_argument("--input",required=True,type=Path);parser.add_argument("--out",required=True,type=Path);a=parser.parse_args()
    gate,_=authorize(a.gate,a.approval_sha256,"challenge_verification")
    if sha(a.input/"manifest.json")!=gate["input_manifest_sha256"]:raise PermissionError("Wrong saved manifest")
    manifest=json.loads((a.input/"manifest.json").read_text());assert manifest["status"]=="complete" and manifest["source_sha256"]==source_pins()
    assert set(manifest["files"])=={p.name for p in a.input.iterdir() if p.is_file() and p.name!="manifest.json"}
    for name,digest in manifest["files"].items():
        if Path(name).name!=name or sha(a.input/name)!=digest:raise AssertionError("Changed artifact")
    import numpy as np
    from experiments.vector_direct_screen.physics import CFG
    schema=json.loads((a.input/"data-schema.json").read_text())
    assert schema=={"schema":1,"n":4096,"bins":512,"counts_dtype":"int64","blocks":[{"file":"counts-00.npz","start":0,"stop":4096}],"noise":"Poisson(2000000 * frozen fluorescence)","regime":"full_B"}
    with np.load(a.input/"counts-00.npz",allow_pickle=False) as z:
        assert z.files==["counts"];counts=z["counts"]
    assert counts.shape==(4096,512) and counts.dtype==np.int64 and np.all(counts>=0)
    with np.load(a.input/"labels.npz",allow_pickle=False) as z:
        assert set(z.files)=={"parameters","mean_check_indices","rates_at_checks","independent_rates"};truth=z["parameters"]
        np.testing.assert_array_equal(z["mean_check_indices"],np.linspace(0,4095,32,dtype=int))
        np.testing.assert_allclose(z["rates_at_checks"],z["independent_rates"],rtol=0,atol=1e-11)
    label_identity(truth,json.loads((a.input/"records.json").read_text()),CFG["lower"],CFG["upper"])
    provenance=json.loads((a.input/"provenance.json").read_text())
    assert provenance["new_candidates"]==list(NEW) and provenance["new_latents"]==4096
    assert not provenance["training"] and not provenance["old_p1_case_access"] and provenance["no_case_exclusions"]
    assert provenance["p1_frozen_commit"]==gate["p1_frozen_commit"] and provenance["challenge_source_sha256"]==source_pins()
    assert provenance["guard_dtype"]==provenance["fallback_dtype"]=="float64" and provenance["cublas_workspace_config"]==":4096:8"
    for name in ("model-final.pt","scaling.npz","setup.json"):
        assert sha(a.input/("p1-"+name))==gate["frozen_inputs"][name]["sha256"]==provenance["frozen_input_sha256"][name]
    stats=json.loads((a.input/"metrics.json").read_text());timings=json.loads((a.input/"timings.json").read_text())
    assert set(stats)==set(timings)==set(NAMES);rebuilt={}
    for name in NAMES:
        with np.load(a.input/(name+"-predictions.npz"),allow_pickle=False) as z:pred={k:z[k] for k in z.files}
        params=pred["parameters"];assert params.shape==(4096,8) and np.isfinite(params).all()
        for key in ("accepted","fallback"):assert pred[key].dtype==np.bool_ and pred[key].shape==(4096,)
        accepted,reduced=guard_from_saved(counts,params,pred["fitted_rates"],CFG["lower"],CFG["upper"])
        np.testing.assert_array_equal(accepted,pred["accepted"]);np.testing.assert_allclose(reduced,pred["reduced_deviance"],rtol=0,atol=1e-6)
        if name in NEW:
            proposal=pred["proposal_parameters"];assert proposal.shape==(4096,8)
            pa,pr=guard_from_saved(counts,proposal,pred["proposal_guard_rates"],CFG["lower"],CFG["upper"])
            np.testing.assert_array_equal(pa,pred["proposal_accepted"]);np.testing.assert_array_equal(~pa,pred["fallback"])
            np.testing.assert_allclose(pr,pred["proposal_reduced_deviance"],rtol=0,atol=1e-6)
            np.testing.assert_array_equal(params[pa],proposal[pa])
            attempts=pred["refinement_accepts"];limit={"affine2_f64":2,"affine2_f32":2,"affine3_f32":3,"neural0":0}[name]
            assert attempts.shape==(4096,) and attempts.dtype.kind in "iu" and np.all((attempts>=0)&(attempts<=limit))
        if name=="lm":assert np.all(pred["fallback"])
        if name=="tied12":
            for key in ("line_valid","line_converged","inverse_valid","inverse_converged"):assert pred[key].dtype==np.bool_ and pred[key].shape==(4096,)
            assert np.all(pred["fallback"]|(pred["line_valid"]&pred["inverse_valid"]))
        s,error=metric(params,truth,accepted,pred["fallback"]);rebuilt[name]=s
        np.testing.assert_allclose(error,pred["field_error_uT"],rtol=0,atol=1e-12)
        for key,value in s.items():close(value,stats[name][key],1e-12)
        t=timings[name];assert (t["batch"],t["chunk"],t["warmups"],t["repeats"])==(4096,1024,1,3)
        assert t["model_dtype"]==("float32" if name.startswith("neural") else None)
        assert t["refinement_dtype"]==("float32" if name.endswith("f32") else (None if name=="neural0" else "float64"))
        assert t["guard_dtype"]==t["fallback_dtype"]==t["output_dtype"]=="float64"
        assert t["service_outputs"]==["parameters","accepted","reduced_deviance","fallback"] and t["includes_transfer_cast_guard_fallback"]
        assert len(t["host_to_host_seconds"])==3 and all(math.isfinite(v) and v>0 for v in t["host_to_host_seconds"])
        with np.load(a.input/(name+"-timing.npz"),allow_pickle=False) as z:
            assert set(z.files)=={"indices","parameters","accepted","reduced_deviance","fallback"}
            np.testing.assert_array_equal(z["indices"],np.arange(4096));assert z["parameters"].dtype==np.float64 and z["parameters"].shape==(3,4096,8)
            for i in range(3):
                np.testing.assert_allclose(z["parameters"][i],params,rtol=0,atol=1e-5)
                for key in ("accepted","fallback"):np.testing.assert_array_equal(z[key][i],pred[key])
                np.testing.assert_allclose(z["reduced_deviance"][i],pred["reduced_deviance"],rtol=0,atol=1e-6)
                repeated,_=metric(z["parameters"][i],truth,z["accepted"][i],z["fallback"][i])
                for key,value in repeated.items():close(value,t["host_repeat_metrics"][i][key],1e-12)
    setup=json.loads((a.input/"setup.json").read_text());result=json.loads((a.input/"result.json").read_text())
    old=json.loads((a.input/"p1-setup.json").read_text())["total_candidate_setup_seconds"]
    close(setup["original_p1_candidate_setup_seconds"],old)
    assert set(setup["method_setup_seconds"])==set(NAMES) and all(math.isfinite(v) and v>0 for v in setup["method_setup_seconds"].values())
    adequate=[n for n in CLASSICAL if all(rebuilt[n][k]<=1.05*rebuilt["lm"][k] for k in ("mean_uT","p95_uT")) and rebuilt[n]["rejections"]<=rebuilt["lm"]["rejections"]]
    med=lambda n:sorted(timings[n]["host_to_host_seconds"])[1]
    best=min(adequate,key=lambda n:(med(n),CLASSICAL.index(n)))
    assert result["adequate_classical"]==adequate and result["fastest_adequate_classical"]==best
    close(result["classical_host_seconds"],med(best));close(result["classical_seconds_per_million"],med(best)/4096*1e6)
    assert set(result["neural_routes"])=={"neural1","neural0"};passes=[]
    for name in ("neural1","neural0"):
        rec=result["neural_routes"][name]
        accuracy=all(rebuilt[name][k]<=1.05*min(rebuilt[n][k] for n in adequate) for k in ("mean_uT","p95_uT")) and rebuilt[name]["rejections"]<=min(rebuilt[n]["rejections"] for n in adequate)
        ratio=med(best)/med(name);saving=(med(best)-med(name))/4096;cost=old+setup["method_setup_seconds"][name]
        assert rec["matched_accuracy_pass"]==accuracy
        for key,value in (("speedup",ratio),("host_seconds",med(name)),("seconds_per_million",med(name)/4096*1e6),("seconds_saved_per_million",saving*1e6),("setup_cost_seconds",cost)):close(rec[key],value)
        assert rec["break_even_spectra"]==(math.ceil(cost/saving) if saving>0 else None)
        expected=accuracy and ratio>=2 and saving>0;assert rec["continuation_pass"]==expected;passes.append(expected)
    assert result["any_neural_continuation"]==any(passes) and result["practical_adoption"] is False and result["confirmation_authorized"] is False
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/"verification.json").write_text(json.dumps({"passed":True,"input_manifest_sha256":sha(a.input/"manifest.json"),"recomputed_metrics":rebuilt,"fastest_adequate_classical":best,"neural_routes":result["neural_routes"],"no_inference":True},indent=2)+"\n")
    return 0
if __name__=="__main__":raise SystemExit(main())
