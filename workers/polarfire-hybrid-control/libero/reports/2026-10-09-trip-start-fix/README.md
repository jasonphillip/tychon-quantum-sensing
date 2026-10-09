# Trip-start fix (1a) — board retest 2026-10-09

Software fix for the short-stall hole found in `../2026-10-09-watchdog-fallback/` (criterion C3). Rule (`firmware/linux/wd_trip_start.h`, shared by `v250_pid_loop` and `wd_fallback_test`): before every inference and on every inference poll, read the watchdog register; if the timeout bit is high and no start has been forced since it was last seen low, write the current error and u_ai and start the core once, so the core sees the timeout at a start. Starts disarmed (arms after the first low reading). On by default in `v250_pid_loop` (`--no-trip-start` disables); opt-in `--trip-start` in `wd_fallback_test`.

- Same 82-run scenario set as the first run, with `CONTROL_EXTRA_ARGS=--trip-start` (`metadata.txt`, `commands.txt`). Binaries: `binary-sha256.txt`; also on the NAS with the raw observer logs: `/mnt/nas/backups/bee-polarfire-hybrid-control/wd-fallback-2026-10-09/run-tripstart-20261009T184529Z/`.
- `rawcheck_summary.txt`: `../2026-10-09-watchdog-fallback/rawcheck.py` (now skips forced rows when measuring; it reproduces the first run's summary unchanged).
- `prodcheck/`: the production loop before and after the fix (rate, forced starts on real pauses).
