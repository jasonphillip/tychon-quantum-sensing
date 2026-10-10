"""Synthetic paired evidence for the increment-8 ablation report."""

import csv
from types import SimpleNamespace

import h5py
import numpy as np
import pytest
import torch

from experiments.increment8_ablation_eval import _compare, _markdown, build_verdicts
from experiments import increment8_eval as evaluator
from experiments.increment8_eval import _angular_row


def test_transient_unlock_is_not_irrecoverable_loss():
    from experiments.increment6_fieldcone import lock_stats

    t = 40
    true = np.tile([1.0, 0.0, 0.0], (t, 1))
    estimate = true.copy()
    estimate[12:22] = [0.0, 1.0, 0.0]
    assert _angular_row(true, estimate)["lock_fraction"] == pytest.approx((t - 10) / t)
    assert lock_stats(true, estimate)["lost"] == 0


def test_undefined_angles_count_as_unlocked():
    true = np.tile([1.0, 0.0, 0.0], (4, 1))
    estimate = true.copy()
    estimate[1] = [0.0, 0.0, 0.0]
    assert _angular_row(true, estimate)["lock_fraction"] == pytest.approx(0.75)


def test_lock_fraction_verdict_uses_lower_bound_and_proposed_margin():
    reference = {str(i): {"lock_fraction": "1.0"} for i in range(40)}
    near = {str(i): {"lock_fraction": "0.995"} for i in range(40)}
    far = {str(i): {"lock_fraction": "0.98"} for i in range(40)}
    good = _compare(near, reference, "lock_fraction", 0.01, False, True)
    bad = _compare(far, reference, "lock_fraction", 0.01, False, True)
    assert good["difference"] == pytest.approx(-0.005)
    assert good["ci_low"] > -0.01
    assert good["verdict"] == "non-inferior"
    assert bad["ci_high"] < -0.01
    assert bad["verdict"] == "inferior"


def test_dwell_and_fieldcone_emit_lock_fraction_in_csv_and_pooled_json(tmp_path, monkeypatch):
    t = 40
    true = np.tile([1.0, 0.0, 0.0], (1, t, 1))
    estimate = true[0].copy()
    estimate[12:22] = [0.0, 1.0, 0.0]
    ds = SimpleNamespace(spectra=np.zeros((1, t, 1)), B_true=true)
    with h5py.File(tmp_path / "dataset.h5", "w") as fh:
        test = fh.create_group("test")
        test["template_idx"] = [0]
        test["exit_topology"] = [0]
        test["bucket_class"] = [0]
        test["target_angle_deg"] = [0.0]
        test["target_B_mT"] = [5.0]

    monkeypatch.setattr(evaluator, "DWELL", tmp_path)
    monkeypatch.setattr(evaluator, "FIELDCONE", tmp_path)
    monkeypatch.setattr(evaluator, "RUNGS", (("clean", None),))
    monkeypatch.setattr(evaluator, "validate_dataset_dir",
                        lambda _: {"linewidth_Hz": 1.0, "line_depths": [0.1]})
    monkeypatch.setattr(evaluator, "SequenceDatasetLoader",
                        lambda _: SimpleNamespace(load_split=lambda _: ds))
    monkeypatch.setattr(evaluator.nmr, "noisy_copy", lambda clean, _: clean)
    monkeypatch.setattr(evaluator.ir, "run_ckpt_outputs",
                        lambda *_: ([{"b_est": estimate}], None))
    monkeypatch.setattr(evaluator.ir, "decode_tracked", lambda *_: None)
    monkeypatch.setattr(evaluator.nmr, "_row", lambda *_: {"lost": False})
    monkeypatch.setattr(evaluator.nmr, "aggregate",
                        lambda rows, labels: {"cov/cross": {"idsw_opp": [0, 1],
                                                             "lock_loss": [0, 1]}})

    dwell_rows, field_rows = [], []
    dwell = evaluator.dwell_split(tmp_path, ["seed"], torch.device("cpu"), dwell_rows)
    field = evaluator.fieldcone(tmp_path, ["seed"], torch.device("cpu"), field_rows)
    expected = pytest.approx((t - 10) / t)
    assert all(row["lock_fraction"] == expected for row in dwell_rows + field_rows)
    for decode in ("baseline", "stack5"):
        pooled = dwell["cells"]["clean"][f"decode:{decode}"]["seed"]["cov/cross"]
        assert pooled["lock_fraction"] == expected
        assert pooled["lock_fraction_all"] == [expected]
    pooled = field["cells"]["clean"]["seed"]
    assert pooled["lock_fraction"] == expected
    assert pooled["lock_fraction_all"] == [expected]
    assert pooled["lost_all"] == [0]

    for name, rows in (("dwell", dwell_rows), ("fieldcone", field_rows)):
        path = tmp_path / f"{name}.csv"
        evaluator.write_sequence_csv(path, rows)
        with path.open(newline="") as fh:
            assert all(float(row["lock_fraction"]) == expected
                       for row in csv.DictReader(fh))


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
    for name, lost, p90, lock in (("baseline_e200", 0, 1.0, 1.0),
                                  ("std_only_e200", 1, 2.0, 0.8)):
        run_dir = tmp_path / name
        run_dir.mkdir()
        for split in ("dwell", "fieldcone"):
            with (run_dir / f"{split}_per_sequence.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["seq_index", "rung", "decode",
                                                        "lost", "angular_error_p90",
                                                        "lock_fraction"])
                writer.writeheader()
                writer.writerows({"seq_index": i, "rung": "clean",
                                  "decode": "baseline" if split == "dwell" else "fieldcone",
                                  "lost": bool(lost) if split == "dwell" else lost,
                                  "angular_error_p90": p90, "lock_fraction": lock}
                                 for i in range(40))

    result = build_verdicts(tmp_path, ["baseline_e200", "std_only_e200", "kd1_e200"],
                            baseline="baseline_e200")
    rows = [row for row in result["comparisons"]
            if row["candidate"] == "std_only_e200" and row["reference"] == "baseline_e200"]
    assert len(rows) == 6
    assert {row["verdict"] for row in rows} == {"inferior"}
    assert [row["difference"] for row in rows if row["metric"] == "lock_fraction"] == \
        pytest.approx([-0.2, -0.2])
    assert any(item["candidate"] == "std_only_e200" and item["reference"] == "kd1_e200"
               for item in result["skipped_pairs"])
    assert all(row["margin_status"] == "proposed, not approved by Jason" for row in rows)

    stale = build_verdicts(tmp_path, ["baseline_e200", "std_only_e200"],
                           baseline="baseline_e200", available_runs={"baseline_e200"})
    assert not stale["comparisons"]
    assert any(item["candidate"] == "std_only_e200" for item in stale["skipped_pairs"])
