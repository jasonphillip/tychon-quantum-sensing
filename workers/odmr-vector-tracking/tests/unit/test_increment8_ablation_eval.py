"""Synthetic paired evidence for the increment-8 ablation report."""

import csv

from experiments.increment8_ablation_eval import _markdown, build_verdicts


def test_markdown_has_one_table_row_per_comparison_in_json_order():
    comparisons = [
        {"pair": "first vs base", "split": "dwell", "rung": "clean",
         "decode": "direct", "metric": "lost_rate", "difference": 0.01,
         "ci_low": 0.0, "ci_high": 0.02, "margin": 0.01, "verdict": "not shown"},
        {"pair": "second vs base", "split": "fieldcone", "rung": "noisy",
         "decode": "filtered", "metric": "angular_error_p90", "difference": 0.2,
         "ci_low": 0.1, "ci_high": 0.3, "margin": 0.1, "verdict": "inferior"},
    ]
    report = {"comparisons": comparisons, "runs": {
        "first": {"epochs_run": 200, "best_epoch": 180, "wall_s": 12, "truncated": False},
        "second": {"epochs_run": 200, "best_epoch": 190, "wall_s": 13, "truncated": False},
    }, "skipped_pairs": []}

    markdown = _markdown(report)
    table_rows = [line.split("|")[1:-1] for line in markdown.splitlines()
                  if line.startswith("| ") and not line.startswith(("| Pair |", "| Run |"))]
    assert len(table_rows) == len(comparisons)
    assert "| Pair | Split | Rung | Decode | Metric |" in markdown
    assert [tuple(cell.strip() for cell in row[:5]) for row in table_rows] == [
        (row["pair"], row["split"], row["rung"], row["decode"], row["metric"])
        for row in comparisons
    ]


def test_worse_run_and_missing_pairs(tmp_path):
    for name, lost, p90 in (("baseline_e200", 0, 1.0), ("std_only_e200", 1, 2.0)):
        run_dir = tmp_path / name
        run_dir.mkdir()
        for split in ("dwell", "fieldcone"):
            with (run_dir / f"{split}_per_sequence.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["seq_index", "rung", "decode",
                                                        "lost", "angular_error_p90"])
                writer.writeheader()
                writer.writerows({"seq_index": i, "rung": "clean",
                                  "decode": "baseline" if split == "dwell" else "fieldcone",
                                  "lost": bool(lost) if split == "dwell" else lost,
                                  "angular_error_p90": p90}
                                 for i in range(40))

    result = build_verdicts(tmp_path, ["baseline_e200", "std_only_e200", "kd1_e200"],
                            baseline="baseline_e200")
    rows = [row for row in result["comparisons"]
            if row["candidate"] == "std_only_e200" and row["reference"] == "baseline_e200"]
    assert len(rows) == 4
    assert {row["verdict"] for row in rows} == {"inferior"}
    assert any(item["candidate"] == "std_only_e200" and item["reference"] == "kd1_e200"
               for item in result["skipped_pairs"])
    assert all(row["margin_status"] == "proposed, not approved by Jason" for row in rows)

    stale = build_verdicts(tmp_path, ["baseline_e200", "std_only_e200"],
                           baseline="baseline_e200", available_runs={"baseline_e200"})
    assert not stale["comparisons"]
    assert any(item["candidate"] == "std_only_e200" for item in stale["skipped_pairs"])
