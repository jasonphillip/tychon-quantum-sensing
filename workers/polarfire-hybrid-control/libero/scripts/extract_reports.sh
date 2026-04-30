#!/bin/bash
# extract_reports.sh — copy post-P&R reports from the Beelink Libero project
# back to Spark1 under libero/reports/<date>/. Intended to run on Spark1.
#
# Usage:  bash libero/scripts/extract_reports.sh 2026-04-28-pdcfix

set -euo pipefail

DATE_TAG="${1:?usage: $0 <date-tag>}"
DEST="libero/reports/${DATE_TAG}"
mkdir -p "$DEST"

REF_PROJECT_DIR="/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
REF_TOP="MPFS_ICICLE_KIT_BASE_DESIGN"

echo "==> Extracting reports to $DEST"

# Designer reports (timing, iteration summary, resource, layout log)
ssh bee "cd $REF_PROJECT_DIR/designer/$REF_TOP && tar cf - \
    ${REF_TOP}_iteration_summary.rpt \
    ${REF_TOP}_compile_netlist_resources.rpt \
    ${REF_TOP}_compile_netlist.log \
    ${REF_TOP}_dsp_rpt.txt \
    ${REF_TOP}_ram_rpt.txt \
    ${REF_TOP}_fanout_rpt.txt \
    ${REF_TOP}_cdc.csv \
    ${REF_TOP}_layout_log.log \
    ${REF_TOP}_bankrpt.rpt \
    ${REF_TOP}_fpga_mapper_resourceusage.rpt \
    place_and_route_jitter_report.txt \
    2>/dev/null || true" | tar xf - -C "$DEST" 2>/dev/null || true

# Per-seed timing reports — pick the highest-numbered run/seed pair.
# The earlier `head -3` of an alphabetic listing returned r1_s1, r2_s10, r2_s11
# (lexicographic), missing the latest closure (r3_s22). Sort numerically on
# (run, seed) and take the tail.
RS=$(ssh bee "ls $REF_PROJECT_DIR/designer/$REF_TOP/${REF_TOP}_timing_r*_s*.rpt 2>/dev/null \
    | sed 's|.*_timing_r\([0-9][0-9]*\)_s\([0-9][0-9]*\)\.rpt|\1 \2|' \
    | sort -k1,1n -k2,2n | tail -1")
RUN_N=$(echo "$RS" | awk '{print $1}')
SEED_N=$(echo "$RS" | awk '{print $2}')
if [ -n "$RUN_N" ] && [ -n "$SEED_N" ]; then
    echo "==> Latest run/seed: r${RUN_N}_s${SEED_N}"
    ssh bee "cd $REF_PROJECT_DIR/designer/$REF_TOP && tar cf - \
        ${REF_TOP}_timing_r${RUN_N}_s${SEED_N}.rpt \
        ${REF_TOP}_timing_violations_max_r${RUN_N}_s${SEED_N}.rpt \
        ${REF_TOP}_timing_violations_min_r${RUN_N}_s${SEED_N}.rpt \
        2>/dev/null || true" | tar xf - -C "$DEST" 2>/dev/null || true
else
    echo "==> WARN: no timing_r*_s*.rpt files found"
fi

# SmartPower
ssh bee "find $REF_PROJECT_DIR/designer/$REF_TOP -maxdepth 1 -name '*power*' -o -name '*Power*' 2>/dev/null | head -10" \
    | while read -r f; do
        [ -z "$f" ] && continue
        echo "  copying $(basename "$f")"
        scp -q "bee:$f" "$DEST/"
    done

# Synthesis report
scp -q "bee:$REF_PROJECT_DIR/synthesis/${REF_TOP}.srr" "$DEST/" 2>/dev/null || true
scp -q "bee:$REF_PROJECT_DIR/synthesis/synplify.log" "$DEST/" 2>/dev/null || true

# Tcl session log
scp -q "bee:~/dev/projects/polarfire-hybrid-control/libero/reports/_pdc_rerun.log" "$DEST/" 2>/dev/null || true

echo "==> Files copied:"
ls -la "$DEST/" | head -30
