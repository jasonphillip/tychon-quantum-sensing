# PolarFire Hybrid Control

Hybrid PID + neural network control system for PolarFire SoC. SmartHLS C++ implementation with bounded safety architecture (Lur'e/Circle Criterion) and CoreVectorBlox integration for on-chip AI inference. Hardware: Icicle Kit (MPFS250T); synthesis host: Beelink (`ssh bee`). Reference detail lives in `docs/claude/` — see the Context Map at the bottom and load on demand.

## Lane Contract (orchestration)
- WORKER lane: executes dispatches from `tychon-verification-workbench` (TVW) and reports results; a worker session must not issue cross-program dispatches itself. Strategic next-steps hand UP to TVW with a ready-to-paste prompt.
- The `polarfire-hybrid-control` repo owns FPGA-side artifacts including `.vnnx`. The `odmr-edge-ml` repo produces TFLite intermediates and stops there. Never tell an ML-session agent to ssh bee for `vnnx_compile` — that's a cross-repo handoff via a separate polarfire-hybrid-control session.

## Scope
Does: SmartHLS C++ PID controller with bumpless AI-to-PID transfer; sector saturation clamps (+-5%) and slew-rate limiting on AI output; hardware watchdog infrastructure (revised near-term idfix2 target is sub-2 ms, `WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz); Libero SoC project targeting MPFS250T with CoreVectorBlox V250; SmartTime timing and SmartPower power analysis.

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
- **Canonical `.vnnx`:** `models/fcnn_v2_residual_dataset_a.vnnx` (12.5 KB, sha256 `6c5cd21a…`, DLOG-048) — on spark2 + bee.
- **Toolchain trap:** firmware must use the **Apr-28** `tychon-polarfire-control` SmartHLS driver for axi4target offsets (the May-17 RPO-4 rebuild ≠ the bitstream version).
- **Dashboard LIVE contract:** only enable M0 writes with `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1`; never read M0; write only `R_OUT_MIN`, `R_OUT_MAX`, `R_KP`, `R_KI`, `R_KD`, `R_INNER_CLAMP`, and `R_ACC_START`; read actuator from M1 `R_POST_CLAMP`.
- **Watchdog wording:** current programmed demo image is the verified 2 ms fabric watchdog build (`WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz). When the V250 helper is stopped, the timeout state should be presented as safe fallback active, not as a broken system.
- **Safety claim language:** README and `safety_architecture.md` say "sector-bounded by design within the Phase I assumptions" rather than "AI cannot destabilize."

## Ground-Truth Discipline
Full contract: `docs/agent_ground_truth_contract.md` (priority order + cautionary examples also in `docs/claude/ground-truth-discipline.md`). Core:
- Treat prior notes, project docs, memories, and previous assistant conclusions as **orientation only** until reconciled against primary artifacts. Generated seed_7 artifacts, live silicon, SDK source, and primary Microchip docs win.
- Label every significant FPGA/VectorBlox/Libero claim: **HYPOTHESIS** (plausible, not yet verified) / **CONFIRMED** (backed by live silicon, generated seed_7 RTL/config/reports, SDK source, or a primary Microchip document) / **FALSIFIED** (directly contradicted by one of those ground-truth sources) / **STALE/RISKY** (inherited from memory, old docs, previous plans, or prior chat transcripts).
- Do **not** say "ruled out", "confirmed", or "root cause" unless the exact evidence is cited: filepath+line/grep, command output, register address+raw value, SmartDebug probe name+value, or primary-doc section/table.

## Autonomous Debug Operating Envelope
When Jason grants a debug direction in auto mode, keep moving without asking for permission at every discriminator. Full envelope (zone details, escalation rules): `docs/claude/debug-envelope.md`.
- **Green zone** (proceed autonomously): read-only live-target inspection; bounded reproduction probes over already-proven software paths; source/artifact/corpus inspection; building analysis tools, sim utilities, and branch bitstreams as long as they are not programmed onto hardware; dated evidence-labeled doc updates.
- **Yellow zone** (only if the live prompt explicitly pre-approves the action class; reversible, bounded, reported): temporary MSS/FIC/MPU diagnostic writes with save/restore; runtime overlays or driver/device-tree tweaks removable without reprogramming.
- **Red zone — STOP for Jason approval:**
  - Programming FPGA fabric, eNVM, sNVM, SPI flash, HSS, U-Boot, Linux images, or any persistent boot artifact unless the live prompt has explicitly approved that action class.
  - Setting LOCK bits, changing SEG mappings, broad MSS config changes, or writes whose blast radius is not proven and reversible.
  - Touching the severed PID slave at `0x60001000` unless Jason explicitly reauthorizes it for a named experiment.
  - Re-synth/reprogram decisions that would replace the trusted seed_7 fallback.
  - Destructive git/filesystem operations, cleanup of unknown files, or overwriting user/other-agent changes.
- Changing hardware state is allowed when it is a purposeful, logged, rollback-safe experiment. Before any persistent or broad hardware-state change, capture the current artifact identity and hash, exact rollback artifact/path/command, current relevant register/config baseline, exact change command/script, expected discriminator, and stop condition.

## Reference Corpus
Dedicated corpus at `~/.corpus/polarfire-control-corpus/`. Search it (`/search-corpus polarfire-control-corpus "<query>"`) BEFORE making any claims about Microchip toolchain APIs, PolarFire SoC fabric details, CoreVectorBlox IP, Synplify Pro message IDs, Lur'e/sector-bounded NN stability, ODMR closed-loop tracking, or VectorBlox V250 deployment (full topic breakdown: `docs/claude/reference-corpus.md`). Do NOT rely on training data for these topics — the corpus has authoritative primary sources (Microchip user guides, vendor handbooks, peer-reviewed papers) that may contradict assumptions.

## Debugging
Before chasing any bug, build failure, or toolchain stall, read `docs/claude/debugging-discipline.md` (9 hard rules; previous sessions burned hours by skipping them). When 30+ min pass with no new evidence, use the `second-opinion` skill.

## Beelink (remote synthesis) Rules
- Never edit source on Beelink — Spark is source of truth
- Always git pull on Beelink before building
- Beelink pushes synthesis reports only (libero/reports/)
- Commands, wrapper paths, and the parallel seed-sweep pattern: `docs/claude/beelink-remote-synthesis.md`

## Commit Messages
- Describe what changed technically, not how it was built
- Never reference specific development tools, assistants, or AI in commit messages
- Example good: "Fix bumpless transfer edge case in watchdog timeout"
- Example bad: "Refactor of watchdog logic"

## Do NOT
- Use VectorBlox SDK v3.0
- Put .vnnx binaries in git
- Write firmware/main.c until SmartDesign memory map is locked
- Use `ap_fixed<W,I>` — that's Xilinx; SmartHLS uses `hls::ap_fixpt<W,I>`

## Context Map — load on demand
| When the task involves... | Read |
|---|---|
| Current bitstream/dashboard state, 2026-06-21 remediation, V250 loop helper, 2 ms watchdog image, measured latency, programming discipline, audit gate (`make verify-local`) | `docs/claude/current-state.md` |
| Bring-up history (rungs A–G), seed_7 closure/fallback, FlashPro/COM ports, Linux-vs-bare-metal decision, strategy audit, FIC_0 address map, `.job` backup | `docs/claude/bringup-history.md` |
| Corpus topic list, VectorBlox deployment sources, complementary corpora | `docs/claude/reference-corpus.md` |
| Ground-truth priority order, conclusion gates, FIC2 MPU cautionary example | `docs/claude/ground-truth-discipline.md` |
| Debug autonomy zones (full text), escalation and hardware-change protocol | `docs/claude/debug-envelope.md` |
| File layout, build/test commands, Libero Tcl flow, safety architecture summary, SDK/toolchain gotchas (Python 3.10, flatc, port mangling) | `docs/claude/file-structure-and-build.md` |
| Bug / build failure / toolchain stall — the 9 debugging rules | `docs/claude/debugging-discipline.md` |
| ssh bee commands, wrapper paths, parallel P&R / seed sweeps, Multi-Pass seed gotcha, Tcl path syntax | `docs/claude/beelink-remote-synthesis.md` |
| Pointers to key project docs (safety architecture, Phase I closeout, runbooks, remediation ledgers) | `docs/claude/key-documents.md` |
