> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# nv-sensor-sim — lane contract

**Role**: WORKER lane (NV-diamond magnetometer ODMR simulator). Upstream data source for `odmr-vector-tracking` (dwell-sweep eval; strain/cross-relaxation identity-cue lineage). Work arrives as TVW dispatches — this lane does NOT issue cross-program dispatches. Strategic next-steps go UP to a TVW session as a ready-to-paste prompt; only mechanical handoffs (copy a dataset, push a mirror) go sibling-to-sibling.

**State lives elsewhere, not here** (this file is rules only): current status in `~/Desktop/Shared/wiki/projects/nv-sensor-sim/README.md` (auto-refreshed) and the auto-injected NOW.md. Code conventions: `CONTRIBUTING.md`.

## Incoming dispatches from TVW (manual, file-based)
TVW queues work as files in `.dispatch/inbox/` (untracked). When Jason says "check your dispatch inbox":
1. List: `~/projects/tychon-verification-workbench/tvw/scripts/dispatch.sh list --lane nv-sensor-sim`
2. Read: `.../dispatch.sh show <id>` — sha256-verified; on integrity MISMATCH do NOT act, ask TVW to re-send.
3. Do the work, then: `.../dispatch.sh ack <id> "one-line result note"`
Never commit `.dispatch/` contents; never poll or auto-consume — Jason relays all dispatches.

## Hard rules
1. **Dataset contracts are downstream-load-bearing**: generated dataset schemas, units, and physics defaults are consumed by `odmr-vector-tracking`. Schema or default-physics changes require a TVW dispatch and a versioned dataset name — never silently regenerate in place.
2. **Physics-fidelity claims need citations**: ground new physics (strain, cross-relaxation, lineshapes) in sources — the `odmr-pnt-nv-docs` corpus is the reference base (`/search-corpus odmr-pnt-nv-docs "<query>"`).
3. **Evidence before claims**: eval results get written to `docs/`/`figures/` with the run config that produced them; never overwrite recorded results — add dated corrections.
4. Large generated datasets/artifacts stay out of git (follow existing .gitignore); ship them to consumers via agreed paths, not commits.

## Git
`origin` = NAS bare mirror (file:///mnt/nas/projects/git/…), `github` = private GitHub. Both stay private.

## Cross-lane dispatch inbox (2026-08-19)

At session start check the inbox: `~/projects/tychon-verification-workbench/tvw/scripts/dispatch.sh list --lane nv-sensor-sim`
(equivalently `ls .dispatch/inbox/ 2>/dev/null`). If a dispatch is queued: `show <id>`, do
the work, then `ack <id> "<evidence receipt: changed paths, commits, checks run>"`.
Dispatches are file-based (sha256-verified) to defeat paste truncation; Jason may also
relay a one-liner pointing here. Strategic next-steps still go UP to TVW, never sideways.
