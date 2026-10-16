"""Manufactured arrays only. Never open the measured archive."""
import io
import zipfile
import numpy as np
import pytest
from experiments.localisation_raw_compatibility.metadata import (
    coordinate_key, raw_inventory, select_sample, read_raw_header, bind_custody, PREFIX)
from experiments.localisation_raw_compatibility.extract import (
    MODEL_CHANNELS, fit_raw, compare_features, load_raw, source_moving_average, extract_payload)

TOLERANCES = dict(splitting_atol_MHz=0.001, splitting_rtol=0.0001,
                  standard_error_atol_MHz=0.0001, standard_error_rtol=0.01)


def encoded(array):
    stream = io.BytesIO()
    if array.dtype.hasobject:
        np.lib.format.write_array_header_1_0(stream, {"descr":"|O","fortran_order":False,"shape":array.shape})
    else:
        np.save(stream, array, allow_pickle=False)
    return stream.getvalue()


def fixture():
    positions = [(float(i), 10.) for i in range(6)]
    groups = [coordinate_key(xy) for xy in positions]
    split = dict(n=6, position_groups=groups, train=[0,1,2,3],
                 full_train=[0,1,2,3], validation=[4], test=[5])
    records = [dict(position_hash=key, session="session"+str(i%2), member=str(i),
                    position_um=list(positions[i]), zip_crc32="00000000",
                    uncompressed_size=128) for i,key in enumerate(groups)]
    return split, records


def test_training_only_deterministic_selection():
    split, records = fixture()
    chosen = select_sample(split, records, 4)
    assert {r["fitted_row"] for r in chosen} == {0,1,2,3}
    assert chosen == select_sample(split, list(reversed(records)), 4)


def test_ambiguous_raw_member_is_excluded():
    split, records = fixture()
    records.append(dict(records[0], member="repeat"))
    assert all(r["fitted_row"] != 0 for r in select_sample(split, records, 3))
    with pytest.raises(ValueError, match="too few"):
        select_sample(split, records, 4)


def test_ambiguous_fitted_coordinate_is_excluded():
    split, records = fixture()
    split["position_groups"][1] = split["position_groups"][0]
    assert {r["fitted_row"] for r in select_sample(split, records, 2)} == {2,3}


def test_held_membership_is_rejected():
    split, records = fixture()
    split["train"].append(5)
    with pytest.raises(ValueError, match="training-only"):
        select_sample(split, records, 4)


def test_missing_unique_training_count_is_rejected():
    split, records = fixture()
    with pytest.raises(ValueError, match="too few"):
        select_sample(split, records, 5)


def test_safe_raw_header_and_loader():
    data = encoded(np.ones((2,16,51), dtype="<f8"))
    assert read_raw_header(io.BytesIO(data), len(data))["shape"] == [2,16,51]
    assert load_raw(data).shape == (2,16,51)


@pytest.mark.parametrize("array", [np.ones((2,16,51),dtype=np.float32),
                                   np.ones((2,15,51)), np.ones((2,16,50)),
                                   np.empty((2,16,51),dtype=object),
                                   np.asfortranarray(np.ones((2,16,51)))])
def test_unsafe_header_is_rejected(array):
    data = encoded(array)
    with pytest.raises(ValueError):
        read_raw_header(io.BytesIO(data),len(data))


def test_trailing_payload_is_rejected():
    data = encoded(np.ones((2,16,51))) + b"extra"
    with pytest.raises(ValueError,match="size"):
        read_raw_header(io.BytesIO(data),len(data))


def test_nonfinite_signal_is_rejected():
    raw = np.ones((2,16,51)); raw[0,0,0] = np.nan
    with pytest.raises(ValueError,match="nonfinite"):
        load_raw(encoded(raw))


def test_known_channel_order_and_source_window():
    assert MODEL_CHANNELS == (15,6,11,4,13,7,3,1)
    np.testing.assert_array_equal(source_moving_average(np.arange(51.)), np.arange(1.,49.))


def test_failed_fit_cannot_reuse_previous_coefficients():
    calls = []
    def fitter(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("manufactured fit failure")
        return np.array([1.,2.82,.02,1.,2.92,10.]), np.eye(6)*1e-6
    parameters, deviations, features, flags = fit_raw(np.ones((2,16,51)), fitter)
    assert len(flags) == 8
    assert flags[0]["valid"] and not flags[1]["valid"] and flags[2]["valid"]
    assert np.isnan(parameters[1]).all() and np.isnan(deviations[1]).all()
    assert np.isnan(features.reshape(8,3)[1]).all()


def test_channel_order_in_extracted_rows():
    seen = []
    raw = np.broadcast_to(np.arange(16.)[None,:,None], (2,16,51)).copy()
    def fitter(model, x, y, **kwargs):
        seen.append(float(y[0]))
        return np.array([1.,2.82,.02,1.,2.92,10.]), np.eye(6)*1e-6
    _,_,features,flags = fit_raw(raw,fitter)
    assert seen == [float(i-1) for i in MODEL_CHANNELS]
    np.testing.assert_allclose(features.reshape(8,3), np.tile([100.,1.,1.],(8,1)))
    assert all(f["valid"] for f in flags)


def test_feature_match_requires_every_element_and_validity():
    expected = np.ones((8,24))
    assert compare_features(expected,expected,TOLERANCES)["all_features_match"]
    bad = expected.copy(); bad[3,5] += 1.
    report = compare_features(bad,expected,TOLERANCES)
    assert not report["all_features_match"] and report["failed_elements"] == [[3,5]]
    for value in (np.nan,np.inf,0.,-1.):
        bad = expected.copy();bad[0,0] = value
        assert not compare_features(bad,expected,TOLERANCES)["all_features_match"]


def test_zip_metadata_excludes_separate_day_and_checks_names():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,"w") as archive:
        archive.writestr(PREFIX+"2025-08-05 145046chip15 45mW/a, x=1.0um, y=2.0um raw data.npy",b"header")
        archive.writestr("Fig.3/August4/a, x=1.0um, y=2.0um raw data.npy",b"header")
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        records=raw_inventory(archive)
    assert len(records)==1 and records[0]["position_um"]==[1.,2.]


def test_custody_binding_rejects_member_drift():
    split, records = fixture()
    selected = select_sample(split, records, 1)
    item = selected[0]
    item["member"] = "Data availability update 20260220/" + item["member"]
    custody = {"schema":1,"signal_decoded":False,"archive_sha256":"a","partition_sha256":"p",
               "training_raw_candidates":{"partition_key":"full_train","candidates":[{
                   "fitted_row":item["fitted_row"],"position_um":item["position_um"],
                   "unambiguous":True,"raw_member_count":1,"raw_members":[{
                       "member":item["member"].split("/",1)[1],"crc32":item["zip_crc32"],
                       "size":item["uncompressed_size"]}]}]}}
    bind_custody(selected,custody,"a","p")
    custody["training_raw_candidates"]["candidates"][0]["raw_members"][0]["crc32"]="ffffffff"
    with pytest.raises(ValueError,match="differs"):
        bind_custody(selected,custody,"a","p")


def test_invalid_raw_sample_retains_eight_flags_and_nan_features():
    raw=np.ones((2,16,51));raw[0,1,1]=np.nan
    parameters, deviations, features, flags=extract_payload(encoded(raw))
    assert len(flags)==8 and not any(f["valid"] for f in flags)
    assert np.isnan(parameters).all() and np.isnan(deviations).all() and np.isnan(features).all()
