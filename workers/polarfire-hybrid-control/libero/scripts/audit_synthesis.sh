#!/usr/bin/env bash
# audit_synthesis.sh - Synplify post-synthesis PID integration audit gate.
#
# Runs AFTER SYNTHESIZE, BEFORE PLACEROUTE. Aborts the pipeline if logic
# that should be present has been pruned, if a netlist hierarchy report is
# missing a required instance, or if Synplify preserved only structural
# reachability while folding away PID datapath semantics. Soft-warns on
# register-bit pruning and unconnected ports.
#
# Usage:
#   bash libero/scripts/audit_synthesis.sh
#       Auto-discover .srr (Beelink live path) and hier-resources CSV
#       (Beelink designer path), with Spark report mirrors as fallback.
#
#   bash libero/scripts/audit_synthesis.sh --srr PATH [--hier PATH]
#       Override discovery for one or both inputs (use absolute paths).
#
#   bash libero/scripts/audit_synthesis.sh --structural-only
#       Skip semantic-collapse checks. This is for forensic comparison only,
#       not for PID-in-loop signoff.
#
# Exit codes:
#   0 - audit PASSED
#   1 - audit FAILED
#   2 - bad argument

set -uo pipefail

SRR_OVERRIDE=""
HIER_OVERRIDE=""
STRUCTURAL_ONLY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --srr)  SRR_OVERRIDE="$2"; shift 2 ;;
        --hier) HIER_OVERRIDE="$2"; shift 2 ;;
        --structural-only) STRUCTURAL_ONLY=1; shift ;;
        -h|--help)
            sed -n '2,24p' "$0"; exit 0 ;;
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
    echo "consumer (AXI register, GPIO, InitMon trace) - do NOT use"
    echo "syn_noprune to mask the warning."
    echo "============================================================"
    printf '%s\n' "$CL168_HITS"
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

require_hier_resources() {
    local csv="$1"
    local pattern="$2"
    local label="$3"
    local min_luts="$4"
    local min_dffs="$5"
    local sums

    sums=$(awk -F, -v pat="$pattern" '
        NR > 2 && index($1, pat) {
            lut += $2 + $4
            dff += $3 + $5
            hits++
        }
        END {
            if (hits == 0) {
                print "0 0 0"
            } else {
                print hits " " lut " " dff
            }
        }' "$csv")

    read -r hits luts dffs <<< "$sums"
    if [[ "$hits" -eq 0 ]]; then
        echo "FATAL: required hierarchy '$label' not found in"
        echo "  $csv"
        exit 1
    fi
    if [[ "$luts" -lt "$min_luts" || "$dffs" -lt "$min_dffs" ]]; then
        echo "FATAL: hierarchy '$label' has too few resources for PID signoff."
        echo "  CSV:  $csv"
        echo "  Hits: $hits"
        echo "  LUTs: $luts (minimum $min_luts)"
        echo "  DFFs: $dffs (minimum $min_dffs)"
        exit 1
    fi
    echo "INFO: hierarchy '$label' resources: hits=$hits LUTs=$luts DFFs=$dffs"
}

if [[ ${#HIER_FILES[@]} -gt 0 ]]; then
    HIER_CSV="${HIER_FILES[0]}"
    echo "Hier-resources scope: $HIER_CSV"
    require_hier_resources "$HIER_CSV" "nv_pid_top_0" "nv_pid_top_0" 500 50
    require_hier_resources "$HIER_CSV" "pid_io_block_0" "pid_io_block_0" 50 50
    require_hier_resources "$HIER_CSV" "watchdog_timer_0" "watchdog_timer_0" 5 10
    if ! grep -q "Vectorblox_ss" "$HIER_CSV"; then
        echo "FATAL: required reference-design hierarchy 'Vectorblox_ss' not found in"
        echo "  $HIER_CSV"
        exit 1
    fi
else
    echo "INFO: no compile_netlist_hier_resources.csv found - skipping hier check."
    echo "      (run after compile_netlist stage to enable)"
fi

if [[ "$STRUCTURAL_ONLY" -eq 0 ]]; then
    # These patterns capture the failure mode where a module remains reachable
    # enough to avoid CL168, but Synplify folds away the actual PID state or
    # arithmetic cone. Exact instance suffixes vary by SmartHLS generation, so
    # keep the patterns anchored to stable signal/module names.
    SEMANTIC_PATTERNS=(
        "Removing sequential instance .*nv_pid_top_pid_integral"
        "Removing sequential instance .*nv_pid_top_pid_prev_error"
        "Removing sequential instance .*nv_pid_top_u_AI_latch"
        "Removing sequential instance .*nv_pid_top_inner_clamp_state"
        "Sequential instance nv_pid_top_0\\.accel_active is reduced to a combinational gate by constant propagation"
        "RAM ram\\[[^]]+\\] removed due to constant propagation"
        "Removing instance .*legup_mult.*in view: work\\.nv_pid_top_nv_pid_top.*because it does not drive other instances"
        "Removing instance .*legup_mult_pipelined_inst.*work\\.nv_pid_top_legup_mult"
        "Removing sequential instance timeout .*work\\.watchdog_timer"
    )

    SEMANTIC_HITS=""
    for pattern in "${SEMANTIC_PATTERNS[@]}"; do
        hits=$(grep -nHE "$pattern" "${SRR_FILES[@]}" 2>/dev/null || true)
        if [[ -n "$hits" ]]; then
            SEMANTIC_HITS+=$'\n'
            SEMANTIC_HITS+="$hits"
        fi
    done

    if [[ -n "$SEMANTIC_HITS" ]]; then
        echo "============================================================"
        echo "FATAL: PID semantic-collapse evidence detected."
        echo "The synthesis run preserved enough structure to avoid CL168,"
        echo "but removed state, arithmetic, RAM, or watchdog logic required"
        echo "for PID-in-loop resource/timing/power signoff."
        echo ""
        echo "Most likely causes:"
        echo "  - HLS axi_target control inputs are still tied inactive or constant."
        echo "  - PID outputs only feed a reduced debug tap instead of exact consumers."
        echo "  - Watchdog timeout is not consumed by preserved downstream logic."
        echo ""
        echo "Correct the design binding and rerun synthesis before P&R."
        echo "============================================================"
        printf '%s\n' "$SEMANTIC_HITS"
        exit 1
    fi
else
    echo "INFO: semantic-collapse checks disabled (--structural-only)."
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
    printf '%s\n' "$UNCON_HITS"
fi

echo "Synthesis audit PASSED."
exit 0
