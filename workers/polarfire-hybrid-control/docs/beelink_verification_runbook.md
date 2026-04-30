# Beelink Verification Runbook

Use this after `bee` is reachable from the local machine. The runner is
noninteractive and records blocked commands instead of prompting.

## Command

```bash
make beelink-verify TAG=2026-04-30-corpus
```

Optional environment overrides:

```bash
BEE_REMOTE=bee BEE_REPO=~/dev/projects/polarfire-hybrid-control make beelink-verify TAG=2026-04-30-corpus
```

## What It Runs

1. `ssh -o BatchMode=yes -o ConnectTimeout=8 bee hostname`
2. Remote branch checkout for the current branch, from either a local Beelink
   branch or `origin/<branch>`.
3. `make hls-test` on Beelink, which runs `cd hls && shls sw_run`.
4. `bash libero/scripts/closure_with_watchdog.sh` if `libero` is on the remote
   path.
5. `bash libero/scripts/extract_reports.sh <tag>` locally.
6. `python3 tools/audit_libero_reports.py libero/reports/<tag>` locally.

## Blocked Conditions

- SSH failure exits `2` and records the exact SSH command.
- Missing branch on Beelink exits `3` and records that the current branch is
  unavailable locally and on `origin`.
- Missing `libero` skips the closure/report refresh but keeps the SmartHLS
  software verification result.

## Expected Evidence

The resulting `libero/reports/<tag>/beelink_verification.log` should include:

- current branch and remote status
- SmartHLS software test result
- Libero closure exit code, when run
- extracted report list
- corpus-grounded report-audit classification
