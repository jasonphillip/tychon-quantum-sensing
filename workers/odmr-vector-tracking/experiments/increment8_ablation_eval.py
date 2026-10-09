"""Evaluate single-checkpoint increment-8 ablations and compare paired sequences.

Uses increment8_eval's dwell/field-cone functions, including their fixed noise rungs.
The margins are proposed retrospective thresholds, not deployment approval.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import increment8_eval as evaluator
from odmr_vector_tracking.evaluation.noninferiority import Outcome, compare_paired


MARGIN_STATUS = "proposed, not approved by Jason"
# docs/noninferiority_reverdict.md proposes lock-loss and post-crossing angular-error
# margins. The angular threshold is reused here for per-sequence p90 as a proposed
# sensitivity check; the document does not approve a p90-specific threshold.
METRICS = {"lost_rate": ("lost", 0.01, True),
           "angular_error_p90": ("angular_error_p90", 0.1, False)}
SPLITS = ("dwell", "fieldcone")


def _number(value: str) -> float:
    if value in ("True", "False"):
        return 1.0 if value == "True" else 0.0
    return float(value)


def _read_rows(path: Path) -> dict[tuple[str, str], dict[str, dict]]:
    groups: dict[tuple[str, str], dict[str, dict]] = {}
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            group = groups.setdefault((row["rung"], row["decode"]), {})
            seq = row["seq_index"]
            if seq in group:
                raise ValueError(f"duplicate sequence {seq} in {path}")
            group[seq] = row
    return groups


def _compare(candidate: dict[str, dict], reference: dict[str, dict],
             field: str, margin: float, binary: bool) -> dict:
    if candidate.keys() != reference.keys():
        raise ValueError("candidate and reference need matching sequence IDs")
    a, b = [], []
    for seq in sorted(candidate, key=lambda x: int(x)):
        av, bv = _number(candidate[seq][field]), _number(reference[seq][field])
        if not (math.isfinite(av) and math.isfinite(bv)):
            continue
        a.append(Outcome(seq, "single", av))
        b.append(Outcome(seq, "single", bv))
    if not a:
        return {"difference": None, "ci_low": None, "ci_high": None,
                "n_sequences": 0, "verdict": "not shown"}
    result = compare_paired(a, b, margin=margin, binary=binary)
    verdict = ("inferior" if math.isfinite(result.ci_low) and result.ci_low > margin
               else "non-inferior" if result.verdict in ("non-inferior", "superior")
               else "not shown")
    return {"difference": result.estimate,
            "ci_low": result.ci_low if math.isfinite(result.ci_low) else None,
            "ci_high": result.ci_high if math.isfinite(result.ci_high) else None,
            "n_sequences": result.n_sequences, "verdict": verdict}


def build_verdicts(out_dir: Path, runs: list[str], *, baseline: str,
                   available_runs: set[str] | None = None) -> dict:
    """Read written per-sequence tables and return paired verdicts and skips."""
    names = list(dict.fromkeys(runs))
    selected = set(names) | {baseline}
    available = selected if available_runs is None else available_runs
    pairs = [(name, baseline) for name in names if name != baseline]
    pairs += [("std_only_e200", "kd1_e200"), ("ens_only_e200", "baseline_e200")]
    trunks = sorted(name for name in names if name.startswith("trunk_only_s")
                    and name.endswith("_e200"))
    pairs += list(itertools.combinations(trunks, 2))
    pairs = list(dict.fromkeys(pairs))
    rows, skipped = [], []
    for candidate, reference in pairs:
        missing = [name for name in (candidate, reference)
                   if name not in available
                   or any(not (out_dir / name / f"{split}_per_sequence.csv").is_file()
                          for split in SPLITS)]
        if missing:
            skipped.append({"candidate": candidate, "reference": reference,
                            "reason": "missing evaluation tables", "missing_runs": missing})
            continue
        for split in SPLITS:
            a = _read_rows(out_dir / candidate / f"{split}_per_sequence.csv")
            b = _read_rows(out_dir / reference / f"{split}_per_sequence.csv")
            if a.keys() != b.keys():
                skipped.append({"candidate": candidate, "reference": reference,
                                "split": split, "reason": "unmatched rung/decode cells"})
                continue
            for (rung, decode), candidate_rows in sorted(a.items()):
                reference_rows = b[(rung, decode)]
                if candidate_rows.keys() != reference_rows.keys():
                    skipped.append({"candidate": candidate, "reference": reference,
                                    "split": split, "rung": rung, "decode": decode,
                                    "reason": "unmatched sequence IDs"})
                    continue
                for metric, (field, margin, binary) in METRICS.items():
                    result = _compare(candidate_rows, reference_rows, field, margin, binary)
                    rows.append({"candidate": candidate, "reference": reference,
                                 "pair": f"{candidate} vs {reference}", "split": split,
                                 "rung": rung, "decode": decode, "metric": metric,
                                 "margin": margin, "margin_status": MARGIN_STATUS,
                                 **result})
    return {"margin_status": MARGIN_STATUS,
            "margin_source": "docs/noninferiority_reverdict.md",
            "angular_p90_margin_note": "0.1 degree is proposed for post-crossing mean; reused for p90 sensitivity only",
            "unsupported_metrics": ["lock_fraction: no per-frame lock fraction in increment8_eval output"],
            "comparisons": rows, "skipped_pairs": skipped}


def _truncated(run_dir: Path, summary: dict) -> bool:
    status = summary.get("status", "")
    if isinstance(status, dict):
        status = status.get("state", status.get("status", ""))
    return ((run_dir / "truncated.txt").exists()
            or str(status).lower() in {"truncated", "interrupted", "stopped_early"}
            or summary.get("truncated") is True)


def _markdown(report: dict) -> str:
    lines = ["# Increment-8 single-component ablation verdicts", "",
             f"Margins: **{MARGIN_STATUS}**. Candidate minus reference; lower is better.",
             "The 0.1 degree angular margin is a proposed p90 sensitivity threshold.", "",
             "| Pair | Split | Metric | Difference | CI (95%) | Margin | Verdict |",
             "|---|---|---|---:|---:|---:|---|"]
    for row in report["comparisons"]:
        fmt = lambda x: "—" if x is None else f"{x:.4f}"
        cell = f"{row['metric']} ({row['rung']}, {row['decode']})"
        ci = f"[{fmt(row['ci_low'])}, {fmt(row['ci_high'])}]"
        lines.append(f"| {row['pair']} | {row['split']} | {cell} | "
                     f"{fmt(row['difference'])} | {ci} | {fmt(row['margin'])} | {row['verdict']} |")
    lines += ["", "## Runs", "", "| Run | Epochs run | Best epoch | Wall seconds | Truncated |",
              "|---|---:|---:|---:|---|"]
    for name, run in report["runs"].items():
        lines.append(f"| {name} | {run['epochs_run']} | {run['best_epoch']} | "
                     f"{run['wall_s']} | {run['truncated']} |")
    lines += ["", "## Skipped pairs", ""]
    lines += [f"- {item['candidate']} vs {item['reference']}: {item['reason']}"
              for item in report["skipped_pairs"]]
    lines += ["", "Lock fraction is unsupported by the per-sequence evaluator output."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True, type=Path)
    parser.add_argument("--runs", required=True, nargs="+")
    parser.add_argument("--baseline", default="baseline_e200")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()
    device = torch.device(args.device)
    args.out.mkdir(parents=True, exist_ok=True)
    metadata = {}
    for name in dict.fromkeys([*args.runs, args.baseline]):
        run_dir = args.runs_dir / name
        if not (run_dir / "best.pt").is_file() or not (run_dir / "summary.json").is_file():
            continue
        summary = json.loads((run_dir / "summary.json").read_text())
        metadata[name] = {key: summary.get(key) for key in ("epochs_run", "best_epoch", "wall_s")}
        metadata[name]["truncated"] = _truncated(run_dir, summary)
        target = args.out / name
        target.mkdir(parents=True, exist_ok=True)
        for split, evaluate in (("dwell", evaluator.dwell_split),
                                ("fieldcone", evaluator.fieldcone)):
            sequence_rows: list[dict] = []
            pooled = evaluate(args.runs_dir, [name], device, sequence_rows)
            (target / f"{split}.json").write_text(json.dumps(pooled, indent=1))
            evaluator.write_sequence_csv(target / f"{split}_per_sequence.csv", sequence_rows)
    report = build_verdicts(args.out, args.runs, baseline=args.baseline,
                            available_runs=set(metadata))
    report["runs"] = metadata
    (args.out / "verdicts.json").write_text(json.dumps(report, indent=1))
    (args.out / "verdicts.md").write_text(_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
