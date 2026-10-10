import csv
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def write_csv(path, fields, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_six_row_hand_calculation(tmp_path):
    from claim_eval import evaluate

    ids = [f"r{i}" for i in range(1, 7)]
    labels_a = ["supported", "contradicted", "stale", "unsupported", "supported", "causal"]
    labels_b = ["supported", "contradicted", "supported", "unsupported", "supported", "unsupported"]
    for name, labels in (("a", labels_a), ("b", labels_b)):
        write_csv(tmp_path / f"{name}.csv", ["id", "label", "evidence", "rationale"],
                  [dict(id=i, label=label, evidence="e", rationale="r") for i, label in zip(ids, labels)])
    write_csv(tmp_path / "constructed.csv", ["id", "label", "origin"],
              [dict(id="r6", label="causal", origin="causal")])
    write_csv(tmp_path / "verdicts.csv", ["claim_id", "q_verdict", "n_verdict"],
              [dict(claim_id=i, q_verdict=q, n_verdict=n) for i, q, n in zip(ids,
               ["SUPPORTED", "SUPPORTED", "SUPPORTED", "UNSUPPORTED", "ERROR", "SUPPORTED"],
               ["SUPPORTED", "CONTRADICTED", "SUPPORTED", "UNSUPPORTED", "SUPPORTED", "SUPPORTED"])])
    result = evaluate(tmp_path / "verdicts.csv", tmp_path / "constructed.csv",
                      tmp_path / "a.csv", tmp_path / "b.csv")
    assert result["final_labels"] == dict(zip(ids, ["supported", "contradicted", "stale", "unsupported", "supported", "causal"]))
    assert result["contested"] == ["r3"]
    assert result["labelers"]["kappa"] == pytest.approx(12 / 17)
    assert result["labelers"]["a"]["constructed_binary_accuracy"] == 1
    assert result["labelers"]["a"]["constructed_five_class_accuracy"] == 1
    assert result["labelers"]["b"]["constructed_binary_accuracy"] == 1
    assert result["labelers"]["b"]["constructed_five_class_accuracy"] == 0
    assert result["labelers"]["a"]["original_supported_count"] == 2
    assert result["labelers"]["b"]["original_supported_count"] == 3
    pooled = result["metrics"]["all"]["pooled"]
    for key, expected in dict(n=6, accept_precision=1/3, accept_recall=1/2,
                              false_acceptance_rate=2/3, abstention_rate=1/6,
                              parser_failure_rate=1/6).items():
        assert pooled["ensemble"][key] == pytest.approx(expected)
    assert pooled["q"]["false_acceptance_rate"] == pytest.approx(3/4)
    assert pooled["n"]["accept_recall"] == 1
    assert result["metrics"]["uncontested"]["pooled"]["ensemble"]["false_acceptance_rate"] == 1/2
    assert result["dependence"]["all"]["pooled"]["both_wrong_rate"] == pytest.approx(1/3)
    assert result["dependence"]["all"]["pooled"]["error_correlation"] == pytest.approx(1/2)
    script = Path(__file__).resolve().parents[1] / "claim_eval.py"
    report = tmp_path / "report.md"
    subprocess.run([sys.executable, str(script), "--verdicts", str(tmp_path / "verdicts.csv"),
                    "--constructed", str(tmp_path / "constructed.csv"),
                    "--labels-a", str(tmp_path / "a.csv"), "--labels-b", str(tmp_path / "b.csv"),
                    "--out", str(report)], check=True)
    assert "Decision per row: accept iff every critic verdict is SUPPORTED" in report.read_text()
    assert "## Uncontested rows" in report.read_text()
    labels_only = subprocess.run([sys.executable, str(script), "--labels-only",
                                  "--constructed", str(tmp_path / "constructed.csv"),
                                  "--labels-a", str(tmp_path / "a.csv"),
                                  "--labels-b", str(tmp_path / "b.csv")],
                                 check=True, capture_output=True, text=True)
    assert "Cohen's kappa" in labels_only.stdout
    assert "Accept precision" not in labels_only.stdout


def test_generator_blind_ids_and_seed(tmp_path):
    import json
    from claim_eval_candidates import generate

    claims = tmp_path / "claims.jsonl"
    source = [dict(id=f"c{i}", text=text, section="S", source_line=i, kind=kind)
              for i, (text, kind) in enumerate((
                  ("Latency is 12 ms in v2.0.", "numerical"),
                  ("Power is 3 W in v2.1.", "numerical"),
                  ("Error correlates with drift.", "definitive")), 1)]
    claims.write_text("".join(json.dumps(row) + "\n" for row in source))
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate(claims, first, 3, 5, 4)
    generate(claims, second, 3, 5, 4)
    for name in ("candidates.jsonl", "labels_constructed.csv", "label_input.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    candidates = [json.loads(line) for line in (first / "candidates.jsonl").read_text().splitlines()]
    blind = list(csv.DictReader((first / "label_input.csv").open()))
    constructed = list(csv.DictReader((first / "labels_constructed.csv").open()))
    assert len(candidates) == len(blind) == 8
    assert len(constructed) == 5
    assert set(blind[0]) == {"id", "text"}
    assert all(row["id"].startswith("e") for row in candidates)
    originals = {row["id"]: row for row in candidates if row["origin"] == "original"}
    assert {row["source_id"] for row in originals.values()} == {row["id"] for row in source}
    assert all(row["parent_id"] in originals for row in candidates if row["origin"] != "original")


def test_generator_balances_all_five_origins(tmp_path):
    import json as _json
    import claim_eval_candidates as gen
    claims = [
        {"id": f"c{i}", "text": f"Build v3.{i} on 2026-04-2{i % 10} runs at {100 + i} MHz and provides {i + 1} ms latency.",
         "section": "s", "source_line": i, "kind": "numerical"}
        for i in range(40)
    ]
    src = tmp_path / "claims.jsonl"
    src.write_text("\n".join(_json.dumps(c) for c in claims))
    gen.generate(src, tmp_path / "out", 30, 30, 0)
    rows = [_json.loads(l) for l in (tmp_path / "out" / "candidates.jsonl").read_text().splitlines()]
    counts = {}
    for r in rows:
        counts[r["origin"]] = counts.get(r["origin"], 0) + 1
    assert counts == {"original": 30, "unit_error": 6, "revision_mismatch": 6, "unmeasured": 6, "stale": 6, "causal": 6}
    stale = [r for r in rows if r["origin"] == "stale"]
    assert all("revision." not in r["text"] for r in stale)   # stale edits change a version or date token


def test_third_labeler_majority_and_policy(tmp_path):
    from claim_eval import evaluate

    ids = ["r1", "r2", "r3", "r4"]
    labels = {"a": ["supported", "supported", "supported", "unsupported"],
              "b": ["supported", "supported", "unsupported", "unsupported"],
              "c": ["supported", "contradicted", "contradicted", "supported"]}
    for name, column in labels.items():
        write_csv(tmp_path / f"{name}.csv", ["id", "label", "evidence", "rationale"],
                  [dict(id=i, label=label, evidence="e", rationale="r") for i, label in zip(ids, column)])
    write_csv(tmp_path / "constructed.csv", ["id", "label", "origin"], [])
    write_csv(tmp_path / "verdicts.csv", ["claim_id", "c1_verdict", "c2_verdict", "c3_verdict"],
              [dict(claim_id=i, c1_verdict=x, c2_verdict=y, c3_verdict=z) for i, x, y, z in zip(ids,
               ["SUPPORTED", "SUPPORTED", "CONTRADICTED", "UNSUPPORTED"],
               ["CONTRADICTED", "SUPPORTED", "CONTRADICTED", "UNSUPPORTED"],
               ["SUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED"])])
    paths = (tmp_path / "verdicts.csv", tmp_path / "constructed.csv", tmp_path / "a.csv", tmp_path / "b.csv")

    # Majority key: r2 two of three say supported; r3 all differ -> most adverse; r4 A=B.
    subset = evaluate(*paths, labels_c_path=tmp_path / "c.csv", critics=["c1", "c3"], policy="majority")
    assert subset["final_labels"] == dict(zip(ids, ["supported", "supported", "contradicted", "unsupported"]))
    assert subset["contested"] == ["r2", "r3", "r4"]
    assert subset["labelers"]["kappa_ab"] == pytest.approx(0.5)
    assert {"kappa_ac", "kappa_bc"} <= set(subset["labelers"])
    # Only c1 and c3 form the ensemble: r1 (S, -, S) is accepted although c2 says CONTRADICTED.
    assert subset["critic_columns"] == ["c1_verdict", "c3_verdict"]
    pooled = subset["metrics"]["all"]["pooled"]
    assert "c2" not in pooled
    assert pooled["ensemble"]["accept_precision"] == 1
    assert pooled["ensemble"]["accept_recall"] == pytest.approx(1 / 2)
    assert pooled["ensemble"]["abstention_rate"] == pytest.approx(2 / 4)

    # Majority over all three critics accepts r2 (SUPPORTED, SUPPORTED, UNSUPPORTED); r1 abstains (one CONTRADICTED).
    three = evaluate(*paths, labels_c_path=tmp_path / "c.csv", policy="majority")["metrics"]["all"]["pooled"]["ensemble"]
    assert three["accept_precision"] == 1 and three["accept_recall"] == pytest.approx(1 / 2)
    assert three["abstention_rate"] == pytest.approx(1 / 4)
    # Unanimous (default) over all three accepts nothing.
    unanimous = evaluate(*paths, labels_c_path=tmp_path / "c.csv")["metrics"]["all"]["pooled"]["ensemble"]
    assert unanimous["accept_precision"] is None and unanimous["abstention_rate"] == pytest.approx(1 / 4)

    script = Path(__file__).resolve().parents[1] / "claim_eval.py"
    report = tmp_path / "report.md"
    subprocess.run([sys.executable, str(script), "--verdicts", str(paths[0]), "--constructed", str(paths[1]),
                    "--labels-a", str(paths[2]), "--labels-b", str(paths[3]), "--labels-c", str(tmp_path / "c.csv"),
                    "--critics", "c1,c3", "--policy", "majority", "--out", str(report)], check=True)
    text = report.read_text()
    assert "accept iff at least 2 verdicts are SUPPORTED and none is CONTRADICTED" in text
    assert "c2" not in text.split("## All rows")[1]
