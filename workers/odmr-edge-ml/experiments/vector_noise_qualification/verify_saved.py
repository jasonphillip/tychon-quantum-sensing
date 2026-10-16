"""Independent arithmetic on saved outputs; no forward model, RNG, or inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.vector_noise_qualification.access import authorize


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_records(data, records):
    import numpy as np
    assert len(records)==128 and data["parameters"].shape==(128,8)
    assert data["latent_parameters"].shape==(64,8)
    assert len({r["record_id"] for r in records})==128
    assert len({r["latent_id"] for r in records})==64
    for i,record in enumerate(records):
        latent=i//2;regime="A" if latent<32 else "B";identifier=f"{regime}{latent%32:02d}"
        assert record=={"row":i,"record_id":identifier+f"-r{i%2}","latent_id":identifier,
            "latent_index":latent,"regime":regime,"replicate":i%2,
            "parameter_sha256":hashlib.sha256(np.asarray(data["parameters"][i],dtype="<f8").tobytes()).hexdigest()}
        np.testing.assert_array_equal(data["parameters"][i],data["latent_parameters"][latent])
    np.testing.assert_array_equal(data["latent_index"],np.repeat(np.arange(64),2))
    np.testing.assert_array_equal(data["replicate"],np.tile(np.arange(2),64))
    assert len({hashlib.sha256(row.astype("<f8").tobytes()).hexdigest() for row in data["latent_parameters"]})==64


def check_information(rates,jac,saved,prefix="",counts=None):
    import numpy as np
    scales=np.array([20,20,20,.4,1,.05,.02,.01])
    for i in range(len(rates)):
        weight=(2000000/rates[i])**.5 if counts is None else counts[i]**.5/rates[i]
        weighted=np.column_stack([jac[i,:,j]*scales[j]*weight for j in range(8)])
        _,s,_=np.linalg.svd(weighted,full_matrices=False)
        threshold=max(weighted.shape)*np.finfo(float).eps*s[0]
        rank=int(np.count_nonzero(s>threshold))
        assert int(saved[prefix+"rank"][i])==rank
        np.testing.assert_allclose(saved[prefix+"fisher_scaled"][i],weighted.T@weighted,rtol=1e-9,atol=1e-8)
        np.testing.assert_allclose(saved[prefix+"singular_values"][i],s,rtol=1e-9,atol=1e-10)
        condition=s[0]/s[-1] if rank==8 else np.inf
        np.testing.assert_allclose(saved[prefix+"weighted_jacobian_condition"][i],condition,rtol=1e-8)
        if rank==8:
            inverse=np.linalg.pinv(weighted,rcond=threshold/s[0])
            covariance=(inverse@inverse.T)*np.outer(scales,scales)
            np.testing.assert_allclose(saved[prefix+"field_covariance_uT2"][i],covariance[:3,:3],rtol=1e-6,atol=1e-8)
        else:assert np.isnan(saved[prefix+"field_covariance_uT2"][i]).all()


def verify(directory):
    import numpy as np
    from scipy.special import xlogy
    manifest=json.loads((directory/"manifest.json").read_text())
    assert manifest["status"]=="complete" and manifest["completed_methods"]==["lm","affine","peaks","calibrated"]
    extras={"manifest.json","central-receipt.json","collected-manifest.json","supervisor-stdout.txt","supervisor-stderr.txt"}
    assert set(manifest["files"])=={p.name for p in directory.iterdir() if p.is_file() and p.name not in extras}
    for name,digest in manifest["files"].items():
        assert Path(name).name==name and sha(directory/name)==digest
    with np.load(directory/"data.npz",allow_pickle=False) as f:data={k:f[k] for k in f.files}
    records=json.loads((directory/"records.json").read_text());validate_records(data,records)
    counts=data["counts"];assert counts.shape==(128,512) and counts.dtype==np.dtype("int64") and (counts>=0).all()
    np.testing.assert_array_equal(data["expected_counts"],data["true_rates"]*2000000)
    np.testing.assert_allclose(data["true_rates"],data["independent_true_rates"],rtol=0,atol=1e-11)
    provenance=json.loads((directory/"provenance.json").read_text())
    assert provenance["exposure_photons_per_bin"]==2000000 and provenance["bit_generator"]=="PCG64"
    assert (provenance["A_latents"],provenance["B_latents"],provenance["replicates_per_latent"],provenance["spectra"])==(32,32,2,128)
    assert provenance["field_units"]=="microtesla" and provenance["frequency_units"]=="MHz"
    cfg=json.loads((ROOT/"experiments/vector_direct_screen/config.json").read_text())
    params=data["parameters"];assert np.isfinite(params).all()
    assert ((params>=cfg["lower"])&(params<=cfg["upper"])).all()
    alo=np.array([-10,-10,-10,2869.9,1.75,.04,.99,-.005]);ahi=np.array([10,10,10,2870.1,2.25,.08,1.01,.005])
    assert ((params[:64]>=alo)&(params[:64]<=ahi)).all()
    with np.load(directory/"true_information.npz",allow_pickle=False) as f:
        check_information(data["true_rates"],data["true_jacobian"],f)
        true_rank_deficient=int((f["rank"]<8).sum())
    result=json.loads((directory/"result.json").read_text());assert result["status"]=="diagnostic_only_no_adoption"
    assert result["true_expected_rank_deficient"]==true_rank_deficient
    assert result["spectra"]==128 and result["all_cases_retained"] and not result["practical_adoption"] and not result["neural_model"]
    for name in ("lm","affine","peaks","calibrated"):
        with np.load(directory/(name+"-prediction.npz"),allow_pickle=False) as f:prediction={k:f[k] for k in f.files}
        with np.load(directory/(name+"-diagnostics.npz"),allow_pickle=False) as f:diag={k:f[k] for k in f.files}
        assert prediction["parameters"].shape==(128,8)
        for key in ("accepted","fallback"):
            assert prediction[key].shape==(128,) and prediction[key].dtype==np.dtype("bool")
        delta=prediction["parameters"][:,:3].astype(float)-params[:,:3]
        error=np.linalg.norm(delta,axis=1)
        np.testing.assert_allclose(diag["field_delta_uT"],delta,rtol=0,atol=1e-12)
        np.testing.assert_allclose(diag["field_error_uT"],error,rtol=1e-12,atol=1e-12)
        mu=diag["fitted_rates"]*2000000
        deviance=2*np.sum(xlogy(counts,counts/mu)-counts+mu,axis=1)/(512-8)
        tolerance=.02 if name=="affine" else 1e-6
        np.testing.assert_allclose(prediction["reduced_deviance"],deviance,rtol=0,atol=tolerance)
        bound_dtype=np.float32 if name=="affine" else np.float64
        lower=np.asarray(cfg["lower"],dtype=bound_dtype);upper=np.asarray(cfg["upper"],dtype=bound_dtype)
        bounded=((prediction["parameters"]>=lower)&(prediction["parameters"]<=upper)).all(axis=1)
        expected_flag=np.isfinite(prediction["parameters"]).all(axis=1)&bounded&np.isfinite(prediction["reduced_deviance"])&(prediction["reduced_deviance"]<=2)
        np.testing.assert_array_equal(prediction["accepted"],expected_flag)
        check_information(diag["fitted_rates"],diag["fitted_jacobian"],diag,"plugin_expected_")
        check_information(diag["fitted_rates"],diag["fitted_jacobian"],diag,"observed_gn_",counts)
        summary=json.loads((directory/(name+"-summary.json")).read_text());assert summary==result["methods"][name]
        expected_config=("float32",4096) if name=="affine" else ("float64",1024)
        assert (summary["dtype"],summary["chunk"])==expected_config
        assert summary["plugin_expected_rank_deficient"]==int((diag["plugin_expected_rank"]<8).sum())
        assert summary["observed_gn_rank_deficient"]==int((diag["observed_gn_rank"]<8).sum())
        assert np.isfinite(summary["diagnostic_seconds"]) and summary["diagnostic_seconds"]>=0
        assert np.isfinite(summary["host_to_host_seconds"]) and summary["host_to_host_seconds"]>0
        for label,indices in (("all",np.arange(128)),("A",np.arange(64)),("B",np.arange(64,128))):
            e=error[indices];s=summary["errors"][label]
            actual=[e.mean(),np.sqrt(np.mean(e**2)),*np.percentile(e,[50,90,99]),e.max()]
            expected=[s[k] for k in ("mean_uT","rmse_uT","p50_uT","p90_uT","p99_uT","max_uT")]
            np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)
            assert s["n"]==len(indices) and s["accepted"]==int(prediction["accepted"][indices].sum()) and s["fallback"]==int(prediction["fallback"][indices].sum())
    return {"passed":True,"scope":"saved bytes, grouping, units, error metrics, likelihood and information arithmetic; no forward model or RNG", "spectra":128,"methods":4,"adoption":False}


def main():
    parser=argparse.ArgumentParser()
    for key in ("gate","input","out"):parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--approval-sha256",required=True)
    args=parser.parse_args();gate,_=authorize(args.gate,args.approval_sha256,"p0_verify")
    if gate.get("input_manifest_sha256")!=sha(args.input/"manifest.json"):
        raise PermissionError("Saved input manifest is not root-bound")
    args.out.mkdir(parents=True,exist_ok=False)
    result=verify(args.input)
    (args.out/"verification.json").write_text(json.dumps(result,indent=2)+"\n")
    return 0


if __name__=="__main__":raise SystemExit(main())
