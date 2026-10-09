> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# PolarFire Hybrid Control

Hybrid PID + neural-network control for PolarFire SoC (SmartHLS C++, sector-bounded safety, CoreVectorBlox V250). Hardware: Icicle Kit (MPFS250T); synthesis host: Beelink (`ssh bee`). This file is a map; load `docs/claude/` on demand.

## Lane Contract (orchestration)
- WORKER lane: executes dispatches from `tychon-verification-workbench` (TVW) and reports results; a worker session must not issue cross-program dispatches itself. Strategic next-steps hand UP to TVW with a ready-to-paste prompt.
- The `polarfire-hybrid-control` repo owns FPGA-side artifacts including `.vnnx`. The `odmr-edge-ml` repo produces TFLite intermediates and stops there. Never tell an ML-session agent to ssh bee for `vnnx_compile` — that's a cross-repo handoff via a separate polarfire-hybrid-control session.

## Scope
Does: SmartHLS PID, bumpless transfer, clamps, watchdog, Libero/V250 project, timing/power analysis (`docs/claude/scope-and-facts.md`).

Does NOT:
- No ML training (see: odmr-edge-ml)
- No physics simulation (see: nv-sensor-sim)
- No VectorBlox SDK v3.0 — pinned to v2.0.x (SDK 3.0 only supports the Video Kit; our SDK 2.0.3 + core 2.0.1 + `-c V250` is the correct supported Icicle pairing)
- No bare-metal-only MSS constraint — REVERSED 2026-06-15: Linux/Yocto adopted for the MSS V250 inference path (rungs C–G). Full rationale: `docs/claude/bringup-history.md`.

## Critical Constraints
- VectorBlox SDK v2.0.3 (NOT v3.0) — matches CoreVectorBlox IP v2.0.1
- .vnnx files compiled with `-c V250` flag
- SmartHLS type: `hls::ap_fixpt<W,I>` (NOT `ap_fixed` — that's Xilinx)
- Target device: MPFS250T (fallback MPFS460T)
- Libero project name: `polarfire_hybrid_control`
- SmartDesign top-level: `hybrid_control_top`

## Live Hardware Facts (safety-critical)
- Current idfix2 PID map is 0x60040000..0x60040fff; V250 is 0x60030000; never poke 0x60001000.
- **Dashboard LIVE contract:** only enable M0 writes with `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1`; never read M0; write only `R_OUT_MIN`, `R_OUT_MAX`, `R_KP`, `R_KI`, `R_KD`, `R_INNER_CLAMP`, and `R_ACC_START`; read actuator from M1 `R_POST_CLAMP`.
- **Safety claim language:** README and `safety_architecture.md` say "sector-bounded by design within the documented design assumptions" rather than "AI cannot destabilize."
- Canonical `.vnnx`, Apr-28 driver trap, watchdog wording: `docs/claude/scope-and-facts.md` — read before firmware work.

## Ground-Truth Discipline
Full contract: `docs/agent_ground_truth_contract.md`; priority order: `docs/claude/ground-truth-discipline.md`. Core:
- Treat prior notes, project docs, memories, and previous assistant conclusions as **orientation only** until reconciled against primary artifacts. Generated seed_7 artifacts, live silicon, SDK source, and primary Microchip docs win.
- Label every significant FPGA/VectorBlox/Libero claim **HYPOTHESIS** / **CONFIRMED** / **FALSIFIED** / **STALE/RISKY** — label definitions: `docs/claude/ground-truth-discipline.md`.
- Do **not** say "ruled out", "confirmed", or "root cause" unless the exact evidence is cited: filepath+line/grep, command output, register address+raw value, SmartDebug probe name+value, or primary-doc section/table.

## Autonomous Debug Operating Envelope
When Jason grants a debug direction in auto mode, keep moving without asking for permission at every discriminator. Full envelope: `docs/claude/debug-envelope.md`.
- **Green zone** (proceed autonomously) and **Yellow zone** (only if the live prompt explicitly pre-approves the action class; reversible, bounded, reported): lists in `docs/claude/debug-envelope.md`.
- **Red zone — STOP for Jason approval:**
  - Programming FPGA fabric, eNVM, sNVM, SPI flash, HSS, U-Boot, Linux images, or any persistent boot artifact unless the live prompt has explicitly approved that action class.
  - Setting LOCK bits, changing SEG mappings, broad MSS config changes, or writes whose blast radius is not proven and reversible.
  - Touching the severed PID slave at `0x60001000` unless Jason explicitly reauthorizes it for a named experiment.
  - Re-synth/reprogram decisions that would replace the trusted seed_7 fallback.
  - Destructive git/filesystem operations, cleanup of unknown files, or overwriting user/other-agent changes.
- Changing hardware state is allowed when it is a purposeful, logged, rollback-safe experiment. Before any persistent or broad hardware-state change, capture the baseline items listed in `docs/claude/debug-envelope.md`.

## Reference Corpus
`/search-corpus polarfire-control-corpus "<query>"` BEFORE any claim about Microchip toolchain, PolarFire SoC fabric, CoreVectorBlox, Synplify message IDs, sector-bounded NN stability, ODMR tracking, or V250 deployment. Do NOT rely on training data for these topics. Topics: `docs/claude/reference-corpus.md`.

## Debugging
Before chasing any bug, build failure, or toolchain stall, read `docs/claude/debugging-discipline.md` (9 hard rules). After 30+ min with no new evidence, use the `second-opinion` skill.

## Beelink (remote synthesis) Rules
- Never edit source on Beelink — Spark is source of truth
- Always git pull on Beelink before building
- Beelink pushes synthesis reports only (libero/reports/)

## Commit Messages
- Describe what changed technically, not how it was built
- Never reference specific development tools, assistants, or AI in commit messages
- Examples: `docs/claude/scope-and-facts.md`

## Do NOT
- Use VectorBlox SDK v3.0
- Put .vnnx binaries in git
- Write firmware/main.c until SmartDesign memory map is locked
- Use `ap_fixed<W,I>` — that's Xilinx; SmartHLS uses `hls::ap_fixpt<W,I>`

## Context Map — load on demand
| Task involves... | Read `docs/claude/` |
|---|---|
| Bitstream/dashboard state, V250 helper, watchdog image, audit gate | `current-state.md` |
| Bring-up history (rungs A–G), seed_7 fallback, FIC_0 map | `bringup-history.md` |
| Full scope, `.vnnx` identity, toolchain trap, commit examples | `scope-and-facts.md` |
| Corpus | `reference-corpus.md` |
| Ground-truth priority, claim labels, conclusion gates | `ground-truth-discipline.md` |
| Debug zones, hardware-change protocol | `debug-envelope.md` |
| File layout, build/test, Libero Tcl, toolchain gotchas | `file-structure-and-build.md` |
| Bug / build failure / toolchain stall — 9 rules | `debugging-discipline.md` |
| ssh bee commands, wrappers, seed sweeps | `beelink-remote-synthesis.md` |
| Key project docs | `key-documents.md` |

## Cross-lane dispatch inbox (2026-08-19)

At session start check the inbox: `~/projects/tychon-verification-workbench/tvw/scripts/dispatch.sh list --lane polarfire-hybrid-control`
(equivalently `ls .dispatch/inbox/ 2>/dev/null`). If a dispatch is queued: `show <id>`, do
the work, then `ack <id> "<evidence receipt: changed paths, commits, checks run>"`.
Strategic next-steps still go UP to TVW, never sideways. Rationale: `docs/claude/scope-and-facts.md`.
