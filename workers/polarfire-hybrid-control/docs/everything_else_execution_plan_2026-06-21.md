# Everything Else Execution Plan - 2026-06-21

## Purpose

This is the go-forward plan after the 2026-06-21 remediation pass. It covers
all remaining roadmap items from `docs/remediation_roadmap.md` using the current
repo state as ground truth:

- Done: #1 dashboard/claim cleanup, #3 resource table, #7 INT8-vs-float harness.
- Partial: #2 latency, #4 watchdog bitstream, #5 derivative-filter P&R, #6
  SmartPower, #10 NN certificate setup, #12 real-NV data hunt.
- Pending: #8 real-time loop closure, #9 ZOH/transport-delay margins, #11 plant
  identification, #13 environmental/flight qualification.
- Demo-positioning decision: see
  `docs/credible_demo_finish_criteria_2026-06-21.md`. The near-term finish line
  is a hardware-real hybrid control demo with an honest ~5% deployed INT8 NN
  assist and a verified sub-2 ms fabric watchdog, not a large ML improvement or
  an exact 1 ms watchdog requirement.

Current execution note, 2026-06-21T11:35-04:00:

- Phase 0 baseline/recovery evidence is captured in
  `libero/reports/2026-06-21-execution-baseline/`.
- A clean-handoff safety clone at
  `~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055`
  was patched for `WATCHDOG_TIMEOUT_CYCLES=125000`.
- Synplify logic synthesis completed and the mapper reported success. The
  headless Libero wrapper then failed to return from `run_tool SYNTHESIZE`: no
  `STAGE_OK SYNTHESIZE`, no `run_tool PLACEROUTE`, no safety `.job`, and no
  programming.
- A follow-on force-state probe showed `SYNTHESIZE`, `PLACEROUTE`,
  `VERIFYTIMING`, and `GENERATEPROGRAMMINGDATA` all report `Tool inputs are out
  of date`; `set_tool_state -state {StateSuccess}` fails as an unknown state.
- A broader state-value probe rejected numeric states `0..6` and obvious
  success names including `Success`, `Passed`, `StateSuccess`, and
  `Tool inputs are up to date`; only the existing out-of-date state string was
  accepted.
- A `run_synthesis -target` probe failed on encrypted VectorBlox VHDL compiler
  errors, so it is not a safe replacement for `run_tool SYNTHESIZE`.
- The earlier direct retry also reached `STAGE_OK PLACEROUTE`, then VERIFYTIMING
  hit repeated Ptolemi `not ROUTED_CONNECT` exceptions, so Ptolemi may still be
  the next blocker after the Libero/Synplify handoff is solved.
- A deliberately quarantined skip-timing export probe from that P&R state also
  failed: `GENERATEPROGRAMMINGDATA` emitted repeated `Incorrect XY loc`
  errors and was manually stopped. No safety job was exported.
- A clean `.vm` import probe at
  `~/libero_seedsweep/seed7_vbx201_v250_safety_vmimport_20260621_1128`
  succeeded at `import_files -verilog_netlist`, `organize_tool_files`, and
  `build_design_hierarchy`, but all downstream tool states still remained
  `Tool inputs are out of date`. No P&R/export ran and no safety job was
  exported.
- Latest attempt archived in
  `libero/reports/2026-06-21-safety-vmimport/`; related probes are in
  `libero/reports/2026-06-21-safety-export-unverified/`,
  `libero/reports/2026-06-21-safety-stateprobe/`,
  `libero/reports/2026-06-21-safety-runsynth/`,
  `libero/reports/2026-06-21-safety-force-state/`,
  `libero/reports/2026-06-21-safety-cleanhandoff/`, and
  `libero/reports/2026-06-21-safety-direct/`.

## Non-Negotiable Gates

- Never touch `0x60001000`.
- Current safe PID page is `0x60040000..0x60040fff`.
- M0 writes remain allowlisted only to limits/gains/start; actuator reads remain
  M1 `R_POST_CLAMP`.
- No persistent programming until the recovery record is complete:
  rollback hashes, exact rollback command, FlashPro scan visibility, current
  artifact identity, expected discriminator, and cold-cycle/post-program checks.
- Keep dashboard/report wording honest until each claim is proven:
  host-paced where host-paced, default/vectorless where SmartPower lacks VCD
  annotation, simulator-trained until real data passes fidelity.

## Target End State

The project is "everything else done" when the following are all true:

1. A watchdog bitstream exists with `WATCHDOG_TIMEOUT_CYCLES=250000`, timing
   closed, programmed only after recovery gates, and verified on silicon at or
   below 2 ms. A 1 ms image is nice-to-have, not the Phase-I demo gate.
2. Derivative-filter RTL is integrated through P&R with timing evidence.
3. Pure fabric/PID cycle latency and V250/loop latency evidence are recorded
   with clear method boundaries.
4. SmartPower uses nonzero workload VCD annotation, not default/vectorless
   activity.
5. The loop runs without host pacing, with V250 feedforward in-loop and watchdog
   not stuck in fallback.
6. ZOH/transport-delay margins are calculated from measured timing and an
   explicit plant assumption/model.
7. The deployed NN has a reproducible sector/Lipschitz certificate, at least as
   an NN-only bound first, then closed-loop once plant bounds exist.
8. A plant sector/model exists from real data or a clearly labeled validated sim.
9. Real NV ODMR data is either found or collected, checked against the simulator
   regime, and used for validation/fine-tune evidence.
10. Environmental/flight claims are either deferred honestly or supported by an
    interim bench thermal/rad-tolerance note; full qualification remains Phase II
    unless budget/customer demand changes.

## Phase 0 - Freeze Current Baseline

Goal: make the next risky build/programming pass reproducible.

Steps:

1. Re-run read-only kit sanity:
   ```bash
   ssh icicle 'cd /root/bringup && \
     /root/bringup/pid_ctl r 0x60040804 && \
     /root/bringup/pid_ctl r 0x60040854 && \
     timeout 15 ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx'
   ```
2. Re-run bee inventory:
   ```bash
   ssh bee 'git -C ~/dev/projects/polarfire-hybrid-control status --short'
   ssh bee 'find ~/libero_seedsweep/seed7_vbx201_v250/export -name "*.job" -print0 | xargs -0 sha256sum'
   ```
3. Re-run FlashPro scan only:
   ```bash
   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpExpress \
     SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/scripts/scan_chain.tcl" \
     LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/<date>-scan/scan.log"
   ```
4. Record the recovery command for resident idfix2 before any new program step.

Done when:

- Baseline evidence is copied into a dated bundle.
- No leftover `libero.exe`, `synplify`, or stale SmartPower processes are running.

## Phase 1 - One Clean Libero Evidence Build

Goal: avoid three separate rebuilds. Create one build variant that can close or
advance #2, #4, #5, and #6 without programming until all artifacts are reviewed.

Build contents:

- `WATCHDOG_TIMEOUT_CYCLES=250000` for the near-term sub-2 ms hardware target.
- Derivative-filter datapath included in the integrated two-slot build.
- Optional PID fabric latency counter:
  - latch cycles from M0 `acc_start` to actuator-valid/post-clamp latch;
  - expose read-only result through M1 CSR;
  - do not add any new M0 read dependency.
- Keep all current idfix2 address safety behavior.

Steps:

1. Start from a fresh clone of the known-good seed/build directory on bee.
2. Patch only the safety timeout, derivative-filter integration, and optional
   read-only M1 latency counter.
3. Add explicit Tcl `puts`/`flush stdout` before long Libero/Synplify/P&R calls.
4. Run synth/P&R/export from a fresh shell with process monitoring.
5. Avoid relying on headless Libero's broken `run_tool SYNTHESIZE` return path.
   Do not repeat the failed `set_tool_state`, `run_synthesis -target`, or clean
   `.vm` import probes unless new Microchip command evidence changes their
   semantics. Prefer GUI/job-manager visibility, a clean source-to-Libero-state
   rebuild, or fixing the routed DB/P&R issue from a fresh seed.
6. If the build hangs or Ptolemi fails again, preserve logs and stop only the
   clone's processes; document whether the failure is the Libero/Synplify
   handoff or VERIFYTIMING/Ptolemi.
7. If a `.job` exports, hash it and stop. Do not program yet.

Done when:

- Either a valid safety/probe `.job` exists with timing/resource reports, or the
  next Libero/P&R failure is documented with stronger logs than the 2026-06-21
  safety-cleanhandoff attempt.

## Phase 2 - Programming Gate And Silicon Validation

Goal: program only after the recovery drill is complete.

Pre-program checklist:

- Current resident job identity and rollback job hashes recorded.
- Exact rollback command recorded.
- FlashPro scan passes.
- New `.job` hash recorded.
- Expected discriminator listed:
  `csr_version`, V250 `out[0]`, M1 actuator tracking, watchdog trip timing, and
  optional fabric latency counter.

Post-program checks:

1. Cold power-cycle.
2. Verify V250:
   ```bash
   ssh icicle 'cd /root/bringup && timeout 20 ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx'
   ```
3. Verify CSR/version/watchdog raw:
   ```bash
   ssh icicle '/root/bringup/pid_ctl r 0x60040804; /root/bringup/pid_ctl r 0x60040854'
   ```
4. Verify actuator:
   ```bash
   python3 tools/rung_g_replay.py --host icicle --rows 5 --out /tmp/post_program_smoke --plot
   ```
5. Verify watchdog trips at or below 2 ms by stopping heartbeat/output-valid updates.
6. If the latency counter was added, record pure fabric cycles.

Done when:

- The new bitstream passes V250, CSR, actuator, clamp, and watchdog checks.
- Rollback path remains proven.

## Phase 3 - SmartPower Closure

Goal: replace default/vectorless power with real workload switching.

Current state:

- Explicit top `nv_pid_top_top` was attempted.
- SmartPower still produced default-equivalent values:
  Total `2622.855 mW`, Static `445.612 mW`, Dynamic `2177.243 mW`.
- No `Annotated Pins` evidence exists for the 2026-06-21 attempt.

Plan:

1. First try GUI-assisted hierarchy mapping:
   compare VCD scope `nv_pid_top_top` against the placed PID instance path inside
   `MPFS_ICICLE_KIT_BASE_DESIGN`.
2. If SmartPower cannot map standalone block VCD to the placed design, switch to
   a full-design or post-synthesis simulation VCD whose names match the netlist.
3. Make the verification fail loud if annotation is zero:
   grep/export `Annotated Pins`, `Unannotated`, and switching summaries into the
   artifact manifest.
4. Commit only a report with nonzero annotation as workload-driven.

Done when:

- Dated SmartPower bundle contains the VCD, import log, annotation percentage,
  `smartpower_workload.rpt`, and a manifest saying why it is workload-driven.

## Phase 4 - Real-Time Loop Closure

Goal: convert the demo from host-paced datapath into real-time control.

Plan:

1. Use a fabric replay source or MSS-side loop that does not depend on SSH per row.
2. Feed sensed/replayed error into PID without host CSR pacing.
3. Run V250 per sample or at a documented cadence; feed `output_valid`/feedforward
   into the controller.
4. Keep watchdog out of permanent fallback under nominal cadence.
5. Demonstrate host-detached behavior:
   start the loop, disconnect host control path, and confirm the actuator continues
   updating.

Done when:

- A silicon log shows loop cadence, V250 feedforward updates, actuator tracking,
  watchdog healthy state, and host-detached continuation.

## Phase 5 - Control And Safety Proof Stack

Goal: turn "bounded by design" into bounded-by-evidence.

Work that can start immediately:

1. Export the frozen deployed float model to ONNX.
2. Define the input domain from `production_50k_v2_aic` plus physical margins.
3. Run alpha,beta-CROWN/auto_LiRPA for output and local slope bounds.
4. Run LipSDP or QC/IQC tooling for a Lipschitz/sector bound.
5. Record a reproducible NN-only certificate first.

Work that depends on timing/plant:

1. Use measured loop period and transport delay from #2/#8.
2. Identify or assume a conservative plant sector.
3. Compute ZOH/discrete phase margin.
4. Combine plant + delay + NN bound in the Circle/IQC argument.

Done when:

- `docs/safety_architecture.md` includes a model hash, input domain, bound,
  tool version, reproducer command, plant assumption/model, and margin result.
- Dashboard/report language says "certified within <domain>" only if the full
  chain is complete.

## Phase 6 - Real NV Data And Plant Model

Goal: remove the biggest credibility gap: simulator-only data.

Parallel tracks:

1. Public dataset track:
   inspect supplementary data for the close-regime CLFL/CW-ODMR ensemble papers;
   search Zenodo/Figshare/OSF by exact title/author; reject datasets that are not
   ensemble CW/CLFL ODMR near the 20-70 uT regime unless a conversion is justified.
2. Borrow/collaboration track:
   ask a quantum-sensing lab or teaching-system owner for a small sweep set in
   the target regime.
3. Benchtop track:
   if no public/borrowed data appears, build or buy access to a simple ensemble
   CW-ODMR setup and collect the needed sweeps.

For any candidate dataset:

1. Record source/license/regime.
2. Run the existing PCA/sim-to-real fidelity check.
3. If fidelity fails, document the mismatch and update the simulator or reject
   the dataset.
4. If fidelity passes, create a small real validation/fine-tune split.
5. Use step/chirp data to identify the plant sector/model for #11.

Done when:

- A real-data bundle exists with raw data, source/license, fidelity result, and
  plant-ID traces or a clear reason why the data is validation-only.

## Phase 7 - Environmental/Flight Position

Goal: keep Phase I honest without starting a months-long qualification campaign.

Interim plan:

1. Write a short note that full thermal/vibe/radiation qualification is Phase II.
2. Cite the target device family's rad-tolerant positioning only as background,
   not as proof this bitstream/system is flight-qualified.
3. Run a cheap bench thermal sanity sweep if hardware access allows.

Full plan, only if customer/budget requires:

- Thermal chamber, vibration, TID, heavy-ion/SEE, board prep, mitigation plan,
  third-party test report.

Done when:

- Current docs stop at an honest interim claim, or a funded qualification plan
  exists with facility quotes and schedule.

## Recommended Order

1. Phase 0 baseline and recovery record.
2. Phase 1 clean Libero build: safety timeout + derivative filter + optional
   latency counter.
3. Phase 3 SmartPower mapping work in parallel while Libero builds run.
4. Phase 5 NN-only certificate in parallel; it does not need hardware.
5. Phase 6 public/borrowed real-data hunt in parallel; it is the long pole.
6. Phase 2 program/validate only after a valid `.job` and recovery gates.
7. Phase 4 real-time loop closure after the programmed safety/probe build is
   stable.
8. Phase 5 full control proof after loop timing and plant data exist.
9. Phase 7 interim environmental note; full qualification only if funded.

## One-Week Practical Sprint

Day 1:

- Reconfirm baseline, scan chain, hashes, and bee cleanliness.
- Prepare fresh safety/probe build clone with stronger logging.
- Start ONNX export/property setup for NN bound.

Day 2-3:

- Run clean Libero build with a bypass for headless `run_tool SYNTHESIZE`;
  preserve logs if handoff, VERIFYTIMING/Ptolemi, or export fails.
- GUI/SmartPower hierarchy check or full-design VCD decision.
- Continue dataset supplementary-data search.

Day 4:

- If `.job` exists, review recovery gate and decide whether to program.
- If no `.job`, debug exact Libero/Synplify hang point before more RTL changes.

Day 5:

- If programming is explicitly approved, program+cold-cycle+validate; otherwise
  complete the build-hang postmortem or stop at hashed `.job` evidence.
- Produce updated status table and next discriminator.

Parallel throughout:

- NN certificate tooling setup.
- Real-data lead inspection.
- Keep dashboard wording/status honest.
