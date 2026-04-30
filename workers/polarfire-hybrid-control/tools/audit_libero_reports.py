#!/usr/bin/env python3
"""Audit archived Libero/Synplify reports for PID survival evidence.

The script is intentionally conservative. It treats report files as evidence
about a build, not as semantic proof of correctness. The goal is to make the
pre-corpus work easy to compare against corpus-backed expectations:

* timing slack should remain positive;
* nv_pid_top should have a nontrivial hierarchy footprint when claimed real;
* PID-related pruning or constant-folding messages should be called out.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIRS = (
    REPO_ROOT / "libero/reports/2026-04-29-recovered",
    REPO_ROOT / "libero/reports/2026-04-29-pid-integrated",
    REPO_ROOT / "libero/reports/2026-04-29-pid-real",
)

REPORT_TOP = "MPFS_ICICLE_KIT_BASE_DESIGN"
PRUNE_IDS = ("CL168", "CL189", "CL260", "CL279", "BN115", "BN362", "MO129", "MO156")
PID_TERMS = (
    "nv_pid",
    "pid_io_block",
    "watchdog_timer",
    "legup_mult",
    "actuator",
    "inner_clamp",
    "axi4target",
    "kp",
    "ki",
    "kd",
)


@dataclass
class AuditResult:
    path: Path
    timing_worst_slack_ns: float | None = None
    resource_totals: dict[str, int] = field(default_factory=dict)
    pid_fabric_4lut: int = 0
    pid_fabric_dff: int = 0
    pid_math: int = 0
    pid_rows: int = 0
    scoped_prune_hits: list[str] = field(default_factory=list)
    global_prune_counts: dict[str, int] = field(default_factory=dict)

    @property
    def has_real_pid_footprint(self) -> bool:
        return self.pid_fabric_4lut >= 1000 and self.pid_fabric_dff >= 500 and self.pid_math >= 5

    @property
    def timing_passes(self) -> bool | None:
        if self.timing_worst_slack_ns is None:
            return None
        return self.timing_worst_slack_ns > 0.0

    @property
    def classification(self) -> str:
        if not self.path.exists():
            return "missing"
        if self.has_real_pid_footprint and self.timing_passes is True:
            return "real PID evidence"
        if self.pid_rows == 0 or self.pid_fabric_4lut < 1000:
            return "baseline/paper-shell evidence"
        if self.scoped_prune_hits:
            return "needs pruning review"
        return "partial evidence"


def parse_int(value: str) -> int | None:
    value = value.strip().replace(",", "")
    if not value or not re.fullmatch(r"-?\d+", value):
        return None
    return int(value)


def parse_resource_totals(report: Path) -> dict[str, int]:
    totals: dict[str, int] = {}
    if not report.is_file():
        return totals

    type_row = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([0-9,]+)\s*\|")
    for line in report.read_text(errors="replace").splitlines():
        match = type_row.match(line)
        if not match:
            continue
        label = match.group(1).strip()
        used = parse_int(match.group(2))
        if used is not None:
            totals[label] = used
    return totals


def parse_timing_worst_slack(report_dir: Path) -> float | None:
    values: list[float] = []
    patterns = (
        f"{REPORT_TOP}_timing_r*_s*.rpt",
        f"{REPORT_TOP}_timing_violations_max_r*_s*.rpt",
        f"{REPORT_TOP}_timing_violations_min_r*_s*.rpt",
    )
    slack_re = re.compile(r"(?:Worst Slack|Slack) \(ns\):\s*(-?\d+(?:\.\d+)?)")

    for pattern in patterns:
        for report in sorted(report_dir.glob(pattern)):
            text = report.read_text(errors="replace")
            for match in slack_re.finditer(text):
                values.append(float(match.group(1)))
    return min(values) if values else None


def parse_pid_hierarchy(report_dir: Path) -> tuple[int, int, int, int]:
    csv_path = report_dir / f"{REPORT_TOP}_compile_netlist_hier_resources.csv"
    if not csv_path.is_file():
        return 0, 0, 0, 0

    rows = 0
    fabric_4lut = 0
    fabric_dff = 0
    math = 0
    raw_lines = csv_path.read_text(errors="replace").splitlines()
    try:
        header_index = next(i for i, line in enumerate(raw_lines) if line.startswith("Module Name,"))
    except StopIteration:
        return 0, 0, 0, 0

    with csv_path.open(newline="", errors="replace") as handle:
        for _ in range(header_index):
            next(handle, None)
        reader = csv.DictReader(handle)
        for row in reader:
            module = row.get("Module Name", "")
            if "nv_pid_top" not in module:
                continue
            rows += 1
            fabric_4lut += parse_int(row.get("Fabric 4LUT", "0")) or 0
            fabric_dff += parse_int(row.get("Fabric DFF", "0")) or 0
            math += parse_int(row.get("Math (18x18)", "0")) or 0
    return rows, fabric_4lut, fabric_dff, math


def parse_pruning(report_dir: Path) -> tuple[list[str], dict[str, int]]:
    scoped_hits: list[str] = []
    counts = {message_id: 0 for message_id in PRUNE_IDS}
    reports = list(report_dir.glob("*.srr")) + list(report_dir.glob("*.log"))
    id_re = re.compile(r"\b(" + "|".join(PRUNE_IDS) + r")\b")

    for report in reports:
        for line in report.read_text(errors="replace").splitlines():
            ids = id_re.findall(line)
            if not ids:
                continue
            lowered = line.lower()
            for message_id in ids:
                counts[message_id] += 1
            if any(term in lowered for term in PID_TERMS):
                scoped_hits.append(f"{report.name}: {line.strip()[:220]}")

    return scoped_hits[:20], counts


def audit_dir(report_dir: Path) -> AuditResult:
    result = AuditResult(path=report_dir)
    result.timing_worst_slack_ns = parse_timing_worst_slack(report_dir)
    result.resource_totals = parse_resource_totals(report_dir / f"{REPORT_TOP}_compile_netlist_resources.rpt")
    result.pid_rows, result.pid_fabric_4lut, result.pid_fabric_dff, result.pid_math = parse_pid_hierarchy(report_dir)
    result.scoped_prune_hits, result.global_prune_counts = parse_pruning(report_dir)
    return result


def format_result(result: AuditResult) -> str:
    rel = result.path.relative_to(REPO_ROOT) if result.path.is_relative_to(REPO_ROOT) else result.path
    slack = "n/a" if result.timing_worst_slack_ns is None else f"{result.timing_worst_slack_ns:.3f} ns"
    timing = "n/a" if result.timing_passes is None else ("pass" if result.timing_passes else "fail")
    totals = result.resource_totals

    lines = [
        f"## {rel}",
        "",
        f"- Classification: **{result.classification}**",
        f"- Worst parsed slack: `{slack}` ({timing})",
        f"- Aggregate resources: 4LUT `{totals.get('4LUT', 'n/a')}`, DFF `{totals.get('DFF', 'n/a')}`, Math `{totals.get('Math', 'n/a')}`",
        f"- nv_pid_top hierarchy rows: `{result.pid_rows}`",
        f"- nv_pid_top summed footprint: 4LUT `{result.pid_fabric_4lut}`, DFF `{result.pid_fabric_dff}`, Math `{result.pid_math}`",
        f"- PID-scoped pruning hits: `{len(result.scoped_prune_hits)}`",
        "- Global pruning-message counts: "
        + ", ".join(f"{message_id}={count}" for message_id, count in result.global_prune_counts.items() if count),
    ]
    if not any(result.global_prune_counts.values()):
        lines[-1] = "- Global pruning-message counts: none found"
    if result.scoped_prune_hits:
        lines.append("")
        lines.append("PID-scoped pruning excerpts:")
        for hit in result.scoped_prune_hits:
            lines.append(f"- `{hit}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dirs", nargs="*", type=Path, help="Report directories to audit")
    args = parser.parse_args()

    report_dirs = args.report_dirs or list(DEFAULT_REPORT_DIRS)
    results = [audit_dir(path.resolve()) for path in report_dirs]

    print("# Libero/Synplify Report Audit")
    print("")
    print("Corpus-grounded checks: positive timing slack, nontrivial nv_pid_top hierarchy footprint, and PID-scoped pruning/constant-folding callouts for review.")
    print("")
    for result in results:
        print(format_result(result))

    failures = []
    for result in results:
        if not result.path.exists() or not result.path.name.endswith("pid-real"):
            continue
        if result.classification != "real PID evidence":
            failures.append(result)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
