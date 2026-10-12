"""Reproduce the clamp-limited additive-correction oracle from 2026-06-21."""

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
DATASETS = (
    ("production_50k", "val"),
    ("production_50k_v2_aic", "test"),
)
CLAMPS = (2.25, 2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 25.0)
INT8_SOURCE = HERE / "fcnn_v2_int8_float_equivalence_2026-06-21.json"
DASHBOARD_CEILING_PCT = 9.3


def deployed_reduction(default):
    """Use the recorded INT8 clamped metric when it identifies this evaluation."""
    if not INT8_SOURCE.is_file():
        return default
    source = json.loads(INT8_SOURCE.read_text(encoding="utf-8"))
    if (
        source.get("split") == "test"
        and Path(source.get("dataset", "")).name == "production_50k_v2_aic"
        and source.get("clamp_uT") == 2.25
    ):
        value = source.get("int8_accuracy", {}).get("clamped_reduction_pct")
        if value is not None:
            return float(value)
    return default


def calculate(data_root):
    results = {}
    for dataset, split in DATASETS:
        with np.load(data_root / dataset / "pid_residuals.npz") as data:
            delta_key = f"{split}_delta_b_uT"
            if delta_key in data:
                delta = data[delta_key]
            else:
                delta = data[f"{split}_b_mag_uT"] - data[f"{split}_b_pid_uT"]
        baseline = np.abs(delta).mean()
        print(f"\n== {dataset} {split} baseline MAE {baseline}")
        print("clamp_uT, oracle_mae, oracle_reduction_pct")
        rows = []
        for clamp in CLAMPS:
            error = np.abs(delta - np.clip(delta, -clamp, clamp))
            oracle_mae = error.mean()
            reduction = (1 - oracle_mae / baseline) * 100
            print(f"{clamp:.2f}, {oracle_mae:.4f}, {reduction:.2f}")
            rows.append(
                {
                    "clamp_uT": clamp,
                    "oracle_mae_uT": float(oracle_mae),
                    "oracle_reduction_pct": float(reduction),
                }
            )
        results[dataset] = {"split": split, "baseline_mae_uT": float(baseline), "rows": rows}
    return results


def markdown_report(results, captured, run_date):
    lines = [
        f"# FCNN v2 Clamp Oracle Ceiling - {run_date}",
        "",
        "Saved rerun of the bounded additive-correction oracle. No model training is involved.",
        "",
    ]
    for dataset, split in DATASETS:
        result = results[dataset]
        lines += [
            f"- Dataset: `{dataset}`, split `{split}`; PID baseline MAE: {result['baseline_mae_uT']:.4f} µT.",
            "",
            "| Clamp (µT) | Oracle MAE (µT) | Oracle reduction vs PID |",
            "|---:|---:|---:|",
        ]
        for row in result["rows"]:
            lines.append(
                f"| {row['clamp_uT']:.2f} | {row['oracle_mae_uT']:.4f} "
                f"| {row['oracle_reduction_pct']:.2f}% |"
            )
        lines.append("")
    lines += [
        "## Provenance",
        "",
        "- First computed 2026-06-21 (about 22:49 UTC) as an inline, unsaved script in a coding-agent session.",
        f"- This file re-runs the same arithmetic from saved `experiments/clamp_oracle_ceiling.py` on {run_date}.",
        "- The oracle clips the true residual to ±clamp and subtracts that bounded correction from the residual. Its MAE is `mean(abs(delta - clip(delta, -clamp, clamp)))`.",
        f"- Deployed INT8 clamped reduction: {captured['deployed_pct']:.4f}% on the same AIC test split, from `experiments/{INT8_SOURCE.name}`.",
        f"- Captured fraction: 4.9033/{captured['ceiling_pct']:.2f} = {captured['fraction_exact']:.1%} using the exact oracle ceiling ({captured['ceiling_pct']:.2f}% displayed); 4.9033/9.3 = {captured['fraction_with_dashboard_constant']:.1%} (displayed as \"~53%\") with the dashboard's 9.3 constant.",
        "- Caveat: synthetic data, scalar residual target, not lab-validated.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path.home() / "projects/tychon-shared-data")
    parser.add_argument("--deployed-reduction-pct", type=float, default=4.9033)
    parser.add_argument("--out-json", type=Path, default=HERE / "fcnn_v2_clamp_oracle_ceiling_2026-10-12.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "fcnn_v2_clamp_oracle_ceiling_2026-10-12.md")
    args = parser.parse_args()

    results = calculate(args.data_root)
    deployed = deployed_reduction(args.deployed_reduction_pct)
    ceiling = results["production_50k_v2_aic"]["rows"][0]["oracle_reduction_pct"]
    run_date = date.today().isoformat()
    captured = {
        "deployed_pct": deployed,
        "ceiling_pct": ceiling,
        "fraction_exact": deployed / ceiling,
        "fraction_with_dashboard_constant": deployed / DASHBOARD_CEILING_PCT,
        "date_run": run_date,
    }
    args.out_json.write_text(
        json.dumps({"datasets": results, "captured_fraction": captured}, indent=2) + "\n",
        encoding="utf-8",
    )
    args.out_md.write_text(markdown_report(results, captured, run_date), encoding="utf-8")


if __name__ == "__main__":
    main()
