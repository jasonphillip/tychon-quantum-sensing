"""Manufactured fixtures only; never read archive signals or real checkpoints."""
import copy
import numpy as np
import pytest
from experiments.localisation_acquisition_transfer.contract import (
    DAY,position_hash,check_geometry,check_saved_labels,decode_seed_bytes)
from experiments.localisation_acquisition_transfer.metrics import evaluate,resampling_bounds
from experiments.localisation_acquisition_transfer.run import load_model
from experiments.localisation_acquisition_transfer.guard import read_json,PACKAGE


def geometry_fixture():
    rows=[]
    for x in (1315.,1377.5,1440.,1502.5,1565.):
        for j,y in enumerate((1184.,1438.,1692.,1946.,2200.)):
            row={"member":DAY+f"sample, x={x}um, y={y}um raw data.npy","position_um":[x,y],
                 "size":100,"compressed":20,"crc32":"00000000","zip_datetime":"2025-08-04 18:00:00",
                 "npy_shape":[2,16,51],"npy_dtype":"float64"}
            rows.append(row)
    custody={"august4":{"members":copy.deepcopy(rows)}}
    geometry={"count":25,"members":[dict(r,group_id="y_stripe_"+str(i%5),
                                       position_sha256=position_hash(r["position_um"])) for i,r in enumerate(rows)]}
    return geometry,custody


def protocol_fixture():
    return copy.deepcopy(read_json(PACKAGE/"protocol.json"))


def predictions():
    geometry,_=geometry_fixture()
    labels=np.asarray([r["position_um"] for r in geometry["members"]])
    groups=np.asarray([r["group_id"] for r in geometry["members"]])
    small=labels+np.array([10.,0.]);full=labels+np.array([12.,0.])
    return labels,small,full,groups


def test_all25_exact_members_and_five_stripes():
    geometry,custody=geometry_fixture()
    assert len(check_geometry(geometry,custody))==25
    assert len({r["group_id"] for r in geometry["members"]})==5


@pytest.mark.parametrize("change",["missing","reordered","duplicate","member","group","labelhash"])
def test_geometry_identity_rejects_changes(change):
    geometry,custody=geometry_fixture()
    if change=="missing":geometry["members"].pop()
    elif change=="reordered":geometry["members"].reverse()
    elif change=="duplicate":geometry["members"][0]=copy.deepcopy(geometry["members"][1])
    elif change=="member":geometry["members"][0]["member"]=DAY+"wrong.npy"
    elif change=="group":geometry["members"][0]["group_id"]="y_stripe_4"
    else:geometry["members"][0]["position_sha256"]="0"*64
    with pytest.raises(ValueError):check_geometry(geometry,custody)


@pytest.mark.parametrize("change",["shifted","permuted","truncated"])
def test_saved_label_identity(change):
    geometry,_=geometry_fixture()
    labels=np.asarray([r["position_um"] for r in geometry["members"]])
    if change=="shifted":labels=labels+1.
    elif change=="permuted":labels=labels[::-1]
    else:labels=labels[:-1]
    with pytest.raises(ValueError):check_saved_labels(labels,geometry)


def test_constants_pass_every_registered_gate():
    labels,small,full,groups=predictions()
    result=evaluate(labels,small,full,groups,protocol_fixture(),123)
    assert result["status"]=="PASS"
    assert all(result["criteria"].values())
    assert len(result["stripes"])==5 and all(r["small"]["count"]==5 for r in result["stripes"])
    assert len(result["per_case_small_error_um"])==25
    assert result["original_spatial_verdict"]=="FAIL"
    assert result["population_day_uncertainty_estimated"] is False


def test_tail_gate_rejects_outliers():
    labels,small,full,groups=predictions()
    small=labels.copy();small[:,0]+=10.;small[:2,0]+=200.
    result=evaluate(labels,small,full,groups,protocol_fixture(),123)
    assert not result["criteria"]["absolute_p95"] and result["status"]=="FAIL"


def test_absolute_gate_not_replaced_by_relative_performance():
    labels,_,_,groups=predictions()
    small=labels+[80.,0.];full=labels+[100.,0.]
    result=evaluate(labels,small,full,groups,protocol_fixture(),123)
    assert result["criteria"]["mean_ratio"]
    assert not result["criteria"]["absolute_mean"] and result["status"]=="FAIL"


def test_invalid_row_is_retained_and_fails():
    labels,small,full,groups=predictions();small[2]=np.nan
    result=evaluate(labels,small,full,groups,protocol_fixture(),123)
    assert result["small"]["count"]==25 and result["small"]["invalid_rows"]==1
    assert result["small"]["mean_error_um"] is None and result["status"]=="FAIL"
    assert result["per_case_small_error_um"][2] is None


def test_zero_reference_error_does_not_invent_ratio():
    labels,small,_,groups=predictions()
    result=evaluate(labels,small,labels.copy(),groups,protocol_fixture(),123)
    assert result["mean_ratio"] is None and result["status"]=="FAIL"


def test_constant_ratio_resampling_moves_whole_stripes():
    groups=np.repeat(np.arange(5),5)
    b=np.arange(1.,26.);a=b*.5
    result=resampling_bounds(a,b,groups,123,100,[.95,.983333333333])
    assert all(np.isclose(v["ratio"],.5) for v in result.values())


def test_98333_bound_is_sensitivity_only(monkeypatch):
    import experiments.localisation_acquisition_transfer.metrics as metrics
    def fixed(*args):
        return {"0.95":{"ratio":1.,"absolute_mean_um":20.},
                "0.983333333333":{"ratio":2.,"absolute_mean_um":200.}}
    monkeypatch.setattr(metrics,"resampling_bounds",fixed)
    result=metrics.evaluate(*predictions(),protocol_fixture(),123)
    assert result["status"]=="PASS"
    assert result["required_uncertainty_quantiles"]==["0.95"]
    assert result["sensitivity_only_quantiles"]==["0.983333333333"]


def test_checkpoint_loading_uses_saved_scaling_without_refit(tmp_path,monkeypatch):
    from experiments.localisation_redesign.models import Scaling
    def forbidden(*args,**kwargs):raise AssertionError("refit forbidden")
    monkeypatch.setattr(Scaling,"fit",forbidden)
    p=tmp_path/"manufactured.npz"
    np.savez(p,**{"state.x":np.ones((2,8)),"state.alpha":np.ones((2,2)),
                  "state.theta":np.zeros((2,10)),"scale.x_mean":np.zeros(24),
                  "scale.x_scale":np.ones(24),"scale.y_mean":np.array([3.,4.]),
                  "scale.y_scale":np.array([2.,3.])})
    state,scale=load_model(p)
    assert state["x"].shape==(2,8)
    np.testing.assert_array_equal(scale.inverse(np.zeros((1,2))),[[3.,4.]])


def test_seed_bytes_commitment_and_big_endian_derivation():
    import hashlib
    payload=bytes(range(32))
    expected=hashlib.sha256(payload).hexdigest()
    assert decode_seed_bytes(payload,expected)==int.from_bytes(payload,"big")
    with pytest.raises(ValueError):decode_seed_bytes(payload[:-1],expected)
    with pytest.raises(ValueError):decode_seed_bytes(bytes(32),expected)
