"""Synthetic paired evidence for the increment-8 ablation report."""

import csv

from experiments.increment8_ablation_eval import build_verdicts


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
