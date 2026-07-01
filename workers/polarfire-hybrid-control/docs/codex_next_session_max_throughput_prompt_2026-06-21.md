# Codex Next-Session Prompt: PolarFire Hybrid Control Max-Throughput Day

Copy/paste this into a fresh Codex session.

---

# LATEST CURRENT STATE, 2026-06-21T11:35-04:00

This prompt contains older startup context below. Treat this section as the
newest truth unless current-state inspection contradicts it.

- Dashboard/live-actuator honesty work is already implemented and verified in
  `~/projects/fpga-demo-dashboard`: idfix2 LIVE is gated by
  `KIT_BITSTREAM=idfix2` and `ALLOW_IDFIX2_M0=1`, guarded M0 writes mirror
  `tools/rung_g_replay.py`, actuator reads come from M1 `R_POST_CLAMP`, and
  invalid `KIT_HOST` reports offline without crashing.
- Latency helpers are already built/run: see
  `docs/latency_measured_2026-06-21.md` and
  `libero/reports/2026-06-21-latency/`.
- ML INT8-vs-float harness is already added/run in
  `~/projects/odmr-edge-ml`; deployed INT8 reduction is about
  4.90%, not 8.71%.
- Resource, scan, rollback-hash, and multiple safety-build evidence bundles
  already exist under `libero/reports/2026-06-21-*`.
- FPGA safety build status: `WATCHDOG_TIMEOUT_CYCLES=125000` reaches
  Synplify/map success in cloned builds, but no safety `.job` exists and no
  programming has been performed.
- Revised demo-positioning decision: the next target is a credible hardware-real
  demo with honest about-5% deployed INT8 NN assist and a verified sub-2 ms
  fabric watchdog (`WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz). Exact 1 ms is
  now nice-to-have, not the Phase-I credibility gate. See
  `docs/credible_demo_finish_criteria_2026-06-21.md`.
- Do not repeat these failed Libero probes without new evidence:
  `set_tool_state` success strings (`StateSuccess`, numeric states, etc.),
  `run_synthesis -target`, skip-timing export from the broken safety-direct
  P&R database, or clean `.vm` import into Libero state. Evidence:
  `libero/reports/2026-06-21-safety-stateprobe/`,
  `libero/reports/2026-06-21-safety-runsynth/`,
  `libero/reports/2026-06-21-safety-export-unverified/`, and
  `libero/reports/2026-06-21-safety-vmimport/`.
- Next best FPGA routes are GUI/job-manager handoff, a clean
  source-to-Libero-state rebuild, or fixing the routed DB/P&R flow from a clean
  seed.

# MISSION

Continue work in:

`~/projects/polarfire-hybrid-control`

Goal: knock out as many items as possible from:

- `docs/remediation_roadmap.md`
- `~/Desktop/Shared/fpga_demo/10_remediation_roadmap_2026-06-20.md`

This is not just dashboard work. The dashboard is a top priority, but the work spans the kit, bee/Libero/SmartHLS/FlashPro, spark1/ML, and report/documentation cleanup.

Use Codex-native workflow. Do not assume Claude-only features such as `/search-corpus`, Claude Plan Mode, Claude skills, or Claude memories. If the current Codex session has useful skills/tools, use them, but otherwise use the repo, local corpora, shell, web search when required, and the live machines.

Do not wait for per-step approval. Make a short execution plan, then execute autonomously. Stop only if an action is not recoverable, the kit becomes unstable/bricked, FlashPro cannot be made visible for a required programming step, or evidence contradicts the safety/recovery assumptions below.

# VERIFIED INVENTORY FROM CODEX, 2026-06-21

Local FPGA repo:

- Repo: `~/projects/polarfire-hybrid-control`
- Branch: `bringup/2026-06-17-two-slot-pid`
- Dirty/untracked at inventory time:
  - `docs/remediation_roadmap.md`
  - `sim/rung_g/dashboard/`
  - `sim/rung_g/rung_g_*_2026-06-19.*`
- Important docs read and reconciled:
  - `CLAUDE.md`
  - `README.md`
  - `docs/agent_ground_truth_contract.md`
  - `docs/skeptic_qa_honest_claims.md`
  - `docs/remediation_roadmap.md`
  - `docs/two_slot_handoff_2026-06-17.md`
  - `docs/two_slot_register_map_2026-06-17.md`

Dashboard repo:

- Repo: `~/projects/fpga-demo-dashboard`
- Branch/status: `main...nas/main`, clean at inventory time.
- Runs with `./run_demo.sh` on `http://localhost:8077`.
- Current dashboard code is stale relative to `idfix2`:
  - README/UI still say LIVE is M0-gated and actuator reads zero.
  - `backend/links.py` still refuses all M0 access.
  - `backend/controller.py` writes M1 shadow gains, not authoritative M0 gains.
  - `frontend/src/App.tsx` and `TelemetryPlot.tsx` still describe M0 as gated.
  - `backend/data/metrics.json` still reports `8.71` and "bit-exact" wording.
- Fix this using `tools/rung_g_replay.py` from the FPGA repo as the known-good idfix2 live-actuator reference.

Live kit:

- `ssh icicle` works over the currently available Ethernet route.
- Do not spend time on the travel-router/Mac path in this session. That will be done later.
- Read-only inventory command succeeded:
  - uptime around 9 min at inventory
  - `/sys/class/uio/uio2 = vbx@60030000`
  - `/sys/class/uio/uio3 = pid@60001000` (overlay label is stale; do not poke `0x60001000`)
  - `/root/bringup/pid_ctl r 0x60040804` returned `0x00010000`
  - `/root/bringup/pid_ctl r 0x60040844` returned `0x00000000` before any M0 gain/start setup
  - `vbx_probe fcnn_v2_residual_dataset_a.vnnx` returned `RESULT: INFERENCE COMPLETED`, `VER=0x20000000`, `error_val=0`
  - `vnnx_smoke fcnn_v2_residual_dataset_a.vnnx` returned `out[0]=-2.9506`
- Codex inventory did not perform M0 writes/reads. The docs and `tools/rung_g_replay.py` say current resident `idfix2` makes M0 safe and live; verify with a bounded smoke test before relying on dashboard M0 behavior.

Bee:

- `ssh bee` works.
- Bee repo at inventory time:
  - `~/dev/projects/polarfire-hybrid-control`
  - branch `bringup/2026-05-18-real-silicon...spark1/bringup/2026-05-18-real-silicon [behind 3]`
  - HEAD `f46bbea`
- Job files found on bee:
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_demo.job`
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_idfix.job`
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_idfix2.job`
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_vbx201_v250.job`
  - `~/dev/projects/polarfire-hybrid-control/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job`
- COM ports present: COM7, COM8, COM9, COM10. Prior docs say COM8 = HSS/MMUART0 and COM10 = Linux/MMUART1.
- FlashPro6 was not confirmed by Codex inventory. Verify with an FPExpress/scan-chain command before any programming.

Spark1:

- `ssh spark1` works.
- GPU visible as `NVIDIA GB10`.
- `~/projects/odmr-edge-ml` has untracked vector-v1 files. Do not overwrite unrelated work.
- `~/projects/fpga-demo-dashboard` and `~/projects/polarfire-hybrid-control` exist there too.

Other repos/corpora:

- Local repos found:
  - `~/projects/odmr-edge-ml`
  - `~/projects/nv-sensor-sim`
  - `~/projects/tychon-shared-data`
  - `~/projects/tychon-sbir`
  - `~/projects/tychon-verification-workbench`
- Local corpora found:
  - `~/.corpus/polarfire-control-corpus`
  - `~/.corpus/odmr-pnt-nv-docs`
  - `~/.corpus/pow-rf`
- Use `rg` over these corpora instead of Claude `/search-corpus`. Use web search for current papers/tools/datasets where the answer may have changed.

# GROUND TRUTH AND SAFETY RULES

Follow `docs/agent_ground_truth_contract.md`.

Label important claims:

- CONFIRMED: backed by live silicon, generated Libero artifacts, SDK source, or primary docs.
- HYPOTHESIS: plausible but unverified.
- FALSIFIED: contradicted by ground truth.
- STALE/RISKY: inherited from old docs/plans/transcripts.

Do not claim root cause, confirmed, or ruled out without raw evidence.

Hard hardware rules:

- Never poke `0x60001000`. On the current two-slot architecture it is DMA controller control, not PID.
- PID lives at SLAVE3:
  - M0 gains: `0x60040000..0x600407ff`
  - M1 `pid_csr`: `0x60040800..0x60040fff`
- Only `idfix2` is M0-safe for the live actuator path. Older `demo`, old `idfix`, `seed_7`, and V250-only rollbacks must not be treated as M0-safe unless reverified from raw evidence.
- Current resident is expected to be `idfix2`, job sha256 `39c8bcf2665ce8b79bcc2abb552ddd2b7b703729d50876744c2cb63c82ca230b`. Preserve this state.
- Before programming any FPGA fabric/eNVM/sNVM/SPI/HSS/U-Boot/Linux image:
  - capture recovery point and current status
  - hash the current and rollback `.job` files
  - record exact rollback command
  - verify FlashPro6/scan-chain visibility
  - after programming, cold power-cycle and reverify V250 + live actuator before continuing
- If a risky step is not recoverable to the current state, stop and ask.
- Do not use destructive git commands. Do not revert unrelated user/agent work.
- Commit only clean, scoped, verified changes if the session prompt explicitly asks you to commit. Commit messages must not mention AI tooling.

# STARTUP CHECKLIST

1. Inventory current state:

```bash
cd ~/projects/polarfire-hybrid-control
git status --short --branch
cd ~/projects/fpga-demo-dashboard
git status --short --branch
```

2. Confirm kit is reachable via current Ethernet route, not travel-router setup:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 icicle 'uptime; for u in /sys/class/uio/uio*; do printf "%s " "$u"; cat "$u/name" 2>/dev/null; done'
ssh -o BatchMode=yes -o ConnectTimeout=8 icicle 'cd /root/bringup && ./vbx_probe fcnn_v2_residual_dataset_a.vnnx && timeout 20 ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx'
ssh -o BatchMode=yes -o ConnectTimeout=8 icicle '/root/bringup/pid_ctl r 0x60040804; /root/bringup/pid_ctl r 0x60040844'
```

3. Before dashboard M0 changes, run one bounded idfix2 smoke test. This intentionally touches M0, so do it only after the V250/M1 checks above pass and you are prepared to power-cycle if the inherited state is wrong:

```bash
cd ~/projects/polarfire-hybrid-control
python3 tools/rung_g_replay.py --host icicle --rows 5 --out /tmp/idfix2_smoke --plot
```

Expected on `idfix2`: nonzero `pid_only_out`/`pidnn_out`, clean completion, `csr_version=0x00010000`, and no LAN loss.

4. Check bee before any build/programming:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 bee 'git -C ~/dev/projects/polarfire-hybrid-control status --short --branch; find ~/libero_seedsweep ~/dev/projects -maxdepth 5 -type f -name "*.job" 2>/dev/null | sed -n "1,80p"'
```

Then run the appropriate read-only FlashPro/FPExpress scan-chain command from the repo scripts. Do not program until scan-chain is verified and rollbacks are hashed.

# PRIORITY WORK TRACKS

Run independent tracks in parallel when safe.

## Track A: Dashboard plus overclaim cleanup (#1)

Goal: make `~/projects/fpga-demo-dashboard` honest and live for `idfix2`.

Do not work on the travel-router/Mac network path. Use the current route to `icicle`.

Implementation target:

- Update LIVE mode so it uses the real idfix2 live actuator flow:
  - set authoritative M0 gains/limits:
    - `R_OUT_MIN = 0x60040018`
    - `R_OUT_MAX = 0x6004001c`
    - `R_KP = 0x6004000c`
    - `R_KI = 0x60040010`
    - `R_KD = 0x60040014`
  - inject error through M1:
    - `R_ERROR_LOW = 0x60040810`
    - `R_ERROR_HIGH = 0x60040814`
    - `R_U_AI = 0x60040818`
  - pulse M0 `acc_start = 0x60040008`
  - read live actuator from M1 `post_clamp_out = 0x60040844`
- Use `tools/rung_g_replay.py` as the reference behavior. The dashboard backend should mirror that proven sequence rather than M1-shadow-only writes.
- Keep a safety guard, but make it idfix2-aware. Good options:
  - default `KIT_BITSTREAM=idfix2` / `ALLOW_IDFIX2_M0=1` after startup smoke passes
  - or require an env var to allow M0 in dashboard LIVE mode and fail loudly otherwise
- Fix stale UI/docs:
  - remove "M0-gated -> 0" language for idfix2
  - say LIVE is host-paced hardware datapath with injected error, not real-time closed loop
  - say V250 inference is live/probed, but per-row NN feedforward is still surrogate or constant unless a real per-row helper is implemented
  - keep "unplug/offline" behavior honest. If physical unplug is inconvenient, verify with a temporarily invalid `KIT_HOST`; travel-router unplug testing is later/out of scope.
- Fix overclaim numbers/wording:
  - `8.71%` -> about `5%` for deployed `fcnn_v2_residual_dataset_a`
  - "bit-exact INT8" -> "INT8 deployment; bit-exact runner reproducibility" if that exact narrower claim is still shown
  - "200 MHz" -> "PID fabric 125 MHz / V250 core 200 MHz"
  - "1 ms watchdog" -> "500 ms host-paced demo; sub-2 ms hardware target pending" until #4 is done
  - "closed-loop" -> "host-paced datapath with injected error" unless referring to software model only
  - remove/qualify "real NV data", "sim-to-real validated", and "verified safety"
- Update dashboard README and frontend/backend text to match.

Verification:

```bash
cd ~/projects/fpga-demo-dashboard
./run_demo.sh
curl -s http://localhost:8077/api/status
curl -s -X POST http://localhost:8077/api/mode -H 'content-type: application/json' -d '{"mode":"LIVE"}'
curl -s http://localhost:8077/api/status
curl -N 'http://localhost:8077/api/telemetry/stream?rows=5&period=0'
```

Open `http://localhost:8077` and verify LIVE shows genuine kit status. If Playwright/browser tools are available, take screenshots after DRY-RUN and LIVE verification.

Mirror overclaim fixes in relevant report docs, especially `tychon-sbir` final/report outlines if present. Avoid broad scans of unrelated exported personal data under `tychon-sbir`; focus on project docs and deliverables.

## Track B: Latency measurements (#2)

Goal: commit measured latency table for the real system.

Measure and document:

- V250 inference latency on kit via the documented VectorBlox path. Prefer a RISC-V helper with `rdcycle` around model start/poll over SSH timing. Report min/median/p99 over enough runs.
- Fabric PID compute latency. If no rebuild, measure pulse-start to read-actuator overhead and label it as host-visible bound. If rebuilding anyway, add/read a fabric cycle counter latched from `acc_start` to `actuator_out_write_en`.
- Host-paced loop period for current dashboard/rung_g path.

Expected artifact:

- `docs/latency_measured_2026-06-21.md` or similarly dated doc with methods, raw commands/logs, units, and caveats.

## Track C: Bee/Libero hardware evidence (#3, #4, #5, #6)

Prepare bee:

- Do not clobber bee build directories.
- Bring bee git checkout to the required branch only after checking for local changes.
- Preserve the Libero/P&R database and `.job` files.

#3 resource table:

- Extract real post-layout resource utilization for exact `idfix2` if P&R DB is intact.
- Commit/copy reports into `libero/reports/<dated-idfix2-resource>/`.
- Fix package-label wording: correct package is FCVG484 for Production MPFS250T.

#4 sub-2 ms watchdog:

- Build the revised watchdog target with `WATCHDOG_TIMEOUT_CYCLES = 250000` at 125 MHz.
- Fold #5 derivative-filter P&R integration into the same build if feasible.
- Program only after recovery capture, job hashes, FlashPro scan, and rollback command are recorded.
- After programming: cold power-cycle, then reverify:
  - `vbx_probe` returns `INFERENCE COMPLETED`
  - `vnnx_smoke` returns `out[0]=-2.9506`
  - live actuator tracks `Kp * error` and clamps
  - watchdog trips at or below 2 ms

#5 derivative filter:

- Capture integrated P&R timing evidence for filtered derivative datapath.
- Update `docs/derivative_filter_design.md` and/or `docs/safety_architecture.md` with measured integrated timing.

#6 workload-driven SmartPower:

- Fix the three staged gaps documented in `docs/workload_smartpower_2026-05-17.md`.
- Use representative ODMR/PID activity that actually drives nonzero switching.
- Generate VCD-driven SmartPower report and commit the dated report bundle.

## Track D: ML evidence and research (#7, #10, #12)

#7 INT8 vs float equivalence:

- Work in `~/projects/odmr-edge-ml`.
- Do not overwrite unrelated untracked vector-v1 files.
- Build an eval harness comparing float `.pt` and deployed INT8 `.tflite` on the held-out `production_50k_v2_aic` test split.
- Source the deployed about-5% claim from `experiments/phase_c_comparison_table.csv`:
  - `dataset_a_aic_test_reduction_pct = 4.97`
  - `val_mae_reduction_pct = 5.01`
  - `sweep_mae_reduction_pct = 3.74`
  - `adev_tau_2700_reduction_pct_direct = 4.82`
- Do not use `8.71%` except as the failed cascade/overclaim example from `exports/cascade_v1/cascade_eval_report.json`.

#10 NN sector/Lipschitz certificate:

- Start only after cheap dashboard/measurement tasks are moving.
- Use local corpora and current web search for tools/methods:
  - LipSDP
  - alpha,beta-CROWN
  - SDP/IQC/Lure sector-bound methods for ReLU networks
- Initial deliverable can be a researched, reproducible plan plus environment setup; a full certificate is a larger task.

#12 real NV data:

- Start dataset hunt in parallel; do not block cheap wins.
- Need regime-matched ensemble CW-ODMR, 20-70 uT longitudinal-ish, not just any NV dataset.
- Use local corpora plus web search. Record candidate datasets, regime fit/mismatch, license/access, and whether they can feed the existing PCA fidelity check.

# DASHBOARD ACCEPTANCE CRITERIA

Dashboard is "done enough today" when:

- `./run_demo.sh` serves `http://localhost:8077`.
- LIVE mode uses the current Ethernet route to `icicle`; no travel-router work.
- LIVE status goes offline if `KIT_HOST` is invalid/unreachable.
- LIVE shows:
  - real V250 probe success, `out[0] = -2.9506`
  - `csr_version = 0x00010000`
  - `axi_write_count` changes under streaming
  - nonzero real actuator values from `0x60040844` after M0 gains and `acc_start`
  - honest watchdog state
- The UI no longer says M0 is gated on `idfix2`.
- The UI/report wording no longer overclaims 8.71%, bit-exact INT8 equivalence, all-200-MHz PID, 1 ms demo watchdog, real-time closed-loop, real NV data, sim-to-real validation, or verified formal stability.

# REPORTING FORMAT

Keep a running progress log.

End with:

- Status table by roadmap item (#1-#13): done / partial / blocked.
- Artifact paths for every completed/partial item.
- Exact commands/logs for hardware claims.
- Remaining risks and next actions.
- Updated TRL read:
  - control electronics: TRL 4 defensible if scoped to FPGA control subsystem and backed by live silicon
  - integrated NV sensor -> ML -> real-time control system: TRL 3 until real sensor/data and real-time integrated loop exist

Do not bury blockers. If something is blocked, state the raw evidence and the next falsifier.
