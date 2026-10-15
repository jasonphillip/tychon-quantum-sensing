"""Merge per-cell comparison_study results.json files and apply the registered decision rule.

Usage: comparison_study_merge.py --runs <dir/cell/results.json ...> --out-json ... --out-md ...
       --decision-md ... --choice docs/best_classical_choice_2026-10.json
Refuses when any cell of the manifest's final partition is missing or duplicated.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_study():
    spec = importlib.util.spec_from_file_location("comparison_study", ROOT / "experiments" / "comparison_study.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)      # module-level only; main() is guarded by __name__
    return mod


IDENTITY_KEYS = ("partition", "version", "estimators", "estimator_identity", "manifest_sha256", "protocol")
PROVENANCE_KEYS = ("date", "git", "environment", "max_sequences", "rerun_reason")


def merge(runs_dir, manifest, choice, partition="final"):
    runs_dir = Path(runs_dir)
    files = sorted(runs_dir.glob("*/results.json"))
    if not files:
        raise SystemExit(f"no <cell>/results.json under {runs_dir}")
    expected = [c["name"] for c in manifest["partitions"][partition]["cells"]]
    first, cells, prov = None, {}, []
    for f in files:
        r = json.loads(f.read_text())
        if len(r.get("cells", {})) != 1:
            raise SystemExit(f"{f}: expected exactly one cell, found {list(r.get('cells', {}))}")
        if first is None:
            first = r
        for k in IDENTITY_KEYS:
            if r.get(k) != first.get(k):
                raise SystemExit(f"{f}: {k} differs from {files[0]}")
        (name, cell), = r["cells"].items()
        if name in cells:
            raise SystemExit(f"cell {name} appears twice (second: {f})")
        cells[name] = cell
        prov.append({"cell": name, "path": str(f), **{k: r.get(k) for k in PROVENANCE_KEYS}})
    missing = [c for c in expected if c not in cells]
    if missing:
        raise SystemExit(f"missing final cells: {', '.join(missing)}")
    extra = [c for c in cells if c not in expected]
    if extra:
        raise SystemExit(f"cells not in manifest {partition} partition: {', '.join(extra)}")
    merged = {k: first[k] for k in IDENTITY_KEYS}
    merged["merged_from"] = prov
    merged["best_classical"] = choice["choice"]
    merged["cells"] = {c: cells[c] for c in expected}
    return merged


def fmt(x, p=3):
    return f"{x:.{p}f}" if isinstance(x, (int, float)) and x == x else str(x)


def results_md(m, study=None):
    L = [f"# Comparison study results: {m['partition']} v{m['version']}", "",
         f"Merged from {len(m['merged_from'])} per-cell runs. Best classical: {m['best_classical']}.", ""]
    for name, cell in m["cells"].items():
        dm = cell.get("data_md5", {})
        n = next(iter(cell["stats"].values())).get("n_sequences", "?")
        L += [f"## Cell {name} (n={n}, md5 {dm.get('computed', '?')}, manifest match {dm.get('match', '?')})", "",
              "| Est | RMSE mT | AE p90-of-p90 deg | lock | lost | nonfinite fr | seq w/ nonfinite | lat med us | lat p90 us |",
              "|---|---|---|---|---|---|---|---|---|"]
        for e, s in cell["stats"].items():
            L.append(f"| {e} | {fmt(s.get('rmse_mean_mT'))} | {fmt(s.get('ae_p90_of_seq_p90_deg'), 2)} | "
                     f"{fmt(s.get('lock_frac_mean'))} | {fmt(s.get('lost_rate'))} | {s.get('nonfinite_frames', '?')} | "
                     f"{s.get('sequences_with_nonfinite', '?')} | {fmt(s.get('latency_us_median'), 0)} | "
                     f"{fmt(s.get('latency_us_p90'), 0)} |")
        L += ["", "| Pair (A-B) | dRMSE mT [95% CI] | dAE p90 deg [95% CI] |", "|---|---|---|"]
        for k, p in cell.get("pairs", {}).items():
            r, a = p["rmse_diff_ci95_mT"], p["ae_p90_diff_ci95_deg"]
            L.append(f"| {k} | {fmt(p.get('rmse_diff_mT'))} [{fmt(r[0])}, {fmt(r[1])}] | "
                     f"{fmt(p.get('ae_p90_diff_deg'), 2)} [{fmt(a[0], 2)}, {fmt(a[1], 2)}] |")
        L.append("")
    L += ["## Per-cell provenance", "", "| Cell | Path | Commit | Date |", "|---|---|---|---|"]
    for p in m["merged_from"]:
        L.append(f"| {p['cell']} | {p['path']} | {(p.get('git') or {}).get('commit')} | {p.get('date')} |")
    return "\n".join(L) + "\n"


def decision_md(m, d):
    L = ["# Comparison study decision", "", f"Outcome: {d['outcome']}", "",
         f"Best classical: {d['best_classical']}. Lowest clean-cell lost rate among E2/E3/E4: "
         f"{fmt(d['clean_lowest_lost_rate_E2_E3_E4'])}.", "", "## Qualifying cells", ""]
    if not d["qualifying"]:
        L.append("None.")
    for side, c in d["qualifying"]:
        key = "classical_beats_E4" if side == "classical" else "E4_beats_classical"
        t = d["detail"][c][key]
        L.append(f"- {side} on {c}: angular improvement {fmt(t['angular_improvement_deg'], 2)} deg, "
                 f"RMSE improvement {fmt(t['rmse_improvement_frac'])}, "
                 f"RMSE diff CI95 {[fmt(v) for v in t['rmse_diff_ci95_mT']]} mT, "
                 f"AE p90 diff CI95 {[fmt(v, 2) for v in t['ae_p90_diff_ci95_deg']]} deg")
    L += ["", "## All cells (win tests)", "", "| Cell | Test | win | ang impr deg | RMSE impr | RMSE CI95 | AE p90 CI95 |",
          "|---|---|---|---|---|---|---|"]
    for c, tests in d["detail"].items():
        for k, t in tests.items():
            L.append(f"| {c} | {k} | {t['win']} | {fmt(t['angular_improvement_deg'], 2)} | "
                     f"{fmt(t['rmse_improvement_frac'])} | {[fmt(v) for v in t['rmse_diff_ci95_mT']]} | "
                     f"{[fmt(v, 2) for v in t['ae_p90_diff_ci95_deg']]} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--decision-md", type=Path, required=True)
    ap.add_argument("--choice", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=ROOT / "docs/comparison_test_v1.manifest.json")
    args = ap.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    choice = json.loads(args.choice.read_text())
    merged = merge(args.runs, manifest, choice)
    study = _load_study()
    needed = {"E2", "E3", "E4"}
    for name, cell in merged["cells"].items():
        if not needed <= set(cell["stats"]):
            raise SystemExit(f"cell {name} lacks one of {sorted(needed)}")
    merged["decision"] = study.decide(merged)
    args.out_json.write_text(json.dumps(merged, indent=1, default=str) + "\n")
    args.out_md.write_text(results_md(merged))
    args.decision_md.write_text(decision_md(merged, merged["decision"]))
    print(f"Outcome: {merged['decision']['outcome']}")
    return merged


if __name__ == "__main__":
    main()
