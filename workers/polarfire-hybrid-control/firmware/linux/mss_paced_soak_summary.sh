#!/bin/sh
# mss_paced_soak_summary.sh - summarize the MSS-paced loop daytime soak from the persistent
# heartbeat log into evidence. This is the harvest one-liner an evening session runs:
#   ssh icicle 'sh /root/bringup/mss_paced/mss_paced_soak_summary.sh /root/bringup/mss_paced/heartbeat.log'
#
# Uses only the persistent, eMMC-resident heartbeat.log (monotonic counters + wall-clock stamps).
# Requires gawk (strtonum/and/rshift) - present on the Icicle image.
LOG="${1:-/root/bringup/mss_paced/heartbeat.log}"
awk '
  /^#/ { next }
  $5=="NA" || $5=="" { na++; next }
  {
    n++
    row=$5+0; axi=strtonum($6); wd=strtonum($7); tns=$8+0; free=$9+0; alive=$3+0; run=$4
    if (n==1){ first_iso=$1; first_row=row; first_axi=axi; first_wd=wd; first_tns=tns; min_free=free; max_free=free }
    if (prow!=""){
      drow=row-prow; dtns=tns-ptns
      if (drow<0) neg_row++
      if (dtns>0){ r=drow/(dtns/1e9); if (rmin==""||r<rmin)rmin=r; if (r>rmax)rmax=r; rsum+=r; rc++ }
    }
    if (alive==0) dead++
    if (free<min_free)min_free=free; if (free>max_free)max_free=free
    prow=row; ptns=tns; last_iso=$1; last_row=row; last_axi=axi; last_wd=wd; last_tns=tns; last_run=run; last_alive=alive
  }
  END{
    if(n==0){ print "NO DATA"; exit 1 }
    dur_ns=last_tns-first_tns
    printf "samples=%d na_samples=%d\n", n, na+0
    printf "window: first=%s last=%s\n", first_iso, last_iso
    printf "daemon_uptime=%.1f s (%.2f h)\n", dur_ns/1e9, dur_ns/1e9/3600
    printf "row: first=%d last=%d steps=%d monotonic=%s\n", first_row, last_row, last_row-first_row, (neg_row?"NO("neg_row" regressions)":"yes")
    printf "axi_write_count: first=0x%x last=0x%x delta=%d (3x_steps=%d agree=%s)\n", first_axi, last_axi, last_axi-first_axi, 3*(last_row-first_row), ((last_axi-first_axi)==3*(last_row-first_row))?"yes":"NO"
    printf "sustained_rate_hz: overall=%.1f per_sample_min=%.1f mean=%.1f max=%.1f\n", (last_row-first_row)/(dur_ns/1e9), rmin, rsum/rc, rmax
    printf "watchdog: trip_first=%d trip_last=%d trip_delta=%d last_bit0=%d (trips are >2ms sched stalls; recovery proven by row monotonic)\n", rshift(first_wd,1), rshift(last_wd,1), rshift(last_wd,1)-rshift(first_wd,1), and(last_wd,1)
    printf "MemFree_kb: min=%d max=%d delta=%d\n", min_free, max_free, max_free-min_free
    printf "loop_pid_alive: dead_samples=%d last_alive=%d last_running=%s\n", dead+0, last_alive, last_run
    verdict="PASS"
    if (dead>0) verdict="FAIL(daemon_died)"
    else if (neg_row>0) verdict="FAIL(row_regressed)"
    printf "VERDICT=%s\n", verdict
  }
' "$LOG"
