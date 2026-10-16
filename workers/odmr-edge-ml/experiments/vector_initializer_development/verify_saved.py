"""Independent saved-output arithmetic. No generator, training, or inference."""
import argparse,hashlib,json,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.vector_initializer_development.access import authorize

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_close(a,b,tolerance=1e-10):
    if not math.isclose(float(a),float(b),rel_tol=tolerance,abs_tol=tolerance):raise AssertionError((a,b))

def main():
    p=argparse.ArgumentParser();p.add_argument("--gate",required=True,type=Path);p.add_argument("--approval-sha256",required=True)
    p.add_argument("--input",required=True,type=Path);p.add_argument("--out",required=True,type=Path);a=p.parse_args()
    gate,_=authorize(a.gate,a.approval_sha256,"p1_verification")
    if digest(a.input/"manifest.json")!=gate["input_manifest_sha256"]:raise PermissionError("Wrong input manifest")
    manifest=json.loads((a.input/"manifest.json").read_text());assert manifest["status"]=="complete"
    for name,sha in manifest["files"].items():
        if Path(name).name!=name or digest(a.input/name)!=sha:raise AssertionError("Changed artifact")
    import numpy as np
    from scipy.special import xlogy
    from experiments.vector_direct_screen.physics import CFG
    with np.load(a.input/"data.npz",allow_pickle=False) as z:data={k:z[k] for k in z.files}
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
    import torch
    state=torch.load(a.input/"model-final.pt",map_location="cpu",weights_only=True)
    expected={"0.weight":(256,512),"0.bias":(256,),"2.weight":(128,256),"2.bias":(128,),
        "4.weight":(64,128),"4.bias":(64,),"6.weight":(8,64),"6.bias":(8,)}
    assert set(state)==set(expected)
    assert all(tuple(state[k].shape)==shape and bool(torch.isfinite(state[k]).all()) for k,shape in expected.items())
    history=json.loads((a.input/"training-history.json").read_text())
    assert [h["epoch"] for h in history]==list(range(1,21)) and all(math.isfinite(h["train_normalized_mse"]) for h in history)
    saved=json.loads((a.input/"metrics.json").read_text());timing=json.loads((a.input/"timings.json").read_text())
    names=("lm","affine1","affine3","affine5","neural1");assert set(saved)==set(timing)==set(names)
    rebuilt={}
    for name in names:
        with np.load(a.input/(name+"-predictions.npz"),allow_pickle=False) as z:pred={k:z[k] for k in z.files}
        parameters=pred["parameters"];assert parameters.shape==(2048,8) and np.isfinite(parameters).all()
        rates=pred["fitted_rates"];assert rates.shape==(2048,512) and np.all(rates>0)
        error=np.sqrt(np.einsum("ni,ni->n",parameters[:,:3]-truth[:,:3],parameters[:,:3]-truth[:,:3]))
        np.testing.assert_allclose(error,pred["field_error_uT"],rtol=0,atol=1e-12)
        reduced=2*np.sum(xlogy(val,val/(2000000*rates))-val+2000000*rates,axis=1)/504
        np.testing.assert_allclose(reduced,pred["reduced_deviance"],rtol=0,atol=1e-6)
        accepted=np.isfinite(reduced)&(reduced<=2)&np.all((parameters>=CFG["lower"])&(parameters<=CFG["upper"]),axis=1)
        np.testing.assert_array_equal(accepted,pred["accepted"])
        assert pred["fallback"].dtype.kind=="b" and pred["fallback"].shape==(2048,)
        s={"n":2048,"mean_uT":float(np.mean(error)),"p95_uT":float(np.percentile(error,95)),
            "rmse_uT":float(np.sqrt(np.mean(error*error))),"max_uT":float(max(error)),
            "rejections":int(np.count_nonzero(~accepted)),"fallbacks":int(np.count_nonzero(pred["fallback"]))}
        for k,v in s.items():check_close(v,saved[name][k],1e-12)
        rebuilt[name]=s
        assert set(timing[name])=={"1","64","4096"}
        for batch in (1,64,4096):
            item=timing[name][str(batch)]
            assert item["dtype"]=="float64" and item["chunk"]==1024
            for key in ("host_to_host_seconds","resident_seconds"):
                assert len(item[key])==3 and all(math.isfinite(v) and v>0 for v in item[key])
            with np.load(a.input/(name+f"-timing-{batch}.npz"),allow_pickle=False) as z:
                np.testing.assert_array_equal(z["indices"],np.arange(batch)%2048)
                assert z["parameters"].shape==(3,batch,8)
                for i in range(3):
                    np.testing.assert_allclose(z["parameters"][i],parameters[z["indices"]],rtol=0,atol=1e-5)
                    np.testing.assert_array_equal(z["accepted"][i],pred["accepted"][z["indices"]])
                    np.testing.assert_array_equal(z["fallback"][i],pred["fallback"][z["indices"]])
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
    fastest=min(med(n,4096) for n in adequate);steps={"affine1":1,"affine3":3,"affine5":5,"lm":120}
    chosen=min((n for n in adequate if med(n,4096)<=1.05*fastest),key=lambda n:(steps[n],n))
    classic=result["classical_engineering_opportunity"];assert classic["selected"]==chosen
    check_close(classic["speedup_vs_full_lm"],med("lm",4096)/med(chosen,4096))
    saving=(med("lm",4096)-med(chosen,4096))/4096
    check_close(classic["seconds_saved_per_million"],saving*1000000)
    calibration=setup_record["persistent_engine_calibration_seconds"][chosen]
    check_close(classic["calibration_setup_seconds"],calibration)
    assert classic["break_even_spectra_conservative_calibration"]==(math.ceil(calibration/saving) if saving>0 else None)
    assert classic["provisional_vs_full_lm"]==(chosen!="lm" and med("lm",4096)>=2*med(chosen,4096))
    assert classic["engineering_opportunity_pass"] is None and classic["adequate_tied_line_comparison"]=="PENDING_REQUIRED"
    assert result["practical_adoption"] is False and result["confirmation_authorized"] is False
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/"verification.json").write_text(json.dumps({"passed":True,"input_manifest_sha256":digest(a.input/"manifest.json"),"recomputed_metrics":rebuilt,"continuation_pass":result["continuation_pass"],"classical_candidate":chosen,"no_inference":True},indent=2)+"\n")
    return 0

if __name__=="__main__":raise SystemExit(main())
