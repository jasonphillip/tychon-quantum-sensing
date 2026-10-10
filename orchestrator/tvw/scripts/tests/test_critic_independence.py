"""Critic-independence check: agreement, chance-corrected agreement and Kish effective votes. No model needed."""

import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
STAGE47 = SCRIPTS.parent / "audits" / "stage-4.7-verdicts.csv"


def wide(tmp_path, columns, name="v.csv"):
    """columns: {critic: [verdict per claim]} -> wide CSV with claim_id and <critic>_verdict."""
    path = tmp_path / name
    critics = list(columns)
    n = len(columns[critics[0]])
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["claim_id"] + [f"{c}_verdict" for c in critics])
        for i in range(n):
            writer.writerow([f"c{i}"] + [columns[c][i] for c in critics])
    return path


def run(path, *extra):
    out = subprocess.run([sys.executable, str(SCRIPTS / "critic_independence.py"), str(path), "--json", *extra],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_independent_critics_give_full_votes(tmp_path):
    r = run(wide(tmp_path, {"a": ["SUPPORTED", "SUPPORTED", "UNSUPPORTED", "UNSUPPORTED"],
                            "b": ["SUPPORTED", "UNSUPPORTED", "SUPPORTED", "UNSUPPORTED"]}))
    assert r["n_critics"] == 2 and r["n_claims"] == 4
    assert r["raw_agreement"] == pytest.approx(0.5)
    assert r["fleiss_kappa"] == pytest.approx(0.0) and r["mean_pairwise_cohen_kappa"] == pytest.approx(0.0)
    assert r["mean_pairwise_phi"] == pytest.approx(0.0)
    assert r["n_eff"] == pytest.approx(2.0)


def test_copied_critic_gives_one_vote(tmp_path):
    v = ["SUPPORTED", "SUPPORTED", "UNSUPPORTED", "CONTRADICTED"]
    r = run(wide(tmp_path, {"a": v, "b": list(v), "c": list(v)}))
    assert r["raw_agreement"] == 1.0 and r["mean_pairwise_phi"] == pytest.approx(1.0)
    assert r["n_eff"] == pytest.approx(1.0)        # Kish: 3 / (1 + 2 * 1)


def test_constant_agreement_is_not_evidence(tmp_path):
    # Ten of ten identical verdicts: agreement looks perfect, but with no variance
    # neither kappa nor the correlation is defined, so the effective votes are undefined.
    r = run(wide(tmp_path, {"a": ["SUPPORTED"] * 10, "b": ["SUPPORTED"] * 10}))
    assert r["raw_agreement"] == 1.0
    assert r["fleiss_kappa"] is None and r["mean_pairwise_phi"] is None and r["n_eff"] is None
    assert "no variance" in r["n_eff_note"]


def test_long_format_matches_wide(tmp_path):
    cols = {"a": ["SUPPORTED", "SUPPORTED", "UNSUPPORTED", "WEAK"], "b": ["SUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "WEAK"]}
    long_path = tmp_path / "long.csv"
    with long_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["claim", "critic", "verdict"])
        for critic, verdicts in cols.items():
            for i, v in enumerate(verdicts):
                writer.writerow([f"c{i}", critic, v])
    assert run(long_path) == run(wide(tmp_path, cols))


def test_error_rows_are_dropped_and_counted(tmp_path):
    r = run(wide(tmp_path, {"a": ["SUPPORTED", "ERROR", "UNSUPPORTED"], "b": ["SUPPORTED", "SUPPORTED", "UNSUPPORTED"]}))
    assert r["n_claims"] == 2 and r["n_dropped"] == 1


def test_truth_mode_uses_error_vectors(tmp_path):
    # With reference verdicts, phi is computed on error indicators (the paper's method).
    verdicts = wide(tmp_path, {"a": ["SUPPORTED", "SUPPORTED", "UNSUPPORTED", "UNSUPPORTED"],
                               "b": ["SUPPORTED", "SUPPORTED", "UNSUPPORTED", "UNSUPPORTED"]})
    truth = tmp_path / "truth.csv"
    truth.write_text("claim,verdict\nc0,SUPPORTED\nc1,UNSUPPORTED\nc2,UNSUPPORTED\nc3,SUPPORTED\n")
    r = run(verdicts, "--truth", str(truth))
    assert r["basis"] == "errors against --truth"
    assert r["mean_pairwise_phi"] == pytest.approx(1.0) and r["n_eff"] == pytest.approx(1.0)


def test_runs_on_committed_stage47_csv():
    r = run(STAGE47)
    assert r["n_critics"] == 2
    assert r["n_claims"] + r["n_dropped"] == 114
    assert r["n_dropped"] == 21                     # nemotron-mini returned ERROR on 21 claims
    assert 0.0 <= r["raw_agreement"] <= 1.0
    text = subprocess.run([sys.executable, str(SCRIPTS / "critic_independence.py"), str(STAGE47)],
                          capture_output=True, text=True, check=True).stdout
    assert "effective votes" in text.lower()


def test_near_constant_critics_get_a_prevalence_warning(tmp_path):
    # Two critics that call almost everything SUPPORTED agree often by prevalence alone.
    a = ["SUPPORTED"] * 19 + ["UNSUPPORTED"]
    b = ["SUPPORTED"] * 18 + ["UNSUPPORTED", "SUPPORTED"]
    r = run(wide(tmp_path, {"a": a, "b": b}))
    assert r["positive_rate"] == {"a": pytest.approx(0.95), "b": pytest.approx(0.95)}
    assert r["raw_agreement"] == pytest.approx(0.9) and r["fleiss_kappa"] < 0.1
    assert "prevalence" in r["prevalence_warning"]
    text = subprocess.run([sys.executable, str(SCRIPTS / "critic_independence.py"), str(wide(tmp_path, {"a": a, "b": b}, "w2.csv"))],
                          capture_output=True, text=True, check=True).stdout
    assert "raw agreement: 0.900" in text and "prevalence" in text


def test_balanced_critics_have_no_prevalence_warning(tmp_path):
    r = run(wide(tmp_path, {"a": ["SUPPORTED", "SUPPORTED", "UNSUPPORTED", "UNSUPPORTED"],
                            "b": ["SUPPORTED", "UNSUPPORTED", "SUPPORTED", "UNSUPPORTED"]}))
    assert r["prevalence_warning"] is None
