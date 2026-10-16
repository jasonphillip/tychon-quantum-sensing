"""Independent saved-output arithmetic. No generator, training, or inference."""
import argparse,hashlib,json,sys,math
from pathlib import Path
from bundle import PublicBundle,parse_args

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_close(a,b,tolerance=1e-10):
    if not math.isclose(float(a),float(b),rel_tol=tolerance,abs_tol=tolerance):raise AssertionError((a,b))

def main():
    a=parse_args()
    bundle=PublicBundle(a.bundle,a.expected_manifest_sha256,a.config,"p1",
        "experiments/vector_initializer_development/verify_saved.py","a10ed1603a4ba263d78d4012e80abf3a182b117d3d1988f5b102338b13a3f353")
    a.input=bundle
    import numpy as np
    from scipy.special import xlogy
    CFG=bundle.config
    with np.load(a.input/"data.npz",allow_pickle=False) as z:data={k:z[k] for k in z.files}
    schema=json.loads((a.input/"data-schema.json").read_text())
    assert schema["schema"]==1 and schema["counts_per_file_max_rows"]==4096 and schema["frequency_bins"]==512 and schema["counts_dtype"]=="int64"
    assert set(schema["blocks"])=={"train","validation"}
    for split,n in (("train",32768),("validation",2048)):
        expected=[{"file":f"{split}-counts-{i:02d}.npz","start":start,"stop":min(start+4096,n)} for i,start in enumerate(range(0,n,4096))]
        assert schema["blocks"][split]==expected
        chunks=[]
        for block in expected:
            with np.load(a.input/block["file"],allow_pickle=False) as z:
                assert z.files==["counts"] and z["counts"].shape==(block["stop"]-block["start"],512) and z["counts"].dtype==np.int64
                chunks.append(z["counts"])
        data[split+"_counts"]=np.concatenate(chunks,axis=0)
    train=data["train_counts"];val=data["validation_counts"];truth=data["validation_parameters"]
    all_ids=[]
    for key,n in (("train",32768),("validation",2048)):
        counts=data[key+"_counts"];labels=data[key+"_parameters"]
        assert counts.shape==(n,512) and counts.dtype.kind in "iu" and np.all(counts>=0)
        assert labels.shape==(n,8) and np.isfinite(labels).all() and np.all(labels>=CFG["lower"]) and np.all(labels<=CFG["upper"])
        all_ids.extend(hashlib.sha256(row.astype("<f8").tobytes()).hexdigest() for row in labels)
        np.testing.assert_array_equal(data[key+"_mean_check_indices"],np.linspace(0,n-1,32,dtype=int))
        np.testing.assert_allclose(data[key+"_independent_rates"],data[key+"_rates_at_checks"],rtol=0,atol=1e-11)
    assert len(set(all_ids))==32768+2048
    with np.load(a.input/"scaling.npz",allow_pickle=False) as z:
        np.testing.assert_allclose(z["feature_mean"],(train/2000000).mean(0),rtol=0,atol=1e-12)
        np.testing.assert_allclose(z["feature_std"],np.maximum((train/2000000).std(0),1e-6),rtol=0,atol=1e-12)
        np.testing.assert_array_equal(z["target_center"],(np.asarray(CFG["lower"])+CFG["upper"])/2)
        np.testing.assert_array_equal(z["target_scale"],(np.asarray(CFG["upper"])-CFG["lower"])/2)
    # Checkpoint bytes were hash-verified by PublicBundle; no Torch deserialization.
    # Original independent tensor shape/dtype/finiteness inspection remains provenance.
    provenance=json.loads((a.input/"provenance.json").read_text())
    for key,expected_dtype in (("train_dtype","float32"),("model_dtype","float32"),("input_normalization_dtype","float32"),("physical_dtype","float64"),("output_dtype","float64")):
        assert provenance[key]==expected_dtype
    history=json.loads((a.input/"training-history.json").read_text())
    assert [h["epoch"] for h in history]==list(range(1,21)) and all(math.isfinite(h["train_normalized_mse"]) for h in history)
    saved=json.loads((a.input/"metrics.json").read_text());timing=json.loads((a.input/"timings.json").read_text())
    names=("lm","affine1","affine3","affine5","tied12","neural1");assert set(saved)==set(timing)==set(names)
    rebuilt={}
    for name in names:
        with np.load(a.input/(name+"-predictions.npz"),allow_pickle=False) as z:pred={k:z[k] for k in z.files}
        parameters=pred["parameters"];assert parameters.dtype==np.float64 and parameters.shape==(2048,8) and np.isfinite(parameters).all()
        rates=pred["fitted_rates"];assert rates.shape==(2048,512) and np.all(rates>0)
        error=np.sqrt(np.einsum("ni,ni->n",parameters[:,:3]-truth[:,:3],parameters[:,:3]-truth[:,:3]))
        np.testing.assert_allclose(error,pred["field_error_uT"],rtol=0,atol=1e-12)
        reduced=2*np.sum(xlogy(val,val/(2000000*rates))-val+2000000*rates,axis=1)/504
        np.testing.assert_allclose(reduced,pred["reduced_deviance"],rtol=0,atol=1e-6)
        accepted=np.isfinite(reduced)&(reduced<=2)&np.all((parameters>=CFG["lower"])&(parameters<=CFG["upper"]),axis=1)
        np.testing.assert_array_equal(accepted,pred["accepted"])
        assert pred["fallback"].dtype.kind=="b" and pred["fallback"].shape==(2048,)
        if name=="tied12":
            for key in ("line_valid","line_converged","inverse_valid","inverse_converged"):
                assert pred[key].dtype.kind=="b" and pred[key].shape==(2048,)
            assert np.all(pred["fallback"]| (pred["line_valid"]&pred["inverse_valid"]))
        s={"n":2048,"mean_uT":float(np.mean(error)),"p95_uT":float(np.percentile(error,95)),
            "rmse_uT":float(np.sqrt(np.mean(error*error))),"max_uT":float(max(error)),
            "rejections":int(np.count_nonzero(~accepted)),"fallbacks":int(np.count_nonzero(pred["fallback"]))}
        for k,v in s.items():check_close(v,saved[name][k],1e-12)
        rebuilt[name]=s
        assert set(timing[name])=={"1","64","4096"}
        for batch in (1,64,4096):
            item=timing[name][str(batch)]
            assert item["physical_dtype"]==item["output_dtype"]=="float64" and item["chunk"]==1024
            assert item["model_dtype"]==("float32" if name=="neural1" else None)
            for key in ("host_to_host_seconds","resident_seconds"):
                assert len(item[key])==3 and all(math.isfinite(v) and v>0 for v in item[key])
            with np.load(a.input/(name+f"-timing-{batch}.npz"),allow_pickle=False) as z:
                np.testing.assert_array_equal(z["indices"],np.arange(batch)%2048)
                assert z["parameters"].dtype==np.float64 and z["parameters"].shape==(3,batch,8)
                for i in range(3):
                    delta=z["parameters"][i,:,:3]-truth[z["indices"],:3]
                    err=np.sqrt(np.einsum("ni,ni->n",delta,delta))
                    rebuilt_timing={"n":batch,"mean_uT":float(err.mean()),"p95_uT":float(np.percentile(err,95)),
                        "rmse_uT":float(np.sqrt(np.mean(err*err))),"max_uT":float(err.max()),
                        "rejections":int(np.count_nonzero(~z["accepted"][i])),"fallbacks":int(np.count_nonzero(z["fallback"][i]))}
                    for key,value in rebuilt_timing.items():check_close(value,item["host_repeat_metrics"][i][key],1e-12)
                    if batch==4096:
                        np.testing.assert_allclose(z["parameters"][i],parameters[z["indices"]],rtol=0,atol=1e-5)
                        np.testing.assert_array_equal(z["accepted"][i],pred["accepted"][z["indices"]])
                        np.testing.assert_array_equal(z["fallback"][i],pred["fallback"][z["indices"]])
                    if name=="tied12":
                        for key in ("line_valid","line_converged","inverse_valid","inverse_converged"):
                            assert z[key].shape==(3,batch) and z[key].dtype.kind=="b"
                            if batch==4096:np.testing.assert_array_equal(z[key][i],pred[key][z["indices"]])
    # Independent gate arithmetic: do not import the evaluator's decision function.
    full=rebuilt["lm"];adequate=[n for n in names[:-1] if rebuilt[n]["mean_uT"]<=1.05*full["mean_uT"] and rebuilt[n]["p95_uT"]<=1.05*full["p95_uT"] and rebuilt[n]["rejections"]<=full["rejections"]]
    neural=rebuilt["neural1"];accuracy=all(neural[k]<=1.05*min(rebuilt[n][k] for n in adequate) for k in ("mean_uT","p95_uT")) and neural["rejections"]<=min(rebuilt[n]["rejections"] for n in adequate)
    result=json.loads((a.input/"result.json").read_text());setup_record=json.loads((a.input/"setup.json").read_text());setup=setup_record["total_candidate_setup_seconds"]+setup_record["persistent_engine_calibration_seconds"]["neural1"]
    assert result["adequate_classical"]==adequate and result["matched_accuracy_pass"]==accuracy
    assert math.isfinite(setup) and setup>0
    speed_ok=True
    med=lambda n,b:sorted(timing[n][str(b)]["host_to_host_seconds"])[1]
    for batch in (1,64,4096):
        best=min(adequate,key=lambda n:(med(n,batch),names.index(n)));c=result["comparisons"][str(batch)]
        ratio=med(best,batch)/med("neural1",batch);saving=(med(best,batch)-med("neural1",batch))/batch
        assert c["fastest_adequate_classical"]==best;check_close(c["speedup"],ratio)
        check_close(c["seconds_saved_per_million"],saving*1000000)
        check_close(c["classical_seconds_per_million"],med(best,batch)/batch*1000000)
        check_close(c["neural_seconds_per_million"],med("neural1",batch)/batch*1000000)
        assert c["break_even_spectra"]==(math.ceil(setup/saving) if saving>0 else None)
        if batch==4096:speed_ok=ratio>=2 and saving>0
    assert result["continuation_pass"]==(accuracy and speed_ok)
    fastest=min(med(n,4096) for n in adequate);steps={"affine1":1,"affine3":3,"affine5":5,"tied12":80,"lm":120}
    chosen=min((n for n in adequate if med(n,4096)<=1.05*fastest),key=lambda n:(steps[n],n))
    classic=result["classical_engineering_opportunity"];assert classic["selected"]==chosen
    check_close(classic["speedup_vs_full_lm"],med("lm",4096)/med(chosen,4096))
    saving=(med("lm",4096)-med(chosen,4096))/4096
    check_close(classic["seconds_saved_per_million"],saving*1000000)
    calibration=setup_record["persistent_engine_calibration_seconds"][chosen]
    check_close(classic["calibration_setup_seconds"],calibration)
    assert classic["break_even_spectra_conservative_calibration"]==(math.ceil(calibration/saving) if saving>0 else None)
    assert classic["full_lm_speed_pass"]==(chosen!="lm" and med("lm",4096)>=2*med(chosen,4096))
    tied_adequate="tied12" in adequate;assert classic["tied12_adequate"]==tied_adequate
    check_close(classic["speedup_vs_tied12"],med("tied12",4096)/med(chosen,4096))
    tied_pass=not tied_adequate or med("tied12",4096)>=2*med(chosen,4096)
    assert classic["tied12_speed_requirement_pass"]==tied_pass
    expected_classical=chosen in ("affine1","affine3","affine5") and med("lm",4096)>=2*med(chosen,4096) and tied_pass
    assert classic["engineering_opportunity_pass"]==expected_classical and classic["adequate_tied_line_comparison"]=="INCLUDED"
    assert result["tied12_comparator_pending"] is False
    assert result["practical_adoption"] is False and result["confirmation_authorized"] is False
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/"verification.json").write_text(json.dumps({"passed":True,"public_manifest_sha256":bundle.public_manifest_sha256,"model_tensor_inspection_repeated":False,"input_manifest_sha256":digest(a.input/"manifest.json"),"recomputed_metrics":rebuilt,"continuation_pass":result["continuation_pass"],"classical_candidate":chosen,"no_inference":True},indent=2)+"\n")
    return 0

if __name__=="__main__":raise SystemExit(main())
