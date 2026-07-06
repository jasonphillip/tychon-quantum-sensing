# PolarFire Hybrid Control

## Project
Hybrid PID + neural network control system for PolarFire SoC. SmartHLS C++ implementation with bounded safety architecture (Lur'e/Circle Criterion) and CoreVectorBlox integration for on-chip AI inference.

## Key Documents
- `docs/safety_architecture.md` — Lur'e/Circle Criterion formal framing, watchdog and bumpless transfer design, Residual Proof Obligations (closable under follow-on path) table
- `docs/phase1_closeout_findings.md` — Phase I closeout for the Final Report and methodology case study
- `docs/smartdesign_two_slot_canvas_runbook.md` — GUI/Tcl steps for the CoreAXI4Interconnect two-slot canvas refresh (follow-on deployment path)
- `docs/remediation_status_2026-06-21.md` — current max-throughput remediation closeout: dashboard honesty, latency/resource evidence, ML harness, research status, and #1-#13 roadmap table
- `docs/remediation_progress_2026-06-21.md` — compact-safe execution ledger with commands, raw evidence, stop conditions, and next actions
- `docs/latency_measured_2026-06-21.md` — measured on-kit V250/PID helper bounds plus host-paced rung-G timing; still not a pure `rdcycle` or fabric-cycle result
- `docs/workload_smartpower_2026-05-17.md` — SmartPower proof-obligation history; 2026-06-21 explicit-VCD-top rerun attempt is logged as no closure
- `README.md` — Architecture diagram, build instructions, safety overview

## Recent Architectural Changes
- **2026-06-21 remediation:** dashboard LIVE is now idfix2-aware and gated (`KIT_BITSTREAM=idfix2` + `ALLOW_IDFIX2_M0=1`), M0 writes are allowlisted to gains/limits/inner-clamp/start only, M0 reads remain blocked, actuator reads come from M1 `R_POST_CLAMP`, and stale dashboard/report claims were corrected to host-paced hardware datapath wording. Deployed accuracy claim is about 5% for `fcnn_v2_residual_dataset_a`; `8.71%` is stale/failed-cascade context only. Evidence: `docs/remediation_status_2026-06-21.md` and the dashboard repo.
- **2026-06-21 V250 loop helper:** added `firmware/linux/v250_pid_loop.c` and dashboard `NN: V250 loop` mode. The helper runs V250 inference on the kit, optionally quantizes per-row ODMR CSV inputs into the V250 input buffer, dequantizes `out[0]`, writes M1 `u_ai`, pulses M0 `acc_start`, and streams M1 actuator/watchdog rows. It now also supports persistent userspace daemon mode with `/api/v250-loop/start|status|stop`; dashboard evidence shows row advance with watchdog clear and clean stop. CONFIRMED that M0 `inner_clamp_setpoint=0.045` at `0x60040020` is required; if left zero, the HLS safety clamp clamps the AI term to zero. Current deployed row CSV is `/root/bringup/odmr_v250_rows.csv`; this is Linux userspace loop closure, not yet autonomous FPGA-resident wiring or live sensor input. Evidence: `docs/v250_pid_loop_2026-06-21.md` and `libero/reports/2026-06-21-v250-pid-loop/`.
- **2026-06-21 FPGA push:** added `firmware/linux/vnnx_latency.c` and `firmware/linux/pid_latency.c`; on-kit results show V250 start+poll median `32 us` / p99 `33 us` and idfix2 M0 pulse+M1 read median `4 us` / p99 `4 us`. `rdcycle` traps in userspace, so these are API/MMIO bounds, not pure cycle counts. A cloned `WATCHDOG_TIMEOUT_CYCLES=125000` safety build reached Synplify/map success in one path, but headless Libero handoff/export probes still failed: state forcing, `run_synthesis -target`, unverified export, and clean `.vm` import did not produce a safety `.job`; no 1 ms image was programmed. SmartPower explicit-top VCD rerun produced a default-equivalent report but no annotation evidence; no workload-annotated power number exists.
- **2026-06-21 2 ms watchdog closeout:** built, exported, and programmed the dated two-slot `WATCHDOG_TIMEOUT_CYCLES=250000` image after recording rollback hashes, exact rollback command, and FlashPro scan visibility. Post-program checks passed for `csr_version=0x00010000`, V250 `out[0]=-2.9506`, guarded actuator telemetry, and V250-loop clear / stop-trip watchdog behavior. Evidence: `libero/reports/2026-06-21-watchdog-2ms/`.
- **2026-06-21 demo-positioning decision:** near-term finish criteria are now hardware-real hybrid control with a modest, honest NN assist, plus a verified sub-2 ms fabric watchdog target (`WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz). The 1 ms build remains nice-to-have, not the Phase-I credibility gate. See `docs/credible_demo_finish_criteria_2026-06-21.md`.
- **Audit gate** (supports follow-on closure path) is `make verify-local` (corpus-grounded calibration; replaces the single-shot `libero/scripts/audit_synthesis.sh` for CI). `verify-strict` adds fail-fast on critical pruning + output_valid wiring + readback-contract.
- **Canvas refresh runbook** (follow-on deployment path) per `docs/smartdesign_two_slot_canvas_runbook.md`. New HDL `libero/hdl/pid_csr_block.v` + `libero/hdl/vbx_pulse_gen.v` is testbench-validated (`make hls-test-local` D.1/D.2/D.3 pass) but **not yet netlist-validated** — the runbook is the production path.
- **Safety claim language**: README and `safety_architecture.md` say "sector-bounded by design within the Phase I assumptions" rather than "AI cannot destabilize." The six Residual Proof Obligations (closable under follow-on path) — plant ID, ZOH phase margin, transport delay, derivative filter SI, ReLU sector verification, workload-driven SmartPower — are listed in `docs/safety_architecture.md`.

## Current idfix2 / Dashboard State (2026-06-21)

- **CONFIRMED:** current resident bitstream is treated as idfix2 for live dashboard use after a bounded smoke: `tools/rung_g_replay.py --host icicle --rows 5 --out /tmp/idfix2_smoke --plot` produced nonzero M1 `post_clamp_out` values and advancing `axi_write_count`.
- **CONFIRMED:** V250 probe remains live: `vbx_probe` / `vnnx_smoke` returned `INFERENCE COMPLETED`, `error_val=0`, `out[0]=-2.9506`; CSR version read `0x00010000`.
- **Dashboard LIVE contract:** only enable M0 writes with `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1`; never read M0; write only `R_OUT_MIN`, `R_OUT_MAX`, `R_KP`, `R_KI`, `R_KD`, `R_INNER_CLAMP`, and `R_ACC_START`; read actuator from M1 `R_POST_CLAMP`.
- **Watchdog wording:** current programmed demo image is the verified 2 ms fabric watchdog build (`WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz). When the V250 helper is stopped, the timeout state should be presented as safe fallback active, not as a broken system.
- **Latest FPGA artifacts:** `libero/reports/2026-06-21-latency/`, `libero/reports/2026-06-21-v250-pid-loop/`, `libero/reports/2026-06-21-watchdog-2ms/`, the historical `libero/reports/2026-06-21-safety-*` 1 ms attempt bundles, and `libero/reports/2026-06-21-workload-power-topname/`. The 2 ms watchdog bundle is the current programmed closure artifact; the 1 ms and SmartPower bundles are evidence of attempted tool runs, not closure artifacts.
- **Programming discipline:** persistent programming was performed only for the dated 2 ms watchdog image after rollback hashes, exact rollback command, and FlashPro scan visibility were recorded. Before any future program, record the exact rollback command, current artifact identity, expected discriminator, and post-program cold-cycle checks.

## FPGA bring-up state (2026-06-15)
**Canonical state doc:** `docs/track0_bringup_runbook.md`. **Active driver:** `~/.claude/plans/i-plugged-in-j11-optimized-quilt.md` (execution log has the full 2026-05-18 → 2026-06-02 arc). **Bring-up plan:** `~/.claude/plans/goal-take-the-existing-wobbly-hollerith.md` (A–I stop-gates) — note the strategy audit below recommends reshaping it.

Quick orient (do not re-audit from repo state alone — substantial work lives on Beelink):
- **Rung A DONE 2026-06-15 — PROGRAM PASS on Production silicon.** The seed_7 bitstream is on the kit: FPExpress `run_selected_actions` PROGRAM PASSED on device `MPFS250T` (IDCODE `1F81A1CF`, no `_ES`; Device Rev 01; `ISC_ENABLE_RESULT 00000000`, `CRCERR 00`; elapsed 57 s). On-silicon **fabric digest `0769…C03DF8` + sNVM digest `EBF8…D32507` match the seed_7 closure byte-for-byte** → exact V250-in-fabric hybrid bitstream confirmed. `program_kit.tcl` was reworked ES-override → production operator-mode flow (commit `e83cf9d`); PASS log + read-only pre-flight scan committed `0c2bcaf`; closed `.job` backed up to `/mnt/nas/backups/bee-polarfire-hybrid-control/` (sha256 `d5f3eb4e` verified). New FlashPro6 `F31E000A`; CP2108 ports **COM7/8/9/10** (old `065D9ACD`/COM3-6 are ghosts). MMUART0→COM still TBD (best-effort, deferred to rung D). Evidence: `libero/reports/2026-06-15-program/program.log`, `docs/silicon_production_confirmed_2026-06-02.md`. (Original ES board blocked rung A 2026-05-18; forensics in `libero/reports/2026-05-18-program-*`.)
- **Closed historical seed_7 fallback is the `MPFS_ICICLE_Vectorblox.prjx` r6_s25 closure** — CoreVectorBlox V250 NPU in fabric by construction. 11.5 MB `.job` on bee, sha256 `d5f3eb4e…`. **V250 control slave = FIC_0 `0x60030000`** (cross-confirmed: SDK DT overlay + SLAVE2 extraction). Old seed_7 PID notes around `0x60001000` are historical only; current idfix2 PID access is `0x60040000..0x60040fff`, and `0x60001000` must not be touched. See `docs/fic_0_address_map_2026-05-18.md`.
- **Canonical `.vnnx`:** `models/fcnn_v2_residual_dataset_a.vnnx` (12.5 KB, sha256 `6c5cd21a…`, DLOG-048) — on spark2 + bee (migrated from spark1 2026-07-05; verified present on spark2 2026-07-06).
- **ARCHITECTURE DECISION MADE 2026-06-15 — Linux/Yocto for the MSS V250 inference path (rungs C–G).** Adopted the strategy audit's recommendation under operator autonomy grant: the only Microchip-supported VectorBlox-on-Icicle runtime is Linux/Yocto (in-tree `generic-uio` + non-cached `udmabuf`); bare-metal is undocumented/high-risk (hand-rolled DDR + 2 MB firmware staging + fabric cache coherency Microchip does NOT document). The PID safety/real-time lives in FABRIC, so Linux does not compromise it; SoftConsole drops off the critical path (toolchain becomes the SmartHLS-bundled `riscv64-*-linux-gnu-gcc`). Dated rationale + override window: `docs/track0_bringup_runbook.md` (2026-06-15 decision record). Full analysis: `docs/rung_f_vectorblox_inference_research_2026-06-02.md` + `docs/vectorblox_deployment_reference_2026-06-02.md`.
- **STRATEGY AUDIT (2026-06-02) — read `docs/whole_process_strategy_audit_2026-06-02.md` before plan day.** Three inherited-default risks beyond bare-metal-vs-Linux: (1) the **"eavesdropper" `pid_io_block`** (severed read path + colliding writes) makes rung E an explainable hack — do the clean two-slot SmartDesign integration (`docs/smartdesign_two_slot_canvas_runbook.md`) first; (2) move C–G to Linux; (3) reframe the demo from "replayed CSV" to "the loop closes + a scripted clamp/watchdog safety trip." Also **[NC]: Microchip de-rated the V250 clock to 75/150 MHz on Icicle** — verify against the seed_7 closure before quoting latency. ODMR-domain credibility: `docs/odmr_demo_credibility_2026-06-02.md`.
- **SoftConsole 2022.2 build 747** on bee (only on the critical path if bare-metal). **RPO-4** landed (DLOG-046). **RPO-6** workload SmartPower: infra closed, live import deferred to a clean Libero session (`docs/workload_smartpower_2026-05-17.md`).
- **Toolchain trap:** firmware must use the **Apr-28** `tychon-polarfire-control` SmartHLS driver for axi4target offsets (the May-17 RPO-4 rebuild ≠ the bitstream version).

## Reference Corpus

This repo has a dedicated reference corpus at `~/.corpus/polarfire-control-corpus/`. Search it with the `search-corpus` skill (e.g. `/search-corpus polarfire-control-corpus "<query>"`) BEFORE making any claims about:
- Microchip toolchain APIs (SmartHLS pragmas, ap_fixpt, Libero Tcl, PDC io.pdc/fp.pdc split)
- PolarFire SoC fabric details (FIC_0/1/2/3 capabilities, MSS memory map, AXI4-Lite slave behavior)
- CoreVectorBlox v2.0.1 IP (control register map, output_valid semantics, WSTRB rules)
- Synplify Pro message IDs (CL189, CL260, BN362, MO129, MO156, etc.) — the OEM Message Reference is in the corpus
- Lur'e / Circle Criterion / sector-bounded NN stability (Khalil, recent arxiv on NN-in-loop control)
- ODMR closed-loop frequency tracking (NV-center magnetometer literature, bandwidth/slew constraints)
- **VectorBlox V250 DEPLOYMENT (added 2026-06-02):** the CoreVectorBlox control-register bit-map (IP Handbook, `vectorblox-sdk-docs-bee/`), bare-metal vs Linux runtime (`vbx_cnn_api.c` dual-path), the supported Linux/Yocto/Icicle flow (`microchip-support/VBX_2.0.3_Icicle_porting_000017296.md`), `generic-uio`+`udmabuf` device-tree mechanism, HSS/U-Boot boot chain, PolarFire SoC fabric-master cache coherency (`CoreAXI4DMAController_HB` §1.10, `mpfs-memory-hierarchy`), and the CartPole/F1TENTH FPGA-control demo benchmark. Query e.g. `/search-corpus polarfire-control-corpus "VectorBlox udmabuf generic-uio bare-metal coherency"`.

Also includes two user-contributed deep-research syntheses on SmartHLS PID datapath survival in the MPFS_ICICLE_VectorBlox design at `raw/user-contributed/`. The NN/ODMR-physics deep-research (NN-over-PID drift prediction, FPGA frequency-locking, edge-ML magnetometry) is in the complementary `odmr-pnt-nv-docs` corpus (expanded 2026-06-02).

Do NOT rely on training data for these topics — the corpus has authoritative primary sources (Microchip user guides, vendor handbooks, peer-reviewed papers) that may contradict assumptions. The complementary `pow-rf` corpus covers the RF/SDR/anomaly-detection side.

## FPGA Ground-Truth Discipline

Durable repo copy: `docs/agent_ground_truth_contract.md`.

Treat prior notes, project docs, memories, and previous assistant conclusions as **orientation only** until reconciled against primary artifacts. This project has stale and contradictory local notes from multiple bring-up phases; generated seed_7 artifacts, live silicon, SDK source, and primary Microchip docs win.

Every significant FPGA/VectorBlox/Libero claim must be labeled:
- **HYPOTHESIS** — plausible, not yet verified.
- **CONFIRMED** — backed by live silicon, generated seed_7 RTL/config/reports, SDK source, or a primary Microchip document.
- **FALSIFIED** — directly contradicted by one of those ground-truth sources.
- **STALE/RISKY** — inherited from memory, old docs, previous plans, or prior chat transcripts.

Ground-truth priority, highest first:
1. Live silicon reads, SmartDebug/FlashPro observations, raw target logs, raw register dumps.
2. Generated seed_7 Libero artifacts on bee (`component/work/**`, `designer/**`, MSS cfg XML, timing reports, probe DB output).
3. Version-matched SDK source and primary Microchip docs in the corpus (MSS TRM, MSS Configurator UG, CoreVectorBlox handbook, SDK `vbx_cnn_api.c`).
4. Canonical Microchip reference design under the installed Libero/SmartHLS tree.
5. Project docs, runbooks, memories, and previous assistant transcripts.
6. Inference.

Conclusion gates:
- Do **not** say "ruled out", "confirmed", or "root cause" unless the exact evidence is cited: filepath+line/grep, command output, register address+raw value, SmartDebug probe name+value, or primary-doc section/table.
- Before carrying forward a prior conclusion, search for contradictions in the corpus and generated seed_7 artifacts using concept synonyms. If local docs disagree with generated RTL/config or a primary document, call that out explicitly and follow the primary/generated artifact.
- For every root-cause claim, record: observed symptom, hypothesis, prediction if true, test performed, raw result, confidence, and next falsifier.
- Do not update memory or durable docs with a root cause until the claim has survived the conclusion gate.

Current cautionary example: do not treat "FIC2 MPU is open" as true unless the actual TRM-defined FIC2 MPU block is read and decoded. A prior 16-region "FIC2 MPU" read was suspect because FIC2/MPU3 is documented as a different block than FIC0/FIC1. Always reconcile MPU/FIC/SEG claims against the MSS TRM register map and live register values.

## Autonomous FPGA Debug Operating Envelope

When Jason grants a debug direction in auto mode, keep moving without asking for
permission at every discriminator. Use this envelope unless Jason gives a
narrower one in the live prompt.

Green-zone actions may proceed autonomously:
- Read-only live target inspection: SSH, register dumps, logs, dmesg, sysfs,
  UIO/udmabuf metadata, bounded read-only SmartDebug/FlashPro observations.
- Bounded reproduction probes that use already-proven software paths and time
  out cleanly, including V250 control-page starts via the current Linux runtime.
- Local or bee-side source/artifact inspection, corpus searches, generated RTL
  and report diffs, SDK/reference-design comparisons.
- Building analysis tools, probe binaries, simulation/test utilities, and branch
  bitstreams for inspection, as long as they are not programmed onto hardware.
- Updating repo docs, handoff notes, changelogs, and wiki summaries with dated,
  evidence-labeled findings.

Yellow-zone actions may proceed only if the live prompt explicitly pre-approves
the action class and the implementation is reversible, bounded, and reported:
- Temporary MSS/FIC/MPU diagnostic writes with save/restore, no LOCK bits, trap
  cleanup, raw before/after values, and no unrelated registers touched.
- Runtime overlays or driver/device-tree tweaks that are removable without
  reprogramming the FPGA.

Red-zone actions require stopping for Jason approval:
- Programming FPGA fabric, eNVM, sNVM, SPI flash, HSS, U-Boot, Linux images, or
  any persistent boot artifact unless the live prompt has explicitly approved
  that action class.
- Setting LOCK bits, changing SEG mappings, broad MSS config changes, or writes
  whose blast radius is not proven and reversible.
- Touching the severed PID slave at `0x60001000` unless Jason explicitly
  reauthorizes it for a named experiment.
- Re-synth/reprogram decisions that would replace the trusted seed_7 fallback.
- Destructive git/filesystem operations, cleanup of unknown files, or overwriting
  user/other-agent changes.

Escalate automatically through the next cheapest discriminator when the current
test falsifies a hypothesis. Stop only when a red-zone action is needed, the
hardware appears unstable, evidence contradicts the operating envelope, or a
root-cause/fix claim is ready for Jason review.

Changing hardware state is allowed when it is a purposeful, logged,
rollback-safe experiment. Do not avoid hardware work merely because it changes
state. Avoid unlogged, irreversible, or non-discriminating changes. Before any
persistent or broad hardware-state change, capture the current artifact identity
and hash, exact rollback artifact/path/command, current relevant register/config
baseline, exact change command/script, expected discriminator, and stop
condition.

## What This Repo Does
- SmartHLS C++ PID controller with bumpless AI-to-PID transfer
- Sector saturation clamps (+-5%) and slew-rate limiting on AI output
- Hardware watchdog infrastructure; the revised near-term idfix2 target is sub-2 ms (`WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz)
- Libero SoC project targeting MPFS250T with CoreVectorBlox V250
- Static timing analysis (SmartTime) and power estimation (SmartPower)

## What This Repo Does NOT Do
- No ML training (see: odmr-edge-ml)
- No physics simulation (see: nv-sensor-sim)
- No VectorBlox SDK v3.0 — pinned to v2.0.x (SDK 3.0 only supports the Video Kit; our SDK 2.0.3 + core 2.0.1 + `-c V250` is the correct supported Icicle pairing)
- ~~No Linux on MSS — bare-metal C only~~ **REVERSED 2026-06-15: Linux/Yocto adopted for the MSS V250 inference path (rungs C–G).** The bare-metal constraint was an inherited default; the only supported VectorBlox-on-Icicle path is Linux/Yocto. The old "Linux jitter violates <150 µs" rationale is incoherent — the <150 µs loop is the *fabric* PID, not MSS software (which is supervisory only). See the FPGA bring-up state block + the runbook's 2026-06-15 decision record.

## Critical Constraints
- VectorBlox SDK v2.0.3 (NOT v3.0) — matches CoreVectorBlox IP v2.0.1
- .vnnx files compiled with `-c V250` flag
- SmartHLS type: `hls::ap_fixpt<W,I>` (NOT `ap_fixed` — that's Xilinx)
- Target device: MPFS250T (fallback MPFS460T)
- Libero project name: `polarfire_hybrid_control`
- SmartDesign top-level: `hybrid_control_top`

## File Structure
```
hls/
  src/nv_pid.cpp          — Top-level PID function (II=1 pipeline, AXI target + simple wires)
  src/nv_pid.hpp          — NVPID class with bumpless transfer and anti-windup
  src/safety_clamps.cpp   — Sector saturation clamp and slew-rate limiter
  src/watchdog.cpp        — Hardware watchdog timer RTL / safety-spec timeout infrastructure
  include/fp_types.hpp    — Fixed-point typedefs: freq_t (Q34.30), gain_t/out_t (Q16.16)
  include/rta_config.hpp  — Safety constants: clamp fraction, max slew, watchdog cycles
  tb/tb_bumpless.cpp      — Bumpless transfer testbench
  tb/stimulus/            — Drop-in directory for ODMR CSV test vectors
  Makefile                — SmartHLS build config (NAME, SRCS, flags)

libero/
  scripts/01_scaffold_proj.tcl  — Initialize Libero project (MPFS250T, constraints)
  scripts/02_import_ip.tcl      — Import SmartHLS PID + CoreVectorBlox + CCC + InitMon
  scripts/03_smartdesign.tcl    — Wire MSS FIC ports, clock, reset, AXI interconnect
  scripts/04_synth_pnr.tcl      — Synthesis, P&R, SmartTime, SmartPower, report extraction
  constraints/timing_200mhz.sdc — 200 MHz (5 ns) clock constraint
  constraints/pinout.pdc         — Board-specific I/O (placeholder for Icicle Kit)
  reports/                       — Tool-generated synthesis and timing reports

	firmware/    — RISC-V MSS code. Per 2026-06-15 decision: Linux userspace tools
	               cross-built with riscv64-*-linux-gnu-gcc, NOT bare-metal.
	               Current idfix2 PID map is 0x60040000..0x60040fff; V250 is
	               0x60030000; never poke 0x60001000.
	               Current helper for kit-side V250->PID loop: v250_pid_loop.c.
models/      — Compiled .vnnx model binaries (not committed, excluded by .gitignore)
```

## Build and Test

SmartHLS and Libero require an x86 host with Microchip tools installed.

```bash
make hls-test    # Run SmartHLS C++ software testbench (verifies bumpless transfer)
make clean       # Remove build artifacts
```

Libero Tcl scripts run sequentially in the Libero Tcl console:
```
source libero/scripts/01_scaffold_proj.tcl   # Creates project, imports constraints
source libero/scripts/02_import_ip.tcl       # Imports PID RTL + CoreVectorBlox + clock/reset
source libero/scripts/03_smartdesign.tcl     # Wires AXI interconnect, promotes datapath ports
source libero/scripts/04_synth_pnr.tcl       # Runs synthesis, P&R, extracts reports
```

The `hls-test` testbench verifies:
- PID output tracks frequency error with correct gain application
- Bumpless transfer absorbs AI output into integrator without voltage discontinuity
- PASS/FAIL printed to stdout based on delta at transition vs expected natural step

## Safety Architecture (Summary)
- **Sector clamp**: AI output bounded to +-4.5% of actuator range (guarantees +-5% after Q16.16 rounding)
- **Slew limiter**: Per-cycle AI output change bounded by `MAX_SLEW_PER_CYCLE`
- **Watchdog**: current programmed demo image is 250,000 cycles at 125 MHz = 2 ms; report raw state plus the user-facing safe-fallback / AI-assist state
- Formal basis: Lur'e/Circle Criterion absolute stability — AI treated as sector-bounded nonlinearity

## Known Gotchas
- SmartHLS 2025.2 may generate different output directory names — check `hls/hls_output/` vs `hls/output/` after `shls hw`
- SmartHLS may mangle port names (e.g. `_V` suffix for std_logic_vector) — verify generated Verilog
- CoreVectorBlox VLNV string may vary by Libero version (vendor field: Actel vs Microsemi vs Microchip)
- The Tcl scripts contain `VERIFY_AFTER_SHLS_HW` comments marking values that depend on actual tool output
- VectorBlox SDK tools require x86-64 Linux — `.so` libraries won't load on ARM64 or native Windows
- Python 3.10 required for VectorBlox SDK venv (not 3.11/3.12 — ABI mismatch)
- `flatc` must be v23.5.26 (not apt default) for VectorBlox FlatBuffer compatibility

## Debugging Discipline

When chasing a bug, build failure, or toolchain stall, follow these rules. They exist because previous sessions burned hours by skipping them.

1. **Evidence inventory before hypothesis.** Before forming a theory, list every artifact (log file, error message, file mtime, prior commit, prior session log) that has data about the problem and read each in full. Cross-reference between them. *Especially*: if a failure is byte-deterministic or output-truncated, find the matching successful run of the same operation and identify exactly what's at the divergence boundary.

2. **Cheap diagnostics before surgical fixes.** GUI tests, log reads, hash compares, byte diffs, file mtime surveys. Recovery operations (edit prjx, rename dirs, restore backups) only after these are exhausted. Hard rule.

3. **Time-box "no new evidence" stretches.** 30 min of fix attempts without learning anything new = step back, re-read evidence, change category of approach. Not "try a slightly different fix."

4. **Forensics before the first failed run.** WerFault local dumps, ProcMon traces, verbose Tcl/synth flags, captured stderr — these are 5 min of setup per session and pay back across every subsequent run. Set them up before any toolchain operation that has shown silent failures.

5. **Backups demand immediate diffs.** A `.bak` file you make and then ignore is overhead, not insurance. Hash and diff it against current state in the same minute you create it.

6. **Conclusion gate.** Before declaring a root cause in a commit message or a notes file, write the evidence→cause chain explicitly. If you can't articulate it, you don't have it. A claimed root cause must explain *all* the symptoms, including why the system worked previously.

7. **Surface silent / byte-deterministic failures to the user early.** That class of bug is rarely solvable from a CLI shell. Ask for hands-on access (GUI, fresh terminal, second machine) within 30 min of identifying the pattern, not after hours of pushing.

8. **For Tcl / batch-mode tools: explicit `flush stdout` before every potentially-blocking call**, and capture stderr to a separate file. Batch-mode buffering quirks burn diagnostic time silently.

9. **Get a second opinion when stuck.** Use the `second-opinion` skill to produce an assumption-free Codex briefing when 30+ min have passed without new evidence, when multiple hypotheses have been tested unsuccessfully, or before committing to a heavy fix path. Fresh eyes catch what momentum-anchored eyes miss.

## Remote Synthesis (Beelink)

SSH from Spark lands in Git Bash (MINGW64) on the Beelink. SmartHLS and Libero are accessible via wrapper scripts.
```bash
# Test SmartHLS from Spark:
ssh bee "cd ~/dev/projects/polarfire-hybrid-control && git pull && cd hls && shls sw_run"

# Trigger full Libero synthesis from Spark:
ssh bee "cd ~/dev/projects/polarfire-hybrid-control && git pull && libero SCRIPT:libero/scripts/04_synth_pnr.tcl"

# VectorBlox SDK (requires WSL):
ssh bee "wsl -d Ubuntu -u jason -- bash -c 'source ~/vbx-env/bin/activate && vnnx_compile -c V250 -t model.tflite -o model.vnnx'"
```

Beelink paths:
- Repo: ~/dev/projects/polarfire-hybrid-control/
- shls wrapper: ~/bin/shls → C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\bin\shls.bat
- libero wrapper: ~/bin/libero → C:\Microchip\Libero_SoC_2025.2\Libero_SoC\Designer\bin\libero

Rules:
- Never edit source on Beelink — Spark is source of truth
- Always git pull on Beelink before building
- Beelink pushes synthesis reports only (libero/reports/)

### Parallel synthesis / seed-sweep on Beelink

For multi-seed P&R sweeps, variance studies, or any audit that needs N independent placement runs against the same RTL+netlist baseline, **default to parallel execution on Beelink** and **never run them sequentially unless you've already proven parallel doesn't fit**. Beelink resource ceiling and a working pattern are documented at `libero/scripts/parallel/README.md`. Headlines:

- **Beelink resources** (verified 2026-05-03): 64 GB RAM (≥56 GB free pre-launch), 774 GB free disk on `C:`. Supports ≥4 concurrent Libero processes (~2 GB each in synth, peaks ~8 GB during P&R).
- **Synplify Pro license** is `INCREMENT synplifypro_actel ... uncounted` in `C:\FlexLM\License.dat` — unlimited concurrent seats. Same for `ACTEL_BASESOC` and `SmartHLS`.
- **One Libero project = one prjx lock**. To run N P&Rs in parallel you must clone the project to N independent directories. The project root is **583 MB** (Vectorblox+Icicle base design); 4 clones = ~2.4 GB.
- **The clone gotcha**: `MPFS_ICICLE_Vectorblox.prjx` hardcodes its absolute self-path (`KEY ProjectLocation "C:\Microchip\...\MPFS_ICICLE_Vectorblox"`) at line 35. Clones must rewrite this. Synth-stage report files (e.g. `synthesis/synlog/*_compiler.srr`) also embed absolute paths to the original install tree — re-running SYNTHESIZE in a clone doesn't always cleanly overwrite them, which can cause parallel Synplify launches from N clones to fail with `Error: Synthesis failed.` even with uncounted licenses.
- **Reliable parallel pattern (proven 2026-05-03 audit-006 §2)**: do ONE Synplify re-synth in a "master" clone, then `cp -r master/synthesis/* seed_N/synthesis/` and `cp -r master/component/* seed_N/component/` to each P&R clone (their `.prjx` self-path stays as the rewritten clone path), then run **PLACEROUTE + VERIFYTIMING only** in each P&R clone with `configure_tool -name {PLACEROUTE} -params [list "RANDOM_SEED:N"]`. This isolates the ~25 min Synplify step (1×) from the ~25 min P&R step (parallel ×N).
- **Tcl path syntax**: Libero in MSYS Git Bash needs Windows-style script paths — `libero "SCRIPT:~/foo.tcl"` works; `SCRIPT:~/foo.tcl` fails with `Parameter 'file' is missing or has invalid value`.
- **Seed knob — BROKEN IN BATCH TCL (audit-006 root-cause 2026-05-03)**: `configure_tool -name {PLACEROUTE} -params [list "RANDOM_SEED:N"]` from a Tcl script does **not** vary placement. The actual mechanism: Libero's batch PLACEROUTE invokes the built-in **Multi-Pass / Iterate Seeds** feature with auto-incremented seed index (next number after the project's existing `r{N}_s{M}.rpt` highest), and **terminates at iteration 1 if timing closes** (`Multi-Pass: Have met stopping criterion`). So all 3 clones with SEED 7/13/23 actually placed at "Seed Index 27" and stopped after the first iteration that met timing. The configure_tool seed value never reached the placer. Verified across 3 independent clones — all produced **bit-identical placement** (path 1/2/3 endpoints, delays, slacks match to 3 decimal places).
- **To actually get N seeds via Multi-Pass**: disable the early-stopping criterion. The relevant Tcl knob is `configure_tool -name {PLACEROUTE} -params [list "EFFORT_LEVEL:high" "MULTIPASS_RUNS:N" "STOP_ON_FIRST_PASS:false"]` (parameter names assumed — needs validation against Microchip Libero 2025.2 reference). Each iteration writes a separate timing rpt; collect them after PLACEROUTE returns. This is **deferred research** — none of those exact param names tested yet.
- **What is reliably variable across clones**: synth output (Synplify Pro is non-deterministic across days even with identical RTL+SDC+tool — the audit-006 re-synth produced sha256 `44917cd6` while the Apr-30 on-disk netlist was `ae51d60d`), tool effort levels, constraint variations. Use those as the variance dimension if you need a meaningful sweep.
- **What IS deterministic** (audit-006 confirmed positive finding): Libero Designer's PLACEROUTE is bit-identical across independent clones for fixed `(netlist, prjx-state, effective-seed)`. So clone-based replication is good for cross-clone audits and reproducibility checks even though the seed knob doesn't work.
- **`run_tool -name {SYNTHESIZE} -script {REPORT}`** is **invalid Tcl** — `-script` expects a Tcl filepath, not a built-in. The construct in legacy `04_synth_pnr.tcl` line 39 / `pnr_verify_only.tcl` is dead code; use plain `run_tool -name {SYNTHESIZE}`.
- **For variance sweeps, skip POWERANALYSIS and GENERATEPROGRAMMINGDATA** — only PLACEROUTE+VERIFYTIMING are needed for slack characterization. Saves ~5 min per clone.
- **Don't re-run SYNTHESIZE in each clone in parallel.** Synplify's startup races and the synth-stage absolute-path entanglement above will make some of them fail. Use the "1 master synth, N parallel P&Rs" pattern.

Reusable templates and a launcher under `libero/scripts/parallel/`. End-to-end wall time for a 4-clone sweep: synth ~25 min + parallel P&R ~25 min ≈ **~50 min total** (versus ~3 hr if run sequentially with re-synth per seed).

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
