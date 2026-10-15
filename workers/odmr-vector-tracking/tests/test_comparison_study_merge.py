"""Tests for experiments/comparison_study_merge.py."""
import importlib.util
import json
from pathlib import Path

import pytest

EXP = Path(__file__).resolve().parents[1] / "experiments"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mg = _load("comparison_study_merge", EXP / "comparison_study_merge.py")
base = _load("test_comparison_study_fixtures", Path(__file__).with_name("test_comparison_study.py"))
cs = base.cs

CASES = {
    "classical_wins": (base.CLASSICAL_WIN, base.CLASSICAL_WIN, []),
    "network_wins": (base.NETWORK_WIN, base.NETWORK_WIN, []),
    "niche_to_confirm": (base.CLASSICAL_WIN, base.TIE, []),
    "inconclusive": (base.TIE, base.TIE, [base.NETWORK_WIN] * 2),
    "neither_reliable": (dict(base.CLASSICAL_WIN, lost_c=0.9, lost_n=0.8), base.CLASSICAL_WIN, []),
}
IDENT = {"estimator_identity": {"E4": {"ckpt_sha256": "abc"}}, "estimators": ["E2", "E3", "E4"],
         "partition": "final", "version": 1, "manifest_sha256": "m", "protocol": "p"}


def write_runs(tmp_path, single, skip=(), dup=None):
    runs = tmp_path / "runs"
    for i, (name, cell) in enumerate(single["cells"].items()):
        if name in skip:
            continue
        d = runs / name
        d.mkdir(parents=True)
        r = dict(IDENT, date=f"t{i}", git={"commit": "c0", "dirty": False}, environment={}, cells={name: cell})
        (d / "results.json").write_text(json.dumps(r))
    if dup:
        d = runs / "dupdir"
        d.mkdir()
        r = dict(IDENT, git={}, cells={dup: single["cells"][dup]})
        (d / "results.json").write_text(json.dumps(r))
    manifest = {"partitions": {"final": {"cells": [{"name": n} for n in single["cells"]]}}}
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(manifest))
    cp = tmp_path / "choice.json"
    cp.write_text(json.dumps({"choice": "E2"}))
    return runs, mp, cp


def run_main(tmp_path, runs, mp, cp):
    out = [tmp_path / n for n in ("r.json", "r.md", "d.md")]
    mg.main(["--runs", str(runs), "--out-json", str(out[0]), "--out-md", str(out[1]),
             "--decision-md", str(out[2]), "--choice", str(cp), "--manifest", str(mp)])
    return out


@pytest.mark.parametrize("outcome", list(CASES))
def test_merge_matches_single_run_decision_and_writes_outcome(tmp_path, outcome):
    single = base.res(*CASES[outcome])
    assert cs.decide(single)["outcome"] == outcome
    runs, mp, cp = write_runs(tmp_path, single)
    oj, om, od = run_main(tmp_path, runs, mp, cp)
    merged = json.loads(oj.read_text())
    assert merged["decision"]["outcome"] == outcome
    assert f"Outcome: {outcome}" in od.read_text()
    assert set(merged["cells"]) == set(single["cells"]) and len(merged["merged_from"]) == len(single["cells"])
    assert "## Cell clean" in om.read_text() and "E2|E4" in om.read_text()


def test_refuses_missing_cell(tmp_path):
    runs, mp, cp = write_runs(tmp_path, base.res(base.TIE, base.TIE), skip=("realistic",))
    with pytest.raises(SystemExit, match="missing final cells: realistic"):
        run_main(tmp_path, runs, mp, cp)


def test_refuses_duplicate_cell(tmp_path):
    runs, mp, cp = write_runs(tmp_path, base.res(base.TIE, base.TIE), dup="clean")
    with pytest.raises(SystemExit, match="appears twice"):
        run_main(tmp_path, runs, mp, cp)


def test_refuses_identity_mismatch(tmp_path):
    runs, mp, cp = write_runs(tmp_path, base.res(base.TIE, base.TIE))
    f = runs / "realistic" / "results.json"
    r = json.loads(f.read_text())
    r["estimator_identity"] = {"E4": {"ckpt_sha256": "zzz"}}
    f.write_text(json.dumps(r))
    with pytest.raises(SystemExit, match="estimator_identity differs"):
        run_main(tmp_path, runs, mp, cp)
