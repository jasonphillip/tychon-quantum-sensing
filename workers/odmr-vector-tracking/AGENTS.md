> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# odmr-vector-tracking — lane contract

**Role**: WORKER lane (ML NV vector tracker, learned data-association). Consumes `nv-sensor-sim` datasets; its trained policies feed `polarfire-hybrid-control` (V250 NPU). Work arrives as TVW dispatches — this lane does NOT issue cross-program dispatches. Strategic next-steps (what to build/request next) go UP to a TVW session as a ready-to-paste prompt; only mechanical handoffs (copy a dataset, push a mirror) go sibling-to-sibling.

**State lives elsewhere, not here** (this file is rules only): current status in `~/Desktop/Shared/wiki/projects/odmr-vector-tracking/README.md` (auto-refreshed) and the auto-injected NOW.md; per-increment evidence in `docs/increment*_results.md`.

## Incoming dispatches from TVW (manual, file-based)
TVW queues work as files in `.dispatch/inbox/` (untracked). When Jason says "check your dispatch inbox":
1. List: `~/projects/tychon-verification-workbench/tvw/scripts/dispatch.sh list --lane odmr-vector-tracking`
2. Read: `.../dispatch.sh show <id>` — sha256-verified; on integrity MISMATCH do NOT act, ask TVW to re-send.
3. Do the work, then: `.../dispatch.sh ack <id> "one-line result note"`
Never commit `.dispatch/` contents; never poll or auto-consume — Jason relays all dispatches.
⊘ narrowed 2026-10-04 → "Jason relays all dispatches" still holds for TVW's file inbox above. In addition, a session Jason names as hub may send this lane a task that Jason asked for in the hub (global CLAUDE.md, "Hub (Jason 2026-10-03)"). This lane still never polls, and never dispatches onward.

## Hard rules
1. **Evidence before claims**: increment verdicts require eval evidence written to `docs/increment<N>_results.md`. Never overwrite a recorded verdict — add dated corrections.
2. **Deployable default is contractual**: `docs/deployable_default.md` documents the canonical policy pair. Changing it requires a TVW dispatch, not lane initiative.
3. **No retraining or policy re-selection without a dispatch** authorizing it.
4. **Artifact boundary**: this repo stops at trained models/policies. `.vnnx` and all FPGA-side artifacts belong to `polarfire-hybrid-control` — never ssh bee for `vnnx_compile` from this lane; hand off via TVW.
5. `experiments/increment4_parity_gate.py` deliberately compares against the archived ws1-era reference — its ws1 paths are its purpose, do not "fix" them.

## Git
`origin` = NAS bare mirror (file:///mnt/nas/projects/git/…, auto-pushed by TVW eod_close), `github` = private GitHub. Both stay private.

## Cross-lane dispatch inbox (2026-08-19)

At session start check the inbox: `~/projects/tychon-verification-workbench/tvw/scripts/dispatch.sh list --lane odmr-vector-tracking`
(equivalently `ls .dispatch/inbox/ 2>/dev/null`). If a dispatch is queued: `show <id>`, do
the work, then `ack <id> "<evidence receipt: changed paths, commits, checks run>"`.
Dispatches are file-based (sha256-verified) to defeat paste truncation; Jason may also
relay a one-liner pointing here. Strategic next-steps still go UP to TVW, never sideways.
