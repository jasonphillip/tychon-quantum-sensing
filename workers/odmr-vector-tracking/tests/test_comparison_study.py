"""Tests for experiments/comparison_study.py: decision rule, failure accounting, final guard."""
import hashlib
import importlib.util
import json
import os
import stat
import struct
from pathlib import Path

import numpy as np
import pytest

SRC = Path(__file__).resolve().parents[1] / "experiments" / "comparison_study.py"
spec = importlib.util.spec_from_file_location("comparison_study", SRC)
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


# ------------------------------------------------------------------ decision rule fixtures

def cell(rm_c, ang_c, rm_n, ang_n, lost_c=0.0, lost_n=0.0, ci_ok=True):
    """Cell with best classical E2 and network E4. Difference CI is E2 - E4."""
    d_r, d_a = rm_c - rm_n, ang_c - ang_n
    half_r, half_a = (abs(d_r) * 0.2, abs(d_a) * 0.2) if ci_ok else (abs(d_r) * 5 + 1, abs(d_a) * 5 + 1)
    return {"stats": {"E2": {"rmse_mean_mT": rm_c, "ae_p90_of_seq_p90_deg": ang_c, "lost_rate": lost_c},
                      "E3": {"rmse_mean_mT": 9., "ae_p90_of_seq_p90_deg": 90., "lost_rate": 1.0},
                      "E4": {"rmse_mean_mT": rm_n, "ae_p90_of_seq_p90_deg": ang_n, "lost_rate": lost_n}},
            "pairs": {"E2|E4": {"rmse_diff_ci95_mT": [d_r - half_r, d_r + half_r],
                                "ae_p90_diff_ci95_deg": [d_a - half_a, d_a + half_a]}}}


CLASSICAL_WIN = dict(rm_c=0.5, ang_c=5.0, rm_n=1.0, ang_n=15.0)      # classical better by 10 deg, 50 %
NETWORK_WIN = dict(rm_c=1.0, ang_c=15.0, rm_n=0.5, ang_n=5.0)
TIE = dict(rm_c=1.0, ang_c=10.0, rm_n=1.0, ang_n=10.0)


def res(clean, realistic, secondary=()):
    cells = {"clean": cell(**clean), "realistic": cell(**realistic)}
    for i, c in enumerate(secondary):
        cells[f"sec{i}"] = cell(**c)
    return {"best_classical": "E2", "cells": cells}


def test_classical_wins_both_primary():
    assert cs.decide(res(CLASSICAL_WIN, CLASSICAL_WIN))["outcome"] == "classical_wins"


def test_network_wins_both_primary():
    assert cs.decide(res(NETWORK_WIN, NETWORK_WIN))["outcome"] == "network_wins"


def test_niche_one_primary():
    out = cs.decide(res(CLASSICAL_WIN, TIE))
    assert out["outcome"] == "niche_to_confirm" and out["qualifying"] == [("classical", "clean")]


def test_niche_three_secondary_and_two_secondary_is_inconclusive():
    assert cs.decide(res(TIE, TIE, [NETWORK_WIN] * 3))["outcome"] == "niche_to_confirm"
    assert cs.decide(res(TIE, TIE, [NETWORK_WIN] * 2))["outcome"] == "inconclusive"


def test_split_primary_wins_is_niche_naming_both_sides():
    out = cs.decide(res(CLASSICAL_WIN, NETWORK_WIN))
    assert out["outcome"] == "niche_to_confirm"
    assert set(out["qualifying"]) == {("classical", "clean"), ("network", "realistic")}


def test_neither_reliable_takes_precedence_over_two_primary_win():
    clean = dict(CLASSICAL_WIN, lost_c=0.9, lost_n=0.8)
    assert cs.decide(res(clean, CLASSICAL_WIN))["outcome"] == "neither_reliable"
    # exactly 50 % is not "> 50 %"
    clean = dict(CLASSICAL_WIN, lost_c=0.5, lost_n=0.5)
    assert cs.decide(res(clean, CLASSICAL_WIN))["outcome"] == "classical_wins"


def test_margin_and_ci_conditions_each_block_a_win():
    small_ang = dict(rm_c=0.5, ang_c=11.0, rm_n=1.0, ang_n=15.0)       # 4 deg < 5 deg margin
    small_rmse = dict(rm_c=0.95, ang_c=5.0, rm_n=1.0, ang_n=15.0)      # 5 % < 10 % margin
    wide_ci = dict(CLASSICAL_WIN, ci_ok=False)                          # CI straddles zero
    for bad in (small_ang, small_rmse, wide_ci):
        assert cs.decide(res(bad, bad))["outcome"] == "inconclusive"
    assert cs.decide(res(CLASSICAL_WIN, small_rmse))["outcome"] == "niche_to_confirm"


def test_zero_loser_rmse_cannot_win():
    z = dict(rm_c=0.0, ang_c=0.0, rm_n=0.0, ang_n=20.0)
    assert not cs.beats(cell(**z), "E2", "E4")["win"]


# ------------------------------------------------------------------ bootstrap

def test_paired_bootstrap_known_ci():
    rng = np.random.default_rng(1)
    a = rng.uniform(1, 2, 40)
    out = cs.paired_bootstrap({"A": a, "B": a + 0.5}, {"A": a * 10, "B": a * 10 + 7.0}, n_boot=500, seed=3)
    p = out["A|B"]
    assert p["rmse_diff_ci95_mT"] == pytest.approx([-0.5, -0.5])
    assert p["ae_p90_diff_ci95_deg"] == pytest.approx([-7.0, -7.0])
    assert cs.paired_bootstrap({"A": a, "B": a}, {"A": a, "B": a}, 200)["A|B"]["rmse_diff_ci95_mT"] == [0.0, 0.0]


def test_bootstrap_is_deterministic():
    a, b = np.arange(30.0), np.arange(30.0)[::-1]
    assert cs.paired_bootstrap({"A": a, "B": b}, {"A": a, "B": b}, 100) == \
        cs.paired_bootstrap({"A": a, "B": b}, {"A": a, "B": b}, 100)


# ------------------------------------------------------------------ failure accounting

def _truth(T=50):
    t = np.linspace(0, 1, T)[:, None]
    return np.array([2e-3, 1e-3, 4e-3]) + t * np.array([1e-3, 0, 0])


BIAS = np.array([1e-3, 0.5e-3, 5e-3])


def test_dropped_frames_never_improve_any_metric():
    truth = _truth()
    good = cs.score_sequence(truth, truth.copy(), BIAS, 1e-3)
    assert good["lock_frac"] == 1.0 and good["rmse_T"] == 0 and good["nonfinite_frames"] == 0
    for where in ([0], [10], [10, 11, 12], [49]):
        raw = truth.copy()
        raw[where] = np.nan
        row = cs.score_sequence(truth, raw, BIAS, 1e-3)
        assert row["nonfinite_frames"] == len(where) and row["n_valid_frames"] == 50 - len(where)
        assert row["lock_frac"] < good["lock_frac"]
        assert row["rmse_T"] >= good["rmse_T"] and row["ae_p90_deg"] >= good["ae_p90_deg"]
        assert row["ae_mean_deg"] >= good["ae_mean_deg"]


def test_missing_frame_uses_last_finite_else_bias():
    truth = _truth(4)
    raw = truth.copy()
    raw[0] = np.nan                       # first frame: bias field
    raw[2] = [np.nan, 1.0, 1.0]           # any nonfinite component: last finite estimate
    row = cs.score_sequence(truth, raw, BIAS, 1e-3)
    scored = np.array([BIAS, truth[1], truth[1], truth[3]])
    expect = np.sqrt(np.mean(np.sum((scored - truth) ** 2, axis=1)))
    assert row["rmse_T"] == pytest.approx(expect)


def test_more_than_ten_percent_missing_is_lost():
    truth = _truth(50)
    raw = truth.copy()
    raw[40:45] = np.nan                   # 10 % exactly: not lost by the missing rule
    # frames 40-44 are unlocked but followed by locked frames, so lost stays False
    assert not cs.score_sequence(truth, raw, BIAS, 1e-3)["lost"]
    raw[10:16] = np.nan                   # 11 missing > 10 %
    assert cs.score_sequence(truth, raw, BIAS, 1e-3)["lost"]


def test_all_missing_is_lost_and_unlocked():
    truth = _truth()
    row = cs.score_sequence(truth, np.full_like(truth, np.nan), BIAS, 1e-3)
    assert row["lost"] and row["lock_frac"] == 0 and row["nonfinite_frames"] == 50


# ------------------------------------------------------------------ final guard (temp layout only)

def _layout(tmp_path, partition="final"):
    data = tmp_path / "data" / partition
    cells = []
    for name in ("clean", "realistic"):
        d = data / name / "seed_0"
        d.mkdir(parents=True)
        (d / "dataset.h5").write_bytes(name.encode() * 10)
        (d / "manifest.json").write_text("{}")
        cells.append({"name": name, "data_md5": cs.cell_md5(data / name)})
    manifest = {"partitions": {partition: {"cells": cells}}}
    choice = tmp_path / "choice.json"
    results = tmp_path / "out" / "results.json"
    return data, manifest, choice, results


def _lock(data):
    for p in [*data.rglob("*"), data]:
        p.chmod(p.stat().st_mode & ~0o222)


def _unlock(data):
    for p in [data, *data.rglob("*")]:
        p.chmod(p.stat().st_mode | 0o200)


def test_cell_md5_rule(tmp_path):
    d = tmp_path / "c" / "seed_0"
    d.mkdir(parents=True)
    (d / "dataset.h5").write_bytes(b"abc")
    rel = b"seed_0/dataset.h5"
    assert cs.cell_md5(tmp_path / "c") == hashlib.md5(struct.pack(">I", len(rel)) + rel + b"abc").hexdigest()


def test_final_guard_accepts_when_all_preconditions_hold(tmp_path):
    data, manifest, choice, results = _layout(tmp_path)
    choice.write_text("{}")
    _lock(data)
    try:
        cs.check_partition_guard("final", data, manifest, choice, results)
    finally:
        _unlock(data)


def test_final_guard_refuses_each_missing_precondition(tmp_path):
    data, manifest, choice, results = _layout(tmp_path)
    choice.write_text("{}")
    # (b) write bits present
    with pytest.raises(cs.GuardError, match="write bits"):
        cs.check_partition_guard("final", data, manifest, choice, results)
    _lock(data)
    try:
        # (c) choice file missing
        choice.unlink()
        with pytest.raises(cs.GuardError, match="choice file"):
            cs.check_partition_guard("final", data, manifest, choice, results)
        choice.write_text("{}")
        # (d) results exist, no rerun reason
        results.parent.mkdir()
        results.write_text("{}")
        with pytest.raises(cs.GuardError, match="rerun-reason"):
            cs.check_partition_guard("final", data, manifest, choice, results)
        cs.check_partition_guard("final", data, manifest, choice, results, rerun_reason="why")
        results.unlink()
        # (a) md5 mismatch
        bad = json.loads(json.dumps(manifest))
        bad["partitions"]["final"]["cells"][1]["data_md5"] = "0" * 32
        with pytest.raises(cs.GuardError, match="md5"):
            cs.check_partition_guard("final", data, bad, choice, results)
    finally:
        _unlock(data)


def test_val_requires_only_md5_and_dev_nothing(tmp_path):
    data, manifest, choice, results = _layout(tmp_path, "val")
    cs.check_partition_guard("val", data, manifest, choice, results)       # writable, no choice file: fine
    manifest["partitions"]["val"]["cells"][0]["data_md5"] = "f" * 32
    with pytest.raises(cs.GuardError, match="md5"):
        cs.check_partition_guard("val", data, manifest, choice, results)
    cs.check_partition_guard("dev", data, manifest, choice, results)


def test_main_final_refuses_before_reading_any_data_when_unguarded(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "comparison_test_v1.manifest.json").write_text(
        json.dumps({"partitions": {"final": {"cells": []}}}))
    (tmp_path / "data" / "comparison_test_v1" / "final").mkdir(parents=True)   # writable, no choice file
    with pytest.raises(cs.GuardError):
        cs.main(["--partition", "final", "--out", str(tmp_path / "out"), "--estimators", "E3"])
