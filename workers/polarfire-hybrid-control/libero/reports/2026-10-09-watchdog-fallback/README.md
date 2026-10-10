# Watchdog fallback board test — 2026-10-09

Run of `docs/watchdog_fallback_test_plan.md` on the Icicle Kit (two-slot idfix2 bitstream), driven from ws2 over SSH. Run directory on the kit: `/root/watchdog-runs/20261009T175628Z-watchdog`. Raw logs (174 MB, observer and control CSVs for all 82 runs): `/mnt/nas/backups/bee-polarfire-hybrid-control/wd-fallback-2026-10-09/run-20261009T175628Z/`.

- `metadata.txt`, `commands.txt`, `binary-sha256.txt`, `zeroing.txt`: as written by `tools/run_wd_fallback.sh` (the repository commit it records is the kit's local snapshot of `portfolio/integration`; source tip at run time: polarfire-hybrid-control `ae74450` plus the b6-tools commit).
- `control-logs/*.csv.gz`: every control-tool log (one row per controller update). These are the primary evidence for the verdicts.
- `analyzer/*-criteria.md`: the output of `tools/wd_fallback_analyze.py` as run on the kit. **Its A1/B1 "clear-to-rise" and A3 bracketing are wrong** (it measures from the timeout bit's previous fall, not from the last inference completion, and it mis-brackets the pause), so A1, B1, A3 and the end-to-end part of B2 in these files are not the record. The record is `rawcheck_summary.txt`, computed by `rawcheck.py` from the control logs with the observer rise times.
