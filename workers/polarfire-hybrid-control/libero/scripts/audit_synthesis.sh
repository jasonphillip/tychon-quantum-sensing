#!/usr/bin/env bash
# audit_synthesis.sh — Synplify post-synthesis structural audit gate.
#
# Runs AFTER SYNTHESIZE, BEFORE PLACEROUTE. Aborts the pipeline if logic
# that should be present has been pruned, or if a netlist hierarchy report
# is missing a required instance. Soft-warns on register-bit pruning and
# unconnected ports.
#
# Usage:
#   bash libero/scripts/audit_synthesis.sh
#       Auto-discover .srr (Beelink live path) and hier-resources CSV
#       (Beelink designer path), with Spark report mirrors as fallback.
#
#   bash libero/scripts/audit_synthesis.sh --srr PATH [--hier PATH]
#       Override discovery for one or both inputs (use absolute paths).
#
# Exit codes:
#   0 — audit PASSED
#   1 — audit FAILED (CL168, missing required instance, no inputs found)
#   2 — bad argument

set -uo pipefail

SRR_OVERRIDE=""
HIER_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --srr)  SRR_OVERRIDE="$2"; shift 2 ;;
        --hier) HIER_OVERRIDE="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,20p' "$0"; exit 0 ;;
        *)
            echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REF_DIR="/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"

# ----- collect .srr inputs -------------------------------------------------
shopt -s nullglob
SRR_FILES=()
if [[ -n "$SRR_OVERRIDE" ]]; then
    if [[ ! -f "$SRR_OVERRIDE" ]]; then
        echo "FATAL: --srr override path does not exist: $SRR_OVERRIDE" >&2
        exit 1
    fi
    SRR_FILES+=("$SRR_OVERRIDE")
else
    SRR_FILES+=("$REF_DIR"/synthesis/*.srr)
    SRR_FILES+=("$REPO_ROOT"/libero/reports/*/MPFS_ICICLE_KIT_BASE_DESIGN.srr)
fi
shopt -u nullglob

if [[ ${#SRR_FILES[@]} -eq 0 ]]; then
    echo "FATAL: no .srr files found." >&2
    echo "  Searched (Beelink live): $REF_DIR/synthesis/*.srr" >&2
    echo "  Searched (Spark mirror): $REPO_ROOT/libero/reports/*/MPFS_ICICLE_KIT_BASE_DESIGN.srr" >&2
    exit 1
fi

echo "Audit scope: ${#SRR_FILES[@]} .srr file(s)"
for f in "${SRR_FILES[@]}"; do echo "  - $f"; done

# ----- HARD FAIL: CL168 instance prune -------------------------------------
CL168_HITS=$(grep -nH "@W: CL168" "${SRR_FILES[@]}" 2>/dev/null || true)
if [[ -n "$CL168_HITS" ]]; then
    echo "============================================================"
    echo "FATAL: Synplify CL168 prune detected."
    echo "An instance was removed because its outputs do not drive"
    echo "other instances. P&R closure on this netlist is not evidence"
    echo "for the pruned logic. Bind dangling outputs to a real"
    echo "consumer (AXI register, GPIO, InitMon trace) — do NOT use"
    echo "syn_noprune to mask the warning."
    echo "============================================================"
    echo "$CL168_HITS"
    exit 1
fi

# ----- HARD FAIL: required instances missing from hier-resources CSV -------
shopt -s nullglob
HIER_FILES=()
if [[ -n "$HIER_OVERRIDE" ]]; then
    if [[ ! -f "$HIER_OVERRIDE" ]]; then
        echo "FATAL: --hier override path does not exist: $HIER_OVERRIDE" >&2
        exit 1
    fi
    HIER_FILES+=("$HIER_OVERRIDE")
else
    HIER_FILES+=("$REF_DIR"/designer/*/COMPILE/*compile_netlist_hier_resources.csv)
    HIER_FILES+=("$REPO_ROOT"/libero/reports/*/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_hier_resources.csv)
fi
shopt -u nullglob

if [[ ${#HIER_FILES[@]} -gt 0 ]]; then
    HIER_CSV="${HIER_FILES[0]}"
    echo "Hier-resources scope: $HIER_CSV"
    for required in nv_pid_top Vectorblox_ss; do
        if ! grep -q "$required" "$HIER_CSV"; then
            echo "FATAL: required instance '$required' not found in"
            echo "  $HIER_CSV"
            exit 1
        fi
    done
else
    echo "INFO: no compile_netlist_hier_resources.csv found — skipping hier check."
    echo "      (run after compile_netlist stage to enable)"
fi

# ----- SOFT WARN: CL189 register-bit pruning -------------------------------
CL189_TOTAL=0
for f in "${SRR_FILES[@]}"; do
    n=$(grep -c "CL189" "$f" 2>/dev/null || true)
    CL189_TOTAL=$((CL189_TOTAL + n))
done
if [[ $CL189_TOTAL -gt 0 ]]; then
    echo "INFO: CL189 register-bit pruning detected ($CL189_TOTAL hits, informational)."
fi

# ----- SOFT WARN: floating output ports ------------------------------------
UNCON_HITS=$(grep -nH "is unconnected" "${SRR_FILES[@]}" 2>/dev/null | head -20 || true)
if [[ -n "$UNCON_HITS" ]]; then
    echo "INFO: unconnected ports detected (showing first 20):"
    echo "$UNCON_HITS"
fi

echo "Synthesis audit PASSED."
exit 0
