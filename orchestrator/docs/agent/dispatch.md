> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# Cross-lane dispatch (dispatch.sh)

> Moved verbatim from CLAUDE.md §Cross-lane dispatch on 2026-09-04 (harness-sota restructure).
> The one-line rule (dispatch.sh, never pasted prompts; end with id + relay one-liner) stays in
> CLAUDE.md §Every session.

Cross-lane dispatches go through `tvw/scripts/dispatch.sh` — NOT via pasted prompts
(paste is the fallback only when the target lane runs on a machine without access to
`~/projects`). Manual pastes silently truncated 3 times on 2026-07-09, once costing a
training run; dispatch.sh is file-based end to end and sha256-verifies every body.

- Send: `tvw/scripts/dispatch.sh send <to-lane> "<title>" --file <body.md>` (or pipe stdin).
  The body file lands verbatim in `~/projects/<to-lane>/.dispatch/inbox/<id>.md`.
- Overview: `tvw/scripts/dispatch.sh list [--all|--lane X]` — every dispatch in flight, one line each.
- The worker lane consumes with `show <id>` and closes with `ack <id> [note]`; acked
  dispatches are kept in `.dispatch/done/` as the permanent record.
- MANUAL + VISIBLE by design (Jason override #3, 2026-07-10): no SessionStart hooks, no
  auto-consumption. Jason relays a one-liner ("check your dispatch inbox") to the worker
  session; the content itself never crosses a paste boundary.
- Still end every cross-lane next-step with the dispatch id + the one-liner for Jason to
  relay, per the standing orchestration rules.
- Worker lanes check their inbox at session start (2026-08-19 — their CLAUDE.mds carry
  the ritual). Mechanical courier pings may travel via native cross-session messaging
  (global CLAUDE.md §Orchestration); payloads still move by file only.
- Envelope: bodies follow `tvw/scripts/dispatch-template.md` (objective, scope,
  acceptance criteria, evidence required, dependencies, source revision, reply
  destination). Acks carry an evidence receipt. Use `--predict h,sessions,p` on send —
  calibration stats need it.

## Claims and leases

Claims are optional. Run `claim <id> [--by <name>] [--lease <hours>]` before starting work.
The default holder is the current lane, or `$USER@$(hostname -s)` outside a lane.
The default lease is 24 hours. Positive fractional hours also work.
The same holder can renew. Another holder gets exit 3 while the lease is live.
Expired claims allow takeover. The old claim stays in `<id>.claim.expired-<epoch>`.
`list` shows `claimed(holder, expiry)` or `claim-expired` in STATUS.

Run `release <id> [--by <name>]` to release your claim. `--force` overrides ownership.
`ack <id> [--by <name>] [--force] [note]` also checks live claims.
Ack copies claim metadata into the done stamp and removes the claim.
If ack stops after writing done, rerun it to finish cleanup without changing the receipt.
Claim sidecars are never envelopes. Body SHA-256 checks remain unchanged.

`DISPATCH_ROOT` overrides `~/projects`; the existing `DISPATCH_LANES_ROOT` override still works.
Atomic ID reservations stay in `<root>/.dispatch-ids/`. Concurrent sends get distinct IDs across lanes.
Claim changes use short-lived `<id>.lock` directories. Normal exits and signals remove them.
After SIGKILL before ack commits, remove a leftover lock only after confirming its writer has stopped.

## Related standing rules (global CLAUDE.md §Orchestration)
- Lane roles: TVW orchestrates; worker lanes execute and report. Workers hand strategic
  next-steps UP to TVW; only mechanical handoffs go sibling-to-sibling.
- Hardware/purchase decisions are Jason's: never put BOM/budget tasks in a dispatch; decision-gated
  dispatches carry a HOLD header (memory `feedback_hardware_decisions_are_jasons.md`).
- Dispatches specify deployment geometry when downstream architectures assume a prior
  (memory `feedback_dispatch_specifies_geometry.md`).
- Lane registry: `~/projects/claude-config/registry/lanes.yml`.
