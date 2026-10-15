"""Manufactured spectra and independent safety contracts for the repair."""
import importlib.util,json,sys
from pathlib import Path
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments/scalar_repair_cycle"))
from estimators import (GRID,TRAIN_MEDIAN,edge_ols,robust_fit,likelihood_magnitude,
    metrics,paired_ci,checked_fallback,profile,jacobian,FitResult)
from run_development import preflight
def manufactured(center=.3,split=3.2,width=.8,slope=.0002):
    # Independent physical-frequency formula, no call to the fitter's profile.
    f=GRID/1e6-2870
    return 1+slope*f-.018*width**2/((f-center+split/2)**2+width**2)-.014*width**2/((f-center-split/2)**2+width**2)
@pytest.mark.parametrize("slope",[-.0002,0,.0002])
def test_manufactured_centers_and_slopes(slope):
    result=robust_fit(manufactured(slope=slope))
    assert not result.hard_invalid,result.as_dict()
    np.testing.assert_allclose(result.diagnostics["centers_MHz"],[-1.3,1.9],atol=.04)
    assert abs(result.slope_per_MHz-slope)<1e-6
    assert result.diagnostics["starts_attempted"]<=4
    assert result.diagnostics["total_nfev"]<=800
def test_single_merged_dip_is_ambiguous():
    result=robust_fit(manufactured(split=0,width=2.5))
    assert result.ambiguous
def test_flat_spectrum_falls_back():
    result=robust_fit(np.ones(100))
    assert result.hard_invalid and result.prediction_uT==TRAIN_MEDIAN
def test_nonfinite_input_falls_back():
    y=manufactured();y[20]=np.nan
    assert robust_fit(y).hard_invalid
def test_changed_grid_is_refused():
    with pytest.raises(ValueError):edge_ols(manufactured(),GRID+1000)
def test_peak_outside_operating_window_rejected():
    result=robust_fit(manufactured(center=30))
    assert result.hard_invalid
def test_large_curvature_rejected():
    y=manufactured()+.06*((GRID-2.87e9)/5e7)**2
    assert robust_fit(y).hard_invalid
def test_fixed_edge_slope_correction():
    x=(GRID-2.87e9)/1e6
    corrected,slope,intercept=edge_ols(1+.0002*x)
    np.testing.assert_allclose(corrected,1,atol=1e-12);assert abs(slope-.0002)<1e-12
def test_analytic_optimizer_jacobian():
    x=(GRID-2.87e9)/1e6;p=np.array([1,.0002,.3,3.2,.018,.014,.8]);eps=1e-6
    numeric=np.column_stack([(profile(x,p+np.eye(7)[i]*eps)-profile(x,p-np.eye(7)[i]*eps))/(2*eps) for i in range(7)])
    np.testing.assert_allclose(jacobian(x,p),numeric,atol=1e-8,rtol=1e-5)
def test_likelihood_is_finite_and_prior_bounded():
    y=manufactured();r=likelihood_magnitude(y,robust_fit(y))
    assert not r["hard_invalid"]
    assert 20<=r["interval90_uT"][0]<=r["prediction_uT"]<=r["interval90_uT"][1]<=70
    assert r["conditional_nuisance"] and not r["calibrated"]
def test_invalid_fit_likelihood_is_flagged_fallback():
    r=likelihood_magnitude(np.ones(100),FitResult())
    assert r["hard_invalid"] and r["prediction_uT"]==TRAIN_MEDIAN
def test_fallback_retains_rows_and_domain_failures():
    p,b=checked_fallback([30,np.nan,100,40],[False,False,False,True])
    assert b.tolist()==[False,True,True,True]
    assert metrics(p,np.ones(4)*40)["n"]==4
def test_metrics_refuse_missing_rows_and_nonfinite():
    for p,t in [([1],[1,2]),([np.nan],[1]),([],[])]:
        with pytest.raises(ValueError):metrics(p,t)
def test_pairing_is_grouped_and_deterministic():
    a=paired_ci([1,1,5,5],["a","a","b","b"],1000)
    b=paired_ci([1,1,5,5],["a","a","b","b"],1000)
    assert a==b and a["groups"]==2 and a["mean_difference_uT"]==3
@pytest.mark.parametrize("name",["val","final"])
def test_reserved_partitions_refused_before_manifest_read(tmp_path,name):
    with pytest.raises(ValueError,match="refuses validation and final"):preflight(tmp_path/name)
def test_unsafe_payload_path_refused(tmp_path):
    root=tmp_path/"dev";root.mkdir()
    m=dict(partition="dev",single_orientation=True,rows_per_cell=256,field_ids=[str(i) for i in range(256)],nuisance_group_ids=[str(i) for i in range(256)],
        cells={k:{"file":"../outside.npz"} for k in ("clean","realistic_anchor","wide_lines","low_snr","negative_slope","negative_offset","higher_contrast")})
    p=root/"manifest.json";p.write_text(json.dumps(m));p.chmod(0o444);root.chmod(0o555)
    try:
        with pytest.raises(ValueError,match="unsafe"):preflight(root)
    finally:root.chmod(0o755);p.chmod(0o644)

import gates
from decisions import decide,final_decision
from models import sha
def custody_fixture(tmp_path,partition="val"):
    root=tmp_path/partition;root.mkdir()
    manifest={"partition":partition,"single_orientation":True,"frequency_grid_hz":[],"field_prior":{},
        "nuisance_distribution":{},"noise_reference_fraction":.3,"generator_sha256":"generator",
        "stress_generator_sha256":"stress","source_sha256":{},"cells":{}}
    gate=tmp_path/("FREEZE1.md" if partition=="val" else "FREEZE2.md");gate.write_text("custodian approval\n")
    frozen=tmp_path/"freeze.json"
    frozen.write_text(json.dumps(dict(schema=1,stage=1 if partition=="val" else 2,
        source_hashes=gates.source_map(),versions=gates.versions(),data_contract=gates.data_contract(manifest),evaluation_root=str(tmp_path/"evaluation"),
        model_records=[],primary_implementation="int8",claim_route="accuracy",bootstrap_seed=202610152001,
        protocol_sha256=sha(ROOT/"experiments/scalar_repair_cycle/PROTOCOL.md"),development_manifest_sha256="development")))
    if partition=="final":
        child=json.loads(frozen.read_text());parent=tmp_path/"freeze1.json"
        parent.write_text(json.dumps(dict(child,stage=1)))
        summary=dict(status="complete",partition="val",freeze_sha256=sha(parent),manifest_sha256="validation",cells=decision_fixture())
        summary["selection"]=decide(summary["cells"]);summary["validation_can_proceed"]=True
        val=tmp_path/"evaluation/results-val";val.mkdir(parents=True)
        (val/"SUMMARY.json").write_text(json.dumps(summary))
        receipt={k:summary[k] for k in ("status","partition","freeze_sha256","manifest_sha256")}
        receipt["summary_sha256"]=sha(val/"SUMMARY.json")
        (val/"RECEIPT.json").write_text(json.dumps(receipt))
        (val.parent/"VAL_EVALUATOR_ACCESS.json").write_text(json.dumps(receipt))
        child.update(parent_freeze_reference="freeze1.json",parent_freeze_sha256=sha(parent),
            validation_summary_sha256=sha(val/"SUMMARY.json"),validation_receipt_sha256=sha(val/"RECEIPT.json"),
            validation_access_sha256=sha(val.parent/"VAL_EVALUATOR_ACCESS.json"),selection=summary["selection"])
        frozen.write_text(json.dumps(child))
    gate.write_text("custodian approval "+sha(frozen)+"\n")
    manifest["gate_document_sha256"]=sha(gate)
    (root/"manifest.json").write_text(json.dumps(manifest))
    access=tmp_path/("exclusive-access-receipt.json" if partition=="final" else "VAL_ACCESS.json")
    base=dict(schema=1,partition=partition,data_manifest_sha256=sha(root/"manifest.json"),
        freeze_receipt_sha256=sha(frozen))
    access.write_text(json.dumps(dict(base,status="authorized")))
    release=tmp_path/"release.json"
    release.write_text(json.dumps(dict(base,approved=True,gate_document_sha256=sha(gate),
        exclusive_access_receipt_sha256=sha(access))))
    return root,frozen,release,gate,access
def authorize_fixture(parts):
    root,frozen,release,gate,access=parts
    return gates.authorize(root,root.name,frozen,sha(frozen),release,sha(release),gate,access)
@pytest.mark.parametrize("partition",["val","final"])
def test_hash_bound_custody_accepts_complete_binding(tmp_path,partition):
    parts=custody_fixture(tmp_path,partition)
    assert authorize_fixture(parts)["stage"]==(1 if partition=="val" else 2)
@pytest.mark.parametrize("target",["manifest","gate","access","release","source"])
def test_hash_bound_custody_rejects_tampering(tmp_path,monkeypatch,target):
    parts=custody_fixture(tmp_path);root,frozen,release,gate,access=parts
    if target=="source":
        current=gates.source_map();current["injected.py"]="bad"
        monkeypatch.setattr(gates,"source_map",lambda:current)
    elif target=="release":
        value=json.loads(release.read_text());value["approved"]=False;release.write_text(json.dumps(value))
    else:
        path={"manifest":root/"manifest.json","gate":gate,"access":access}[target]
        path.write_text(path.read_text()+" ")
    with pytest.raises(ValueError):authorize_fixture(parts)
def test_missing_authorization_is_not_inferred_from_filename(tmp_path):
    parts=custody_fixture(tmp_path);value=json.loads(parts[2].read_text());value.pop("approved")
    parts[2].write_text(json.dumps(value))
    with pytest.raises(ValueError):authorize_fixture(parts)
def test_release_hash_is_required(tmp_path):
    root,frozen,release,gate,access=custody_fixture(tmp_path)
    with pytest.raises(ValueError,match="pinned receipt"):
        gates.authorize(root,"val",frozen,sha(frozen),release,"",gate,access)
def test_source_freeze_detects_added_or_deleted_experiment_sources():
    frozen=dict(source_hashes=gates.source_map(),versions=gates.versions())
    frozen["source_hashes"].pop(next(iter(frozen["source_hashes"])))
    with pytest.raises(ValueError,match="source"):gates.verify_sources(frozen)
def decision_fixture():
    labels=("robust_prior_fit","conditional_likelihood","edge_ols__int8","joint_fit__int8")
    summary={}
    for cell in ("clean","realistic_anchor"):
        summary[cell]=dict(decision_metrics={},paired_comparisons={})
        for i,label in enumerate(labels):
            summary[cell]["decision_metrics"][label]=dict(mae_uT=10+i,p90_abs_uT=20,
                hard_invalid_fraction=0.,valid_fraction=.98,all_seeds_reliable=True,median_pipeline_seconds=.01)
            for base in ("training_mean","training_median"):
                summary[cell]["paired_comparisons"][label+"_minus_"+base]=dict(ci95_uT=[-2.,-1.])
        for policy in ("edge_ols__int8","joint_fit__int8"):
            for classical in ("robust_prior_fit","conditional_likelihood"):
                summary[cell]["paired_comparisons"][policy+"_minus_"+classical]=dict(ci95_uT=[-1.2,-.8])
    return summary
def test_validation_never_weakens_classical_reference_for_passing_status():
    s=decision_fixture()
    s["clean"]["paired_comparisons"]["robust_prior_fit_minus_training_mean"]["ci95_uT"]=[-1,1]
    selection=decide(s)
    assert selection["classical"]=="robust_prior_fit"
    assert selection["can_proceed"]
def test_secondary_or_single_primary_win_cannot_rescue_final():
    s=decision_fixture();selection=decide(s)
    s["clean"]["paired_comparisons"][selection["neural"]+"_minus_"+selection["classical"]]["ci95_uT"]=[-1,1]
    assert not final_decision(s,selection)["neural_accuracy_advantage"]
def test_ambiguity_blocks_reliable_claim_despite_prediction_gain():
    s=decision_fixture();selection=decide(s)
    s["realistic_anchor"]["decision_metrics"][selection["neural"]]["all_seeds_reliable"]=False
    result=final_decision(s,selection)
    assert result["neural_accuracy_advantage"] and not result["neural_reliable"]

from run_development import reserve_evaluation
def test_exclusive_evaluator_receipt_blocks_replay_and_new_output(tmp_path):
    frozen={"evaluation_root":str(tmp_path/"evaluation")}
    out=tmp_path/"evaluation/results-val"
    receipt=reserve_evaluation(out,"val","manifest","freeze",frozen)
    assert receipt.exists()
    with pytest.raises(ValueError,match="already consumed"):
        reserve_evaluation(out,"val","manifest","freeze",frozen)
    with pytest.raises(ValueError,match="output differs"):
        reserve_evaluation(tmp_path/"other","val","manifest","freeze",frozen)

def test_generator_distribution_is_frozen_independently_of_custody_hashes(tmp_path):
    parts=custody_fixture(tmp_path)
    root,frozen,release,gate,access=parts
    m=json.loads((root/"manifest.json").read_text());m["nuisance_distribution"]={"changed":True}
    (root/"manifest.json").write_text(json.dumps(m))
    # Even a new release covering the changed manifest cannot change Freeze 1.
    a=json.loads(access.read_text());a["data_manifest_sha256"]=sha(root/"manifest.json");access.write_text(json.dumps(a))
    r=json.loads(release.read_text());r["data_manifest_sha256"]=a["data_manifest_sha256"];r["exclusive_access_receipt_sha256"]=sha(access);release.write_text(json.dumps(r))
    with pytest.raises(ValueError,match="generator/distribution drift"):authorize_fixture(parts)


def test_unselected_pass_cannot_rescue_validation():
    s=decision_fixture()
    for label in ("robust_prior_fit","edge_ols__int8"):
        s["clean"]["paired_comparisons"][label+"_minus_training_mean"]["ci95_uT"]=[-1,1]
    assert not decide(s)["can_proceed"]

def test_development_revision_name_is_explicit(tmp_path):
    with pytest.raises(FileNotFoundError):preflight(tmp_path/"dev-r2")
    with pytest.raises(ValueError):preflight(tmp_path/"dev-r3")

def test_create_freeze_requires_pinned_development_manifest(tmp_path,monkeypatch):
    monkeypatch.setattr(gates,"records",lambda _:[])
    p=tmp_path/"manifest.json";p.write_text('{"partition":"dev-r2"}')
    with pytest.raises(ValueError,match="pinned"):
        gates.create_freeze(1,tmp_path/"freeze",None,evaluation_root=tmp_path,development_manifest=p)

def test_completed_validation_requires_canonical_matching_receipts(tmp_path):
    summary=dict(status="complete",partition="val",freeze_sha256="f",manifest_sha256="m",cells=decision_fixture())
    summary["selection"]=decide(summary["cells"]);summary["validation_can_proceed"]=True
    root=tmp_path/"eval";out=root/"results-val";out.mkdir(parents=True)
    path=out/"SUMMARY.json";path.write_text(json.dumps(summary))
    receipt=dict(status="complete",partition="val",freeze_sha256="f",manifest_sha256="m",summary_sha256=sha(path))
    (out/"RECEIPT.json").write_text(json.dumps(receipt));access=root/"VAL_EVALUATOR_ACCESS.json";access.write_text(json.dumps(receipt))
    assert gates.completed_validation({"evaluation_root":str(root)},"f",path)==summary
    other=tmp_path/"SUMMARY.json";other.write_text(path.read_text())
    with pytest.raises(ValueError,match="canonical"):gates.completed_validation({"evaluation_root":str(root)},"f",other)
    receipt["status"]="in_progress";access.write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match="completion"):gates.completed_validation({"evaluation_root":str(root)},"f",path)

def test_budget_counts_failures_and_unknown_cpu_conservatively(tmp_path):
    from job_receipt import usage,check_budget
    p=tmp_path/"ledger";p.write_text(json.dumps(dict(status="failed",wall_seconds=5,cpu_seconds=None))+"\n")
    total=usage([p]);assert total["cpu_seconds"]==20 and total["wall_seconds"]==5
    with pytest.raises(ValueError,match="reserve"):check_budget(total,total,120,"development",cpu_cap=7300)
    with pytest.raises(ValueError,match="development"):check_budget(total,dict(cpu_seconds=0,wall_seconds=890),20,"development")

def test_timing_warms_only_on_separate_development_inputs(monkeypatch):
    import timing
    calls=[]
    def fake_fit(row):
        calls.append(float(row[0]));return FitResult(hard_invalid=True)
    monkeypatch.setattr(timing,"robust_fit",fake_fit)
    monkeypatch.setattr(timing,"likelihood_magnitude",lambda row,fit:{"prediction_uT":TRAIN_MEDIAN})
    result=timing.measure(np.ones((2,100))*7,None,None,np.ones((4,100))*3,count=2)
    assert calls==[3,3,3,3,7,7]*14
    assert all(v["warmup_source"]=="frozen development" for v in result.values())

def test_raw_accounting_does_not_hide_original_fit_failure():
    from run_development import raw_accounting
    pred=np.array([TRAIN_MEDIAN,TRAIN_MEDIAN,80.])
    raw=np.array([np.nan,np.nan,80.]);proj=np.array([np.nan,80.,40.])
    flags,valid=raw_accounting(pred,raw,np.array([True,True,False]),np.zeros(3,bool),np.zeros(3,bool),np.ones(3)*40,proj)
    assert flags["nonfinite_raw_count"]==2 and flags["nonfinite_raw_projection_count"]==1
    assert flags["raw_projection_support_violations"]==1 and flags["raw_output_support_violations"]==1
    assert not valid.any() and metrics(pred,np.ones(3)*40)["n"]==3

def test_freeze_two_rejects_wrong_parent_stage(tmp_path,monkeypatch):
    monkeypatch.setattr(gates,"records",lambda _:[])
    parent=tmp_path/"freeze.json";parent.write_text(json.dumps(dict(schema=1,stage=2,source_hashes=gates.source_map(),versions=gates.versions())))
    with pytest.raises(ValueError,match="requires Freeze 1"):
        gates.create_freeze(2,tmp_path/"next.json",None,prior=parent,prior_hash=sha(parent))

def test_budget_standard_correction_supersedes_old_format(tmp_path):
    from job_receipt import usage
    p=tmp_path/"ledger"
    rows=[dict(completed_utc="a",cpu_seconds=None,wall_seconds=5),
        dict(job="cpu_adjustment",original_completed_utc="a",adjustment_cpu_seconds=20),
        dict(job="cpu_adjustment",correction_of_utc="a",cpu_seconds=20,wall_seconds=0)]
    p.write_text("".join(json.dumps(row)+"\n" for row in rows))
    assert usage([p])["cpu_seconds"]==20

@pytest.mark.parametrize("block",["budget","lock"])
def test_budget_rejection_never_launches_child(tmp_path,block):
    import subprocess,fcntl
    ledger=tmp_path/"ledger";ledger.write_text(json.dumps(dict(wall_seconds=0,cpu_seconds=14400 if block=="budget" else 0))+"\n")
    lock=tmp_path/"lock";marker=tmp_path/"launched"
    with lock.open("a") as handle:
        if block=="lock":fcntl.flock(handle,fcntl.LOCK_EX)
        cmd=[sys.executable,str(ROOT/"experiments/scalar_repair_cycle/job_receipt.py"),
            "--ledger",str(ledger),"--budget-lock",str(lock),"--seconds","1","--",sys.executable,
            "-c","from pathlib import Path; Path("+repr(str(marker))+").touch()"]
        result=subprocess.run(cmd,capture_output=True)
    assert result.returncode!=0 and not marker.exists()


@pytest.mark.parametrize("target",["parent","summary","receipt","access"])
@pytest.mark.parametrize("mutation",["changed","missing"])
def test_final_authorization_rechecks_parent_and_completed_evidence(tmp_path,target,mutation):
    parts=custody_fixture(tmp_path,"final")
    paths={"parent":tmp_path/"freeze1.json","summary":tmp_path/"evaluation/results-val/SUMMARY.json",
        "receipt":tmp_path/"evaluation/results-val/RECEIPT.json","access":tmp_path/"evaluation/VAL_EVALUATOR_ACCESS.json"}
    path=paths[target]
    if mutation=="missing":path.unlink()
    else:path.write_text(path.read_text()+" ")
    with pytest.raises((ValueError,FileNotFoundError)):authorize_fixture(parts)

def rebind_final_fixture(parts,child):
    root,frozen,release,gate,access=parts
    frozen.write_text(json.dumps(child))
    gate.write_text("custody approval "+sha(frozen))
    manifest=json.loads((root/"manifest.json").read_text());manifest["gate_document_sha256"]=sha(gate)
    (root/"manifest.json").write_text(json.dumps(manifest))
    a=json.loads(access.read_text());a.update(freeze_receipt_sha256=sha(frozen),data_manifest_sha256=sha(root/"manifest.json"))
    access.write_text(json.dumps(a))
    r=json.loads(release.read_text());r.update(freeze_receipt_sha256=sha(frozen),data_manifest_sha256=sha(root/"manifest.json"),
        gate_document_sha256=sha(gate),exclusive_access_receipt_sha256=sha(access))
    release.write_text(json.dumps(r))

def test_final_authorization_rejects_forged_stage2_selection(tmp_path):
    parts=custody_fixture(tmp_path,"final")
    child=json.loads(parts[1].read_text());child["selection"]["classical"]="conditional_likelihood"
    rebind_final_fixture(parts,child)
    with pytest.raises(ValueError,match="selection"):authorize_fixture(parts)

@pytest.mark.parametrize("reference",["/absolute/freeze1.json","./freeze1.json",""])
def test_final_parent_reference_must_be_portable_and_normalized(tmp_path,reference):
    parts=custody_fixture(tmp_path,"final");child=json.loads(parts[1].read_text());child["parent_freeze_reference"]=reference
    rebind_final_fixture(parts,child)
    with pytest.raises(ValueError,match="normalized and relative"):authorize_fixture(parts)

def test_final_authorization_rejects_symlinked_parent_evidence_directory(tmp_path):
    parts=custody_fixture(tmp_path,"final")
    val=tmp_path/"evaluation/results-val";moved=tmp_path/"moved";val.rename(moved);val.symlink_to(moved,target_is_directory=True)
    with pytest.raises(ValueError,match="symlinked"):authorize_fixture(parts)

def test_create_freeze_two_stores_relative_parent_reference(tmp_path,monkeypatch):
    parts=custody_fixture(tmp_path,"final");parent=tmp_path/"freeze1.json";child=tmp_path/"freeze2-created.json"
    monkeypatch.setattr(gates,"records",lambda _:[])
    gates.create_freeze(2,child,None,prior=parent,prior_hash=sha(parent),validation=tmp_path/"evaluation/results-val/SUMMARY.json")
    frozen=json.loads(child.read_text())
    assert frozen["parent_freeze_reference"]=="freeze1.json"
    assert gates.verify_parent_chain(child,frozen)["stage"]==1
