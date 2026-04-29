#!/usr/bin/env bash
# closure_with_watchdog.sh — run pnr_verify_only.tcl on Beelink with a
# 10-minute no-progress hang-watchdog. Kills libero + synplify_pro if
# the monitored files do not change for 600 consecutive seconds.
#
# Run on Beelink. Exits:
#   0 — closure completed cleanly
#   2 — watchdog fired (hang detected, processes killed)
#   * — libero failure exit code

set -uo pipefail

REF="/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
HANG_TIMEOUT=600          # 10 min of no file activity = hang
POLL_INTERVAL=60          # poll every minute

monitor_files=(
    "$REF/synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.srr"
    "$REF/synthesis/synplify.log"
    "$REF/synthesis/synlog/MPFS_ICICLE_KIT_BASE_DESIGN_fpga_mapper.srr"
    "$REF/designer/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN_layout_log.log"
    "$REF/designer/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN_iteration_summary.rpt"
)

LOG=/tmp/libero_closure.log
: > "$LOG"

# Sanity: must be in repo root for SCRIPT:libero/scripts/... to resolve.
cd ~/dev/projects/polarfire-hybrid-control || {
    echo "[watchdog] FATAL: cannot cd to repo root" >&2
    exit 1
}

echo "[watchdog] $(date +'%F %T') launching libero pnr_verify_only"
libero "SCRIPT:libero/scripts/pnr_verify_only.tcl" > "$LOG" 2>&1 &
LIBERO_PID=$!
echo "[watchdog] libero PID $LIBERO_PID; log $LOG"

last_progress=$(date +%s)
prev_state=""

while kill -0 "$LIBERO_PID" 2>/dev/null; do
    sleep "$POLL_INTERVAL"

    # snapshot mtimes (0 if file doesn't exist yet)
    cur_state=""
    for f in "${monitor_files[@]}"; do
        m=$(stat -c "%Y" "$f" 2>/dev/null || echo 0)
        cur_state="${cur_state}${m} "
    done

    now=$(date +%s)
    if [[ "$cur_state" != "$prev_state" ]]; then
        last_progress=$now
        prev_state="$cur_state"
        elapsed_total=$((now - last_progress + 0))
        echo "[watchdog] $(date +%T) progress detected; mtimes=$cur_state"
    fi

    elapsed=$((now - last_progress))
    if [[ $elapsed -gt $HANG_TIMEOUT ]]; then
        echo "[watchdog] $(date +%T) HANG — no file activity for ${elapsed}s" >&2
        echo "[watchdog] killing libero ($LIBERO_PID) and synplify_pro" >&2
        powershell -Command 'Get-Process libero,synplify_pro -ErrorAction SilentlyContinue | Stop-Process -Force' || true
        # Give Windows a moment to release the kill
        sleep 3
        # Drain the libero pid for tracking
        wait "$LIBERO_PID" 2>/dev/null || true
        echo "[watchdog] killed; closure aborted" >&2
        echo "[watchdog] tail of libero log:"
        tail -20 "$LOG"
        exit 2
    fi

    echo "[watchdog] $(date +%T) idle=${elapsed}s libero alive"
done

# libero exited on its own
wait "$LIBERO_PID"
LIBERO_EXIT=$?
echo "[watchdog] libero exited at $(date +'%F %T') with code $LIBERO_EXIT"
echo "[watchdog] tail of libero log:"
tail -25 "$LOG"
exit "$LIBERO_EXIT"
