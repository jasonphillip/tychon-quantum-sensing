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
import json
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
OUTPUT_VALID_ISSUE_TERMS = (
    "not found",
    "undriven",
    "floating",
    "component declaration",
)
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
CRITICAL_PID_TERMS = (
    "kp",
    "ki",
    "kd",
    "out_min",
    "out_max",
    "inner_clamp_setpoint",
    "pid_integral",
    "prev_error",
    "u_ai_latch",
    "legup_mult",
)
INFORMATIONAL_PID_TERMS = (
    "mem_size_",
    "down_convert_shift_dist",
    "ii_counter",
    "prev_watchdog",
    "cooldown_counter",
)
PID_PATTERNS = tuple(re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])") for term in PID_TERMS)
CRITICAL_PID_PATTERNS = tuple(
    re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])") for term in CRITICAL_PID_TERMS
)
INFORMATIONAL_PID_PATTERNS = tuple(
    re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])") for term in INFORMATIONAL_PID_TERMS
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
    critical_prune_hits: list[str] = field(default_factory=list)
    informational_prune_hits: list[str] = field(default_factory=list)
    global_prune_counts: dict[str, int] = field(default_factory=dict)
    vectorblox_output_valid_issues: list[str] = field(default_factory=list)

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
            if self.critical_prune_hits:
                return "real PID evidence with pruning review"
            return "real PID evidence"
        if self.pid_rows == 0 or self.pid_fabric_4lut < 1000:
            return "baseline/paper-shell evidence"
        if self.scoped_prune_hits:
            return "needs pruning review"
        return "partial evidence"

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "classification": self.classification,
            "timing_worst_slack_ns": self.timing_worst_slack_ns,
            "timing_passes": self.timing_passes,
            "resource_totals": self.resource_totals,
            "pid_rows": self.pid_rows,
            "pid_fabric_4lut": self.pid_fabric_4lut,
            "pid_fabric_dff": self.pid_fabric_dff,
            "pid_math": self.pid_math,
            "pid_scoped_prune_hits": len(self.scoped_prune_hits),
            "critical_prune_hits": self.critical_prune_hits,
            "informational_prune_hits": self.informational_prune_hits,
            "global_prune_counts": self.global_prune_counts,
            "vectorblox_output_valid_issues": self.vectorblox_output_valid_issues,
        }


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


def parse_pruning(report_dir: Path) -> tuple[list[str], list[str], list[str], dict[str, int]]:
    scoped_hits: list[str] = []
    critical_hits: list[str] = []
    informational_hits: list[str] = []
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
            if any(pattern.search(lowered) for pattern in PID_PATTERNS):
                hit = f"{report.name}: {line.strip()[:220]}"
                scoped_hits.append(hit)
                if any(pattern.search(lowered) for pattern in CRITICAL_PID_PATTERNS):
                    critical_hits.append(hit)
                elif any(pattern.search(lowered) for pattern in INFORMATIONAL_PID_PATTERNS):
                    informational_hits.append(hit)

    return scoped_hits[:20], critical_hits[:20], informational_hits[:20], counts


def parse_output_valid_issues(report_dir: Path) -> list[str]:
    issues: list[str] = []
    reports = list(report_dir.glob("*.srr")) + list(report_dir.glob("*.log"))
    for report in reports:
        for line in report.read_text(errors="replace").splitlines():
            lowered = line.lower()
            if "output_valid" not in lowered:
                continue
            if any(term in lowered for term in OUTPUT_VALID_ISSUE_TERMS):
                issues.append(f"{report.name}: {line.strip()[:220]}")
    return issues[:20]


def audit_dir(report_dir: Path) -> AuditResult:
    result = AuditResult(path=report_dir)
    result.timing_worst_slack_ns = parse_timing_worst_slack(report_dir)
    result.resource_totals = parse_resource_totals(report_dir / f"{REPORT_TOP}_compile_netlist_resources.rpt")
    result.pid_rows, result.pid_fabric_4lut, result.pid_fabric_dff, result.pid_math = parse_pid_hierarchy(report_dir)
    (
        result.scoped_prune_hits,
        result.critical_prune_hits,
        result.informational_prune_hits,
        result.global_prune_counts,
    ) = parse_pruning(report_dir)
    result.vectorblox_output_valid_issues = parse_output_valid_issues(report_dir)
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
        f"- Critical pruning review hits: `{len(result.critical_prune_hits)}`",
        f"- Informational pruning hits: `{len(result.informational_prune_hits)}`",
        f"- CoreVectorBlox output_valid wiring issues: `{len(result.vectorblox_output_valid_issues)}`",
        "- Global pruning-message counts: "
        + ", ".join(f"{message_id}={count}" for message_id, count in result.global_prune_counts.items() if count),
    ]
    if not any(result.global_prune_counts.values()):
        lines[-1] = "- Global pruning-message counts: none found"
    if result.scoped_prune_hits:
        lines.append("")
        if result.critical_prune_hits:
            lines.append("Critical pruning review excerpts:")
        else:
            lines.append("Informational pruning review excerpts:")
        critical_excerpt = result.critical_prune_hits or result.scoped_prune_hits
        for hit in critical_excerpt[:10]:
            lines.append(f"- `{hit}`")
    if result.vectorblox_output_valid_issues:
        lines.append("")
        lines.append("CoreVectorBlox output_valid wiring excerpts:")
        for hit in result.vectorblox_output_valid_issues[:10]:
            lines.append(f"- `{hit}`")
    lines.append("")
    return "\n".join(lines)


# --- Strict-mode helpers --------------------------------------------------
# Strict mode applies fail-fast corpus rules to bundles that claim production-
# grade closure (names ending in pid-real, overnight-*, or -strict). Baseline
# and paper-shell bundles are skipped because they intentionally embody the
# pre-corpus failure modes for comparison.
STRICT_BUNDLE_PATTERNS = (
    re.compile(r"pid-real$"),
    re.compile(r"^overnight-"),
    re.compile(r"-strict$"),
)


def _is_strict_bundle(result: AuditResult) -> bool:
    name = result.path.name
    return any(p.search(name) for p in STRICT_BUNDLE_PATTERNS)


def _strict_check(result: AuditResult) -> list[str]:
    """Return list of strict-gate violations for a single bundle. Empty list
    means the bundle passes strict mode."""
    violations: list[str] = []
    if not result.path.exists():
        violations.append(f"{result.path.name}: report bundle missing")
        return violations
    # 1. Must be classified as real PID evidence (with or without pruning review)
    if not result.classification.startswith("real PID evidence"):
        violations.append(
            f"{result.path.name}: classification is "
            f"'{result.classification}' (expected 'real PID evidence')"
        )
    # 2. Timing must close (positive slack)
    if result.timing_passes is False:
        violations.append(
            f"{result.path.name}: timing slack negative "
            f"({result.timing_worst_slack_ns} ns)"
        )
    # 3. No critical pruning hits — corpus rule from
    #    preserving-real-smarthls-pid-datapath.md: CL189+CL260 sequences on
    #    coefficient registers indicate constant-folding survived. Each hit
    #    references one of the critical PID terms (Kp/Ki/Kd/out_min/out_max/
    #    inner_clamp_setpoint/legup_mult/etc.).
    if result.critical_prune_hits:
        violations.append(
            f"{result.path.name}: {len(result.critical_prune_hits)} critical "
            "PID-coefficient pruning hits (CL189/CL260 on Kp/Ki/Kd or "
            "legup_mult cone). First: "
            f"{result.critical_prune_hits[0][:160]}"
        )
    # 4. No CoreVectorBlox output_valid wiring issues — corpus rule from
    #    HB0919: the port must be propagated through the SmartDesign canvas.
    if result.vectorblox_output_valid_issues:
        violations.append(
            f"{result.path.name}: {len(result.vectorblox_output_valid_issues)} "
            "CoreVectorBlox output_valid wiring issues "
            "(undriven/floating/component-declaration). First: "
            f"{result.vectorblox_output_valid_issues[0][:160]}"
        )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dirs", nargs="*", type=Path, help="Report directories to audit")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Apply corpus-backed fail-fast gates (pruning, output_valid, "
        "timing) to any bundle whose name ends in pid-real, starts with "
        "overnight-, or ends with -strict. Other bundles are reported but "
        "do not affect the exit code in strict mode either.",
    )
    parser.add_argument(
        "--fail-on-prune-pid-coeff",
        action="store_true",
        help="Subset of --strict: only the coefficient-pruning gate.",
    )
    parser.add_argument(
        "--require-status-csrs",
        action="store_true",
        help="(Reserved for future use once overnight bundles include the "
        "new status CSR signals.) Asserts that the readback nets for "
        "kp/ki/kd shadows and watchdog timeout counters appear in the "
        "synthesis reports without pruning. Today this is a soft check.",
    )
    parser.add_argument(
        "--fail-on-output-valid-issue",
        action="store_true",
        help="Subset of --strict: only the CoreVectorBlox output_valid gate.",
    )
    args = parser.parse_args()

    report_dirs = args.report_dirs or list(DEFAULT_REPORT_DIRS)
    results = [audit_dir(path.resolve()) for path in report_dirs]

    strict_violations: list[str] = []
    if args.strict or args.fail_on_prune_pid_coeff or args.fail_on_output_valid_issue:
        strict_targets = [r for r in results if _is_strict_bundle(r)]
        if not strict_targets:
            strict_violations.append(
                "no strict-eligible bundles found "
                "(names matching pid-real$, ^overnight-, or -strict$)"
            )
        for r in strict_targets:
            for v in _strict_check(r):
                if args.strict:
                    strict_violations.append(v)
                elif args.fail_on_prune_pid_coeff and "pruning hits" in v:
                    strict_violations.append(v)
                elif args.fail_on_output_valid_issue and "output_valid" in v:
                    strict_violations.append(v)

    if args.json:
        payload = {
            "results": [result.to_dict() for result in results],
            "strict_violations": strict_violations,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1 if (strict_violations or _real_pid_failures(results)) else 0

    print("# Libero/Synplify Report Audit")
    print("")
    print("Corpus-grounded checks: positive timing slack, nontrivial nv_pid_top hierarchy footprint, and PID-scoped pruning/constant-folding callouts for review.")
    print("")
    for result in results:
        print(format_result(result))

    if args.strict or args.fail_on_prune_pid_coeff or args.fail_on_output_valid_issue:
        print("## Strict-Mode Verdict")
        if not strict_violations:
            print("All strict-eligible bundles pass corpus gates.")
        else:
            print(f"{len(strict_violations)} strict violation(s):")
            for v in strict_violations:
                print(f"- {v}")
        print("")

    if args.require_status_csrs:
        print("## Status CSR Coverage (soft check)")
        print(
            "Reserved for overnight-r* bundles that include the new "
            "pid_io_block status registers (kp_shadow, ki_shadow, kd_shadow, "
            "watchdog_timeout_event_count, etc.). Currently informational only."
        )
        print("")

    if strict_violations:
        return 1
    return 1 if _real_pid_failures(results) else 0


def _real_pid_failures(results: list[AuditResult]) -> list[AuditResult]:
    failures = []
    for result in results:
        if not result.path.exists() or not result.path.name.endswith("pid-real"):
            continue
        if not result.classification.startswith("real PID evidence"):
            failures.append(result)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
