# Decision-2 Option C — recovered run-3 / seed-22 reports (2026-04-29)

P&R closure: WNS +1.215 ns, 24.71% 4LUT (run 3, seed 22).

## SmartTime + SmartPower addendum (added after VERIFYTIMING/VERIFYPOWER rerun)

The April 29 PDC re-run flow exited before the post-PnR analysis stages
finished saving artifacts (load crash on .prjx + .msg truncation). The run-3
seed-22 layout DB itself was preserved, so VERIFYTIMING and VERIFYPOWER were
re-driven against it (no re-place, no re-route) to regenerate the SmartTime
and SmartPower reports. New files in this directory:

- `timing_analysis_jitter_report.txt` — SmartTime jitter, peak-to-peak per
  clock domain (system jitter 52 ps; PLL OUT0/OUT1/OUT3 = 135 ps).
- `MPFS_ICICLE_KIT_BASE_DESIGN_power_report.xml` — SmartPower fabric power
  (total 2672.4 mW; static 445.6 mW / dynamic 2226.8 mW; per-rail and
  per-type breakdown for §7.4 of the report).
- `smartpower.spw` and `power_analysis.sdc` — SmartPower workspace and the
  derived SDC used for the analysis.
