#!/bin/sh
# mss_paced_heartbeat.sh - persistent on-kit soak monitor for the v250_pid_loop MSS-paced loop.
#
# Samples the daemon's live-state JSON (on tmpfs, high-frequency scratch) plus the loop pidfile
# every INTERVAL seconds and appends ONE wall-clock-stamped line to a PERSISTENT log on eMMC
# (/root/bringup). The persistent log is the soak evidence of record: it survives host (SSH)
# disconnect, operator session exit, and kit reboot. The daemon's own JSON stays on tmpfs so the
# high-frequency (~kHz) rewrites cause no eMMC wear and do not throttle the control loop below the
# 2 ms fabric-watchdog deadline; only this 30 s-cadence heartbeat touches eMMC.
#
# Fields (space-separated, one per sample):
#   iso_utc  uptime_s  loop_pid_alive  running  row  axi_write_count  watchdog_raw  daemon_t_ns  free_kb
# Notes:
#   - row              : software distinct-iteration counter (monotonic).
#   - axi_write_count  : fabric AXI write counter CSR (=3 per loop iteration); independent HW proof.
#   - watchdog_raw     : M1 watchdog CSR; bit0=timeout-live, bits[31:1]=trip_count (= raw>>1).
#   - daemon_t_ns      : daemon CLOCK_MONOTONIC_RAW elapsed since start; use for rate = d(row)/d(t_ns).
#   - loop_pid_alive=0 : the daemon process is gone (permanent stall / exit) -> soak FAIL.
#
# Usage: mss_paced_heartbeat.sh [state_json] [log_path] [loop_pidfile] [interval_s]
STATE="${1:-/tmp/v250_state.json}"
LOG="${2:-/root/bringup/mss_paced/heartbeat.log}"
LOOP_PID_FILE="${3:-/root/bringup/mss_paced/loop.pid}"
INTERVAL="${4:-30}"

if [ ! -f "$LOG" ]; then
  echo "# mss_paced heartbeat  iso_utc uptime_s loop_pid_alive running row axi_write_count watchdog_raw daemon_t_ns free_kb" >> "$LOG"
fi

while :; do
  iso=$(date -u +%FT%TZ)
  up=$(cut -d. -f1 /proc/uptime)
  st=$(cat "$STATE" 2>/dev/null)
  running=$(printf '%s' "$st" | sed -n 's/.*"running":\([a-z]*\).*/\1/p'); running=${running:-NA}
  row=$(printf '%s' "$st" | sed -n 's/.*"row":\([0-9]*\).*/\1/p'); row=${row:-NA}
  axi=$(printf '%s' "$st" | sed -n 's/.*"axi_write_count":"\(0x[0-9a-f]*\)".*/\1/p'); axi=${axi:-NA}
  wd=$(printf '%s' "$st" | sed -n 's/.*"watchdog_raw":"\(0x[0-9a-f]*\)".*/\1/p'); wd=${wd:-NA}
  tns=$(printf '%s' "$st" | sed -n 's/.*"t_ns":\([0-9]*\).*/\1/p'); tns=${tns:-NA}
  free=$(awk '/MemFree/{print $2; exit}' /proc/meminfo)
  lp=$(cat "$LOOP_PID_FILE" 2>/dev/null)
  if [ -n "$lp" ] && kill -0 "$lp" 2>/dev/null; then alive=1; else alive=0; fi
  echo "$iso $up $alive $running $row $axi $wd $tns $free" >> "$LOG"
  sync
  sleep "$INTERVAL"
done
