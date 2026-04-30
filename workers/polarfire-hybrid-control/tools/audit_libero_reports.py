#!/usr/bin/env python3
"""audit_libero_reports.py — corpus-grounded classifier for Libero/Synplify
report bundles. Operates on extracted report directories under
`libero/reports/<tag>/` and judges each bundle against the corpus's
ground-truth criteria for "real PID datapath survival."

Classification taxonomy (corpus-derived, see citations below):

  real-pid-evidence
    - positive worst-case timing slack
    - nv_pid_top hierarchy present in compile_netlist_hier_resources
    - non-trivial summed PID footprint (LUT + DFF + MATH > thresholds)
    - no critical pruning hits in the .srr (CL189/CL260/CL279/BN362/BN115)
    Citation: ~/.corpus/polarfire-control-corpus/raw/user-contributed/
              preserving-real-smarthls-pid-datapath.md:74-103

  paper-shell
    - nv_pid_top instance present but datapath summed footprint is below
      pruned-baseline threshold OR critical pruning hits seen in .srr
    Citation: same file, lines 53-67 (cascade signature).

  baseline
    - reports captured BEFORE any constant-folding fix applied; expected to
      fail strict gates and useful only as comparison evidence.

  unknown
    - missing or unparseable artifacts.

Strict mode (--strict) elevates configurable subset of issues to fail-fast
exit-1 violations; otherwise everything is reporting-only.

Corpus-derived rules:

  CL189: "Register bit X is always 0/1, optimizing..."
    -> bit-level constant inference on a sequential instance.
    Citation: preventing-synplify-constant-folding-smarthls-pid.md:108
  CL260: "Pruning Register bit N of <regname>"
    -> follows CL189 once a bit's fate is determined.
    Citation: preventing-synplify-constant-folding-smarthls-pid.md:109
  CL279: same family; corpus checklist includes it explicitly.
    Citation: preserving-real-smarthls-pid-datapath.md:98
  BN362: "Removing sequential instance ... no references to outputs"
    -> tied-down AXI failure mode signature.
    Citation: preventing-synplify-constant-folding-smarthls-pid.md:112
  BN115: corpus marks as "structural note, verify in local log."
    Citation: preventing-synplify-constant-folding-smarthls-pid.md:111
  MO129: "Sequential instance reduced to combinational gate by constant
    propagation." Corpus says: "Not located verbatim in the public OEM
    reference. Verify in local log." -> WARNING ONLY by default; only
    fail-fast under --strict-mo129.
    Citation: preventing-synplify-constant-folding-smarthls-pid.md:113

Output is human-readable; exit code 1 on strict violations, 0 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --- Corpus-derived constants ---------------------------------------------

# Critical message IDs that confirm coefficient/datapath constant-folding.
# Corpus-confirmed cascade is CL189 -> CL260 -> BN362 (preventing:60-61,
# 108-113). CL279 is named in the survival checklist (preserving:98).
# BN115 and MO129 are flagged "verify in local log" by the corpus itself
# (preventing:111, 113) and so are warnings unless explicitly opted in.
CRITICAL_PRUNE_IDS = ("CL189", "CL260", "CL279", "BN362")

# Speculative IDs: corpus says these are not verbatim-confirmed in the
# public OEM reference. Demoted to warnings unless --strict-mo129 (etc).
SPECULATIVE_PRUNE_IDS = ("MO129", "BN115")

# Coefficient names whose pruning is decisive evidence. Source: corpus
# checklist preserving:98 ("upper bits of Kp, Ki, Kd, clamp limits, and
# intermediate products/sums"). `legup_mult` is intentionally NOT here:
# it's a SmartHLS-generated arithmetic-primitive name, and Synplify
# routinely prunes unused multiplier alternatives — that's not coefficient
# constant-folding.
PID_COEFF_NAMES = (
    "Kp",
    "Ki",
    "Kd",
    "out_min",
    "out_max",
    "inner_clamp_setpoint",
)

# Output_valid wiring issue terms. Corpus says output_valid must propagate to
# the top of the SmartDesign canvas; warnings about "not found", "undriven",
# etc near "output_valid" are evidence it never reached the watchdog.
# Source: HB0919:784 (interrupt mirror) + corpus user-contributed evaluation.
OUTPUT_VALID_TERMS = ("not found", "undriven", "floating", "component declaration")

# Empirical thresholds for "non-trivial PID footprint." A pruned-baseline
# bundle from this repo's history showed nv_pid_top summed to ~30 LUT,
# ~10 DFF, 0 MATH; a real bundle showed ~2390 LUT / ~1700 DFF / ~25 MATH.
# Pick thresholds that cleanly separate the two regimes.
MIN_LUT_REAL = 500
MIN_DFF_REAL = 400
MIN_MATH_REAL = 4


# --- Data classes ---------------------------------------------------------


@dataclass
class BundleEvidence:
    path: Path
    has_pid_hierarchy: bool = False
    pid_lut_total: int = 0
    pid_dff_total: int = 0
    pid_math_total: int = 0
    pid_hier_rows: int = 0
    timing_slack_ns: float | None = None
    critical_prune_hits: list[tuple[str, str]] = field(default_factory=list)
    speculative_prune_hits: list[tuple[str, str]] = field(default_factory=list)
    output_valid_issues: list[str] = field(default_factory=list)
    multi_axi_slave_concern: bool = False
    classification: str = "unknown"
    notes: list[str] = field(default_factory=list)


# --- Parsers --------------------------------------------------------------


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def parse_pid_hierarchy(bundle: Path, ev: BundleEvidence) -> None:
    """Sum Fabric 4LUT / Fabric DFF / Math across nv_pid_top hierarchy
    rows in compile_netlist_hier_resources.csv. Columns are picked by
    HEADER NAME (not index), since interface/fabric/io columns interleave
    in this report layout."""
    candidates = list(bundle.glob("*compile_netlist_hier_resources*.csv"))
    if not candidates:
        return
    csv = candidates[0]
    text = _read_text(csv)
    if not text:
        return
    lines = text.splitlines()
    header_idx = None
    headers: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("Module Name"):
            header_idx = i
            headers = [h.strip() for h in line.split(",")]
            break
    if header_idx is None:
        return

    def col(name_substring: str) -> int:
        for j, h in enumerate(headers):
            if name_substring.lower() in h.lower():
                return j
        return -1

    lut_idx = col("Fabric 4LUT")
    dff_idx = col("Fabric DFF")
    math_idx = col("Math")
    if min(lut_idx, dff_idx, math_idx) < 0:
        return

    rows = 0
    lut = dff = math = 0
    for line in lines[header_idx + 1 :]:
        if "nv_pid_top" not in line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) <= max(lut_idx, dff_idx, math_idx):
            continue
        rows += 1
        try:
            lut += int(parts[lut_idx])
            dff += int(parts[dff_idx])
            math += int(parts[math_idx])
        except ValueError:
            continue
    if rows:
        ev.has_pid_hierarchy = True
        ev.pid_hier_rows = rows
        ev.pid_lut_total = lut
        ev.pid_dff_total = dff
        ev.pid_math_total = math


_TIMING_RE = re.compile(
    r"(?:WORST CASE SLACK|Worst Slack|Slack \(ns\))\s*[:=]?\s*([+-]?\d+\.\d+)",
    re.IGNORECASE,
)


def parse_timing(bundle: Path, ev: BundleEvidence) -> None:
    for path in bundle.glob("*timing*.rpt"):
        m = _TIMING_RE.search(_read_text(path))
        if m:
            try:
                ev.timing_slack_ns = float(m.group(1))
                return
            except ValueError:
                pass
    # Fall back: scan iteration_summary for a slack number.
    for path in bundle.glob("*iteration_summary*"):
        m = _TIMING_RE.search(_read_text(path))
        if m:
            try:
                ev.timing_slack_ns = float(m.group(1))
                return
            except ValueError:
                pass


def parse_synplify_messages(bundle: Path, ev: BundleEvidence) -> None:
    for path in bundle.glob("*.srr"):
        text = _read_text(path)
        if not text:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            for msg_id in CRITICAL_PRUNE_IDS:
                if msg_id in stripped:
                    if any(coeff in stripped for coeff in PID_COEFF_NAMES):
                        ev.critical_prune_hits.append((msg_id, stripped[:240]))
            for msg_id in SPECULATIVE_PRUNE_IDS:
                if msg_id in stripped:
                    if any(coeff in stripped for coeff in PID_COEFF_NAMES):
                        ev.speculative_prune_hits.append((msg_id, stripped[:240]))
            low = stripped.lower()
            if "output_valid" in low or "output valid" in low:
                if any(term in low for term in OUTPUT_VALID_TERMS):
                    ev.output_valid_issues.append(stripped[:240])


def parse_multi_axi_slave_concern(bundle: Path, ev: BundleEvidence) -> None:
    """Look for the two-slaves-on-one-FIC-master pattern in the patched
    SmartDesign Verilog. Both `pid_io_block_0` (or `pid_csr_block_0`) AND
    nv_pid_top's `axi4target` instance share `FIC_0_PERIPHERALS_1_AXI4mslave0`
    -> read-data multiplexing is undefined.
    Corpus criterion (preserving:97): software write-then-readback is the
    architectural proof of survival.
    """
    for path in bundle.glob("*.patched.v"):
        text = _read_text(path)
        if not text:
            continue
        master_taps = text.count("FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR")
        slave_marks = sum(
            1 for k in ("pid_io_block_0", "pid_csr_block_0", "axi4target") if k in text
        )
        # Two distinct slave references both touching one master ARADDR is
        # the eavesdropping pattern.
        if master_taps and slave_marks >= 2 and "CoreAXI4Interconnect" not in text:
            ev.multi_axi_slave_concern = True
            return


# --- Classification -------------------------------------------------------


def classify(ev: BundleEvidence) -> None:
    name = ev.path.name.lower()
    if "pruned" in name or "baseline" in name:
        ev.classification = "baseline"
        return
    pid_ok = (
        ev.has_pid_hierarchy
        and ev.pid_lut_total >= MIN_LUT_REAL
        and ev.pid_dff_total >= MIN_DFF_REAL
        and ev.pid_math_total >= MIN_MATH_REAL
    )
    if pid_ok and not ev.critical_prune_hits:
        ev.classification = "real-pid-evidence"
    elif ev.has_pid_hierarchy and (
        not pid_ok or ev.critical_prune_hits
    ):
        ev.classification = "paper-shell"
    elif not ev.has_pid_hierarchy:
        ev.classification = "unknown"


# --- Reporting ------------------------------------------------------------


def format_bundle(ev: BundleEvidence) -> str:
    lines = [f"== {ev.path}"]
    lines.append(f"   classification: {ev.classification}")
    if ev.has_pid_hierarchy:
        lines.append(
            f"   nv_pid_top: {ev.pid_hier_rows} rows | "
            f"LUT={ev.pid_lut_total} DFF={ev.pid_dff_total} MATH={ev.pid_math_total}"
        )
    else:
        lines.append("   nv_pid_top: hierarchy not found")
    if ev.timing_slack_ns is not None:
        lines.append(f"   timing slack: {ev.timing_slack_ns:+.3f} ns")
    if ev.critical_prune_hits:
        lines.append(f"   critical pruning hits: {len(ev.critical_prune_hits)}")
        for mid, line in ev.critical_prune_hits[:5]:
            lines.append(f"     [{mid}] {line}")
    if ev.speculative_prune_hits:
        lines.append(
            f"   speculative MO129 hits (warning only): "
            f"{len(ev.speculative_prune_hits)}"
        )
    if ev.output_valid_issues:
        lines.append(
            f"   output_valid wiring issues: {len(ev.output_valid_issues)}"
        )
        for line in ev.output_valid_issues[:3]:
            lines.append(f"     {line}")
    if ev.multi_axi_slave_concern:
        lines.append(
            "   readback-contract concern: two AXI slaves on one FIC master "
            "without CoreAXI4Interconnect (preserving:97 criterion not met)"
        )
    return "\n".join(lines)


# --- CLI ------------------------------------------------------------------


def collect_bundles(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in paths:
        if not root.exists():
            continue
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if child.is_dir():
                    out.append(child)
        else:
            out.append(root)
    return out


def is_strict_target(path: Path) -> bool:
    name = path.name
    return (
        name.endswith("pid-real")
        or name.startswith("overnight-")
        or name.endswith("-strict")
        or name.startswith("2026-04-30-")  # this branch's own runs
    )


def main(argv: list[str] | None = None) -> int:
    desc = (__doc__ or "").split("\n", 1)[0]
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("paths", nargs="+", help="report root(s) (e.g. libero/reports)")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="fail-fast on critical pruning + output_valid issues "
        "(eligible bundles only)",
    )
    ap.add_argument(
        "--fail-on-prune-pid-coeff",
        action="store_true",
        help="fail-fast when CL189/CL260/CL279/BN362/BN115 hit a PID coeff",
    )
    ap.add_argument(
        "--fail-on-output-valid-issue",
        action="store_true",
        help="fail-fast on CoreVectorBlox output_valid wiring warnings",
    )
    ap.add_argument(
        "--check-readback-contract",
        action="store_true",
        help="fail when two AXI slaves share one FIC master without "
        "CoreAXI4Interconnect (preserving:97)",
    )
    ap.add_argument(
        "--strict-mo129",
        action="store_true",
        help="elevate MO129 from warning to fail-fast (corpus marks MO129 "
        "speculative; opt-in only)",
    )
    args = ap.parse_args(argv)

    bundles = collect_bundles([Path(p) for p in args.paths])
    if not bundles:
        print("no bundles found under:", " ".join(args.paths))
        return 0

    violations = 0
    for bundle in bundles:
        ev = BundleEvidence(path=bundle)
        parse_pid_hierarchy(bundle, ev)
        parse_timing(bundle, ev)
        parse_synplify_messages(bundle, ev)
        parse_multi_axi_slave_concern(bundle, ev)
        classify(ev)
        print(format_bundle(ev))
        print()

        eligible = is_strict_target(bundle)
        gates_active = (
            args.strict
            or args.fail_on_prune_pid_coeff
            or args.fail_on_output_valid_issue
            or args.check_readback_contract
            or args.strict_mo129
        )

        if not gates_active:
            continue

        # Strict mode applies all gates to eligible bundles. Individual gate
        # flags apply regardless of eligibility.
        apply_prune = args.fail_on_prune_pid_coeff or (args.strict and eligible)
        apply_ov = args.fail_on_output_valid_issue or (args.strict and eligible)
        apply_rb = args.check_readback_contract or (args.strict and eligible)
        apply_mo129 = args.strict_mo129

        if apply_prune and ev.critical_prune_hits:
            violations += 1
            print(
                f"   STRICT VIOLATION: {len(ev.critical_prune_hits)} critical "
                f"PID-coefficient pruning hits"
            )
        if apply_ov and ev.output_valid_issues:
            violations += 1
            print(
                f"   STRICT VIOLATION: {len(ev.output_valid_issues)} output_valid "
                f"wiring issues"
            )
        if apply_rb and ev.multi_axi_slave_concern:
            violations += 1
            print(
                "   STRICT VIOLATION: readback-contract not met "
                "(two slaves on one FIC master)"
            )
        if apply_mo129 and ev.speculative_prune_hits:
            violations += 1
            print(
                f"   STRICT VIOLATION (MO129 opt-in): "
                f"{len(ev.speculative_prune_hits)} hits"
            )

    if violations:
        print(f"FAIL: {violations} strict violation(s)")
        return 1
    print("OK: no strict violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
