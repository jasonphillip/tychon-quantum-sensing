# Remediation Progress Log - 2026-06-21

## Resume Point

- Goal: implement as much of `docs/remediation_roadmap.md` as possible, prioritizing dashboard/live-actuator honesty, measured evidence, low-risk bee/Libero extraction, ML accuracy honesty, and research notes.
- Revised demo-positioning decision: steer the near-term finish criteria toward
  hardware-real hybrid control with an honest ~5% deployed INT8 NN assist and a
  verified 2 ms fabric watchdog (`WATCHDOG_TIMEOUT_CYCLES=250000` at
  125 MHz), rather than exact 1 ms watchdog or a large ML-improvement claim.
  See `docs/credible_demo_finish_criteria_2026-06-21.md`.
- Current mode: autonomous implementation; do not wait for per-step approval unless a stop condition is hit.
- Stop conditions: kit unstable/bricked, FlashPro cannot be made visible for a required programming step, evidence contradicts idfix2/M0 safety assumptions, or a persistent programming step is not recoverable.
- Hard rule: never poke `0x60001000`; current two-slot PID lives at `0x60040000..0x60040fff`, with M0 gains/start at `0x60040000..0x600407ff` and M1 `pid_csr` at `0x60040800..0x60040fff`.
- Programming rule: do not program FPGA fabric/eNVM/sNVM/SPI/HSS/U-Boot/Linux until current and rollback `.job` files are hashed, exact rollback command is recorded, FlashPro/scan-chain visibility is verified, and a recovery point is captured.
- Git rule: no commits unless explicitly requested; preserve unrelated dirty/untracked work.

## Starting State

- Timestamp: 2026-06-21T08:36:57-04:00.
- FPGA repo: `~/projects/polarfire-hybrid-control`, branch `bringup/2026-06-17-two-slot-pid`.
- FPGA repo pre-existing untracked items include `docs/remediation_roadmap.md`, `docs/codex_next_session_max_throughput_prompt_2026-06-21.md`, and `sim/rung_g/*`.
- Dashboard repo: `~/projects/fpga-demo-dashboard`, branch `main...nas/main`, clean before edits.
- ML repo: `~/projects/odmr-edge-ml`, branch `feature/op-set-check-and-fcnnv2-docstring...origin/feature/op-set-check-and-fcnnv2-docstring`; pre-existing untracked vector-v1 files must not be touched.

## Evidence Log

Append raw commands and key outputs here as work proceeds.

### Startup Hardware Inventory - 2026-06-21

- CONFIRMED: `ssh icicle 'uptime; for u in /sys/class/uio/uio*; ...'` succeeded at 12:37 UTC-ish uptime output:
  - `uio2 vbx@60030000`
  - `uio3 pid@60001000` (overlay label stale; do not poke `0x60001000`)
- CONFIRMED: `ssh icicle 'cd /root/bringup && ./vbx_probe fcnn_v2_residual_dataset_a.vnnx && timeout 20 ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx'`
  - `RESULT: INFERENCE COMPLETED`
  - `error_val=0`
  - `out[0] ... -2.9506`
- CONFIRMED: `ssh icicle '/root/bringup/pid_ctl r 0x60040804; /root/bringup/pid_ctl r 0x60040844'`
  - `0x60040804 = 0x00010000`
  - initial `0x60040844 = 0x00000000`
- CONFIRMED: `python3 tools/rung_g_replay.py --host icicle --rows 5 --out /tmp/idfix2_smoke --plot`
  - completed without LAN loss
  - `/tmp/idfix2_smoke.csv` rows show nonzero real M1 `post_clamp_out` after M0 gain/start setup: `0.399994`, `0.381943`, `0.360153`, `0.335236`, `0.307739`
  - `axi_write_count` advanced `4, 8, 12, 16, 20`
  - watchdog bit was already set on all rows; post-smoke `0x60040854 = 0x00000011`, so dashboard/reporting must label watchdog as tripped/current demo-state, not ok
- CONFIRMED: bee reachable; job files found:
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_demo.job`
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_idfix.job`
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_idfix2.job`
  - `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_vbx201_v250.job`
  - `~/dev/projects/polarfire-hybrid-control/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job`

### Dashboard Verification - 2026-06-21

- CONFIRMED: dashboard frontend/backend checks passed after idfix2 LIVE edits:
  - `python3 -m compileall backend`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`
- CONFIRMED: `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1 ./run_demo.sh` served `http://localhost:8077`.
- CONFIRMED: LIVE mode status after `POST /api/mode {"mode":"LIVE"}`:
  - `online=true`
  - `csr_version=0x00010000`
  - `kit_bitstream=idfix2`
  - `m0_writes_enabled=true`
  - watchdog raw observed as `0x00000015` / timeout bit set
- CONFIRMED: `POST /api/v250/probe` in LIVE returned:
  - `RESULT=INFERENCE COMPLETED`
  - `error_val=0`
  - `out0=-2.9506`
  - `simulated=false`
- CONFIRMED: sequential LIVE stream command `curl -sN 'http://localhost:8077/api/telemetry/stream?rows=5&period=0'` produced nonzero M1 actuator samples after dashboard-internal idfix2 M0 smoke:
  - sample 0: `error_in=0.5`, `pid_only_out=0.399994`, `actuator_out=0.399994`, `axi_write_count=50`
  - sample 4: `error_in=0.590452`, `pid_only_out=0.472351`, `actuator_out=0.472351`, `axi_write_count=66`
  - `idfix2_smoke_note="idfix2 M0 smoke passed; post_clamp_out=0.199997"`
- CONFIRMED: invalid-host check `KIT_HOST=definitely-not-icicle KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1 ./run_demo.sh`, then LIVE status:
  - `online=false`
  - `error="bad read reply: ''"`
  - no server crash

### Demo Portability Prep - 2026-06-22

- CONFIRMED: copied the live Spark working tree for `~/projects/fpga-demo-dashboard`
  to the Mac at `~phillip/projects/fpga-demo-dashboard`. This was a working-tree sync
  rather than a normal Git clone because the dashboard repo has uncommitted demo changes that are not
  present in `nas/main`.
- CONFIRMED: the copied Mac tree includes the built frontend at `frontend/dist/index.html` and
  backend demo data including `backend/data/v250_pid_rows.csv`.
- CONFIRMED: Mac backend dependencies were installed into
  `~phillip/projects/fpga-demo-dashboard/.venv`.
- CONFIRMED: added dashboard backend dependency
  `eval_type_backport>=0.2.0; python_version < "3.10"` so the FastAPI/Pydantic app can run on the
  Mac's system Python 3.9 while using the dashboard's current `str | None` annotations.
- CONFIRMED: Mac local smoke with the FPGA unplugged passed:

```bash
cd ~phillip/projects/fpga-demo-dashboard
PORT=18077 KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1 KIT_HOST=icicle ./run_demo.sh
curl -fsS http://127.0.0.1:18077/api/health
```

Observed response:

```json
{"ok": true, "mode": "DRY-RUN"}
```

- CAVEAT: live FPGA paths were not tested in this prep step because the FPGA was not plugged in.
  The Mac still needs an `icicle` SSH alias or explicit `KIT_HOST=<travel-router FPGA IP>` once the
  FPGA is on the travel-router LAN.
- CONFIRMED: added a Mac repo-local `.git/info/exclude` entry for `CLAUDE.md` so the copied
  dashboard repo status matches Spark's global-ignore behavior without changing tracked source.

### Latency Evidence - 2026-06-21

- PARTIAL: created and updated `docs/latency_measured_2026-06-21.md`.
- CONFIRMED host-visible V250 helper timing:
  - `vnnx_smoke`: n=30, min 760.776 ms, median 761.767 ms, p99 762.981 ms
  - `vbx_probe`: n=20, min 765.995 ms, median 766.528 ms, p99 768.069 ms
- CONFIRMED host-visible PID/dashboard timing through persistent `pid_ctl repl`:
  - `acc_start + M1 post_clamp_out read`: n=120, min 1199.0 us, median 1901.4 us, p99 3461.6 us
  - dashboard-style two-compute sample: n=120, min 5537.5 us, median 9121.7 us, p99 12970.1 us
  - `tools/rung_g_replay.py --rows 120`: inter-sample median 10122.0 us, p99 15412.0 us
- CONFIRMED on-kit helper timing:
  - `vnnx_latency`: binary hash `a9752426ca834a2deee72bb0403c965958e4a0fa63c45c1d146ac6e86154f32c`; command `ssh icicle 'cd /root/bringup; timeout 30 ./vnnx_latency fcnn_v2_residual_dataset_a.vnnx 1000 20'`
  - `vnnx_latency` result: `rdcycle=0`, `rdtime=1`, 1 MHz timebase; total start+poll n=1000, min 31 us, median 32 us, p99 33 us, max 58 us; `error_val=0`, `out0=-2.950607`
  - `pid_latency`: binary hash `5e1485fa94c1ed7cf6fbdc346e36da59eda9e2707cbc1bdce3f02184b0127930`; command `ssh icicle 'cd /root/bringup; timeout 30 ./pid_latency 5000 100'`
  - `pid_latency` result: `rdcycle=0`, `rdtime=1`, 1 MHz timebase; M0 start pulse + M1 `post_clamp_out` read n=5000, min 3 us, median 4 us, p99 4 us, max 50 us; `csr_version=0x00010000`, `watchdog_raw=0x00000081`
  - artifacts: `libero/reports/2026-06-21-latency/`
- Caveat: Linux userspace `rdcycle` traps, so these are on-kit API/MMIO bounds rather than core cycle counts or pure fabric latency.

### V250-to-PID On-Kit Loop - 2026-06-21

- PARTIAL/CLOSED for the software bridge: added `firmware/linux/v250_pid_loop.c`, a Linux helper that runs V250 inference, dequantizes `out[0]`, writes M1 `u_ai`, pulses M0 `acc_start`, and streams M1 `post_clamp_out` plus watchdog status.
- CONFIRMED build/deploy:
  - original bee scratch build binary hash: `92834c95d50ac7de0805e57a45dfdc8d33a3e6d3d23be17302d0319a67883b0c`
  - per-row CSV loader binary hash before daemon mode: `87b03568c13a97a7494b35f115ddffe48a0d9e7ffd75f5f960444191cda3e4ed`
  - current daemon-capable binary hash: `a05172ed98b834ea3b31d3a64ee1fbbd3ea33e7f9a9dfbd8329ddd7cc6921b43`
  - deployed row CSV hash: `060d91f883e698c3415c27971b710ae20e82ccbe48bdac2244e8a5f59eda809c`
  - deployed target: `/root/bringup/v250_pid_loop`
  - current source hash after daemon mode: `ba1fb14294a9eeaa45fb67d9e4595fdbbe105a3ff8dd491a45a4bf67c32efbb3`
- CONFIRMED first smoke:
  - before helper loop: watchdog CSR bit set (`0x60040854 = 0x0000009d`)
  - during helper loop: `watchdog_timeout=0`, `nn_out0=-2.950607300`, `u_ai=-0.046103239`, `axi_write_count` advanced
  - after helper stopped and 1 s elapsed: watchdog CSR timed out again (`0x60040854 = 0x0000009f`)
- IMPORTANT finding: M0 `inner_clamp_setpoint` at `0x60040020` must be initialized to `0.045`; otherwise the HLS sector clamp accepts a zero-width inner sector and clamps the AI term to zero. After initializing it, dashboard-shaped rows showed actual V250 assist:
  - row 0: `pid_only_out=0.160000`, `nn_u_ai=-0.046103`, `actuator_out=0.113892`, `watchdog_timeout=0`
  - row 4: `pid_only_out=0.163200`, `nn_u_ai=-0.046103`, `actuator_out=0.117096`, `watchdog_timeout=0`
- CONFIRMED dashboard integration in `~/projects/fpga-demo-dashboard`:
  - added `NN: V250 loop` telemetry mode
  - `curl -sN 'http://localhost:8077/api/telemetry/stream?rows=5&period=0&nn=v250-loop&stunt=none'` returned `PID_NN` rows with watchdog clear and actuator below PID-only
  - follow-up per-row ODMR run: `dashboard_v250_loop_odmr_stream_120.sse` captured 120 rows, watchdog unique `[0]`, mode unique `[PID_NN]`, `nn_u_ai` min/max `-0.045746/-0.035739`, mean `|actuator_out - pid_only_out|=0.03888945`
  - daemon API run: `dashboard_v250_loop_daemon_api.log` captured `POST /api/v250-loop/start`, row advance `105 -> 370 -> 669`, watchdog clear, `idfix2_smoke_ok=true`, and `POST /api/v250-loop/stop` with `stopped=true`
  - frontend `npm run typecheck` and `npm run build` passed after the change
- Evidence doc: `docs/v250_pid_loop_2026-06-21.md`.
- Artifact bundle: `libero/reports/2026-06-21-v250-pid-loop/`.
- Caveat: per-row held-out ODMR CSV input loading and dashboard-controlled userspace daemon mode now work; FPGA-resident/live-sensor autonomous operation remains pending.

### Bee / Libero Evidence - 2026-06-21

- CONFIRMED job hashes from bee:
  - `polarfire_hybrid_control_two_slot_demo.job`: `a5550f9e486e19f127aad78e97e06e0839d359c91028d4bcd21bb32b98f5b367`
  - `polarfire_hybrid_control_two_slot_idfix.job`: `7907a83f9fc6e99ca25ebc3c389c802d6d07e42b71403767ee644103783dff6e`
  - `polarfire_hybrid_control_two_slot_idfix2.job`: `39c8bcf2665ce8b79bcc2abb552ddd2b7b703729d50876744c2cb63c82ca230b`
  - `polarfire_hybrid_control_vbx201_v250.job`: `4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e`
- CONFIRMED read-only FPExpress scan:
  - artifact: `libero/reports/2026-06-21-scan/scan.log`
  - Embedded FP6 `F31E000A`, version `EF9B`
  - Device IDCODE `1F81A1CF`, part `MPFS250(T|TS|TL|TLS|TC)`
  - `Scan and Check Chain PASSED`
- CONFIRMED resource artifact copied:
  - `libero/reports/2026-06-21-idfix2-resource/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt`
  - package `FCVG484`, device `MPFS250T`
  - resource table: 67,811 4LUT (26.68%), 66,473 DFF (26.15%), 419 uSRAM (17.81%), 113 LSRAM (13.92%), 109 Math (13.90%)
- PARTIAL/DEFERRED:
  - #4 1 ms watchdog build was attempted in a cloned seed only, not completed/programmed:
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_20260621`
    - patched clone proof lines: `WATCHDOG_TIMEOUT_CYCLES(125000)` in `component/work/FIC_0_PERIPHERALS/FIC_0_PERIPHERALS.v`; `WATCHDOG_TIMEOUT_CYCLES = 125_000` in `hdl/pid_subsystem.v`; safety export job name `polarfire_hybrid_control_two_slot_safety`
    - Libero/Synplify entered map setup and then stopped making progress; stopped only the cloned run. No safety `.job` was exported and no programming was performed.
    - artifacts: `libero/reports/2026-06-21-safety-build/`
  - #4 safety retry was repeated from a fresh cloned seed with stronger proof/stall capture:
    - baseline/recovery bundle: `libero/reports/2026-06-21-execution-baseline/`
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_retry_20260621_1015`
    - patched proof lines captured `WATCHDOG_TIMEOUT_CYCLES = 125_000`, `.WATCHDOG_TIMEOUT_CYCLES(125000)`, and safety export job name `polarfire_hybrid_control_two_slot_safety`
    - synthesis advanced through compiler and premap, then stopped advancing after `Running: fpga_mapper (Map & Optimize)`; logs were flat from `2026-06-21 10:17:40 -0400` through final capture at `2026-06-21T10:21:48-04:00`
    - stopped only the retry run's `libero`/`synbatch`/`synplify_pro` processes; post-stop process check showed no remaining matching entries
    - no P&R, no exported safety `.job`, and no programming
    - artifacts: `libero/reports/2026-06-21-safety-retry/`
  - #4 safety-direct retry corrected the earlier mapper-stall interpretation:
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_direct_20260621_1025`
    - patched proof lines captured `WATCHDOG_TIMEOUT_CYCLES = 125_000`, `.WATCHDOG_TIMEOUT_CYCLES(125000)`, and safety export job name `polarfire_hybrid_control_two_slot_safety`
    - Synplify logic synthesis completed with `exit status=0`; mapper report says `Mapper successful!`
    - Libero synth wrapper did not return to a clean saved-project handoff after the successful Synplify/map evidence was captured, so only the clone's run was stopped
    - P&R/export attempt reached `==> STAGE_OK PLACEROUTE`, then VERIFYTIMING hit repeated Ptolemi `not ROUTED_CONNECT` exceptions
    - export directory still contained only the four original jobs; no `*safety*` `.job` was exported and no programming was performed
    - artifacts: `libero/reports/2026-06-21-safety-direct/`
  - #4 clean-handoff retry narrowed the current Libero blocker:
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055`
    - `build_two_slot_pnr_cleanhandoff.tcl` ran `SYNTHESIZE` first, then was supposed to save, route, verify timing, generate programming data, export `polarfire_hybrid_control_two_slot_safety`, close, and exit
    - Synplify logic synthesis completed with `exit status=0`; mapper report says `Mapper successful!`
    - after Synplify exited, the headless Libero wrapper did not return from `run_tool SYNTHESIZE`: no `STAGE_OK SYNTHESIZE`, no `run_tool PLACEROUTE`, no safety `.job`
    - stopped only the clone's remaining `libero` process; post-stop process check showed no remaining matching entries
    - no programming was performed
    - artifacts: `libero/reports/2026-06-21-safety-cleanhandoff/`
  - #4 force-state probe tested one bypass idea and failed safely:
    - same remote clone as clean-handoff
    - Libero reported `SYNTHESIZE`, `PLACEROUTE`, `VERIFYTIMING`, and `GENERATEPROGRAMMINGDATA` as `Tool inputs are out of date`
    - `set_tool_state -name {SYNTHESIZE} -state {StateSuccess}` failed with `Unkown state StateSuccess`; no P&R stage ran
    - no safety `.job` and no programming
    - artifacts: `libero/reports/2026-06-21-safety-force-state/`
  - #4 state-value probe tested the broader `set_tool_state` bypass and failed safely:
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_stateprobe_20260621_1117`
    - Libero rejected numeric states `0..6` and obvious success names including `Success`, `Passed`, `StateSuccess`, and `Tool inputs are up to date`
    - only the existing `Tool inputs are out of date` string was accepted
    - conclusion: no confirmed Tcl success-state bypass; do not use direct XML state edits as valid build evidence
    - artifacts: `libero/reports/2026-06-21-safety-stateprobe/`
  - #4 `run_synthesis -target` probe tested another synthesis-handoff route and failed safely:
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_runsynth_20260621_1118`
    - `run_synthesis -target .../synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.vm` started Synplify Pro ME and failed on encrypted VectorBlox VHDL compiler errors such as `No identifier "width_a" in scope`; P&R/export did not run
    - conclusion: `run_synthesis -target` is not a safe replacement for the observed `run_tool SYNTHESIZE` path in this project
    - artifacts: `libero/reports/2026-06-21-safety-runsynth/`
  - #4 unverified-export probe tested whether the safety-direct P&R database could at least produce a quarantined job and failed safely:
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_export_unverified_20260621_1120`
    - script intentionally skipped timing, then ran `GENERATEPROGRAMMINGDATA`
    - Libero warned that array data was being generated without all IOs assigned/locked and then emitted a flood of `Incorrect XY loc (384434489, 32766)` errors
    - the runaway failure was manually interrupted; remaining `libero` process was stopped; post-stop process check was clean
    - no quarantined safety job, no verified safety job, and no programming
    - artifacts: `libero/reports/2026-06-21-safety-export-unverified/`
  - #4 clean `.vm` import probe tested whether the completed safety-clone Synplify netlist could be reintroduced to Libero as downstream P&R input and failed safely:
    - remote clone: `~/libero_seedsweep/seed7_vbx201_v250_safety_vmimport_20260621_1128`
    - `import_files -verilog_netlist`, `organize_tool_files` for `PLACEROUTE`/`VERIFYTIMING`, and `build_design_hierarchy` all succeeded
    - before and after the import, `SYNTHESIZE`, `PLACEROUTE`, `VERIFYTIMING`, `GENERATEPROGRAMMINGDATA`, and `EXPORTPROGRAMMINGJOB` all remained `Tool inputs are out of date`
    - VM hash captured: `c53c14125134a9b9a2c1c230b82542eaba9a58e160f6fc81fbfae5cd7eb7e664`
    - no P&R, no exported safety `.job`, no safety-job search hits, and no programming
    - artifacts: `libero/reports/2026-06-21-safety-vmimport/`
  - #5 derivative filter remains HLS-complete but integrated P&R timing is deferred.
  - #6 SmartPower remains partial:
    - patched `libero/scripts/05_smartpower_workload*.tcl` to pass a dated report tag and call `smartpower_import_vcd` with explicit `-auto_detect_top_level_name {FALSE}`, `-top_level_name {nv_pid_top_top}`, and `-glitch_filtering {auto}`.
    - remote top-level rerun command launched on bee against the reference-design project; streamed log froze during project source loading, but SmartPower later left a small report directory.

### 2 ms Watchdog Build, Program, and Post-Program Checks - 2026-06-21

- CONFIRMED build/export artifact: `libero/reports/2026-06-21-watchdog-2ms/`.
- Remote clone: `~/libero_seedsweep/seed7_vbx201_v250_2ms_20260621_160037`.
- Patched watchdog target: `WATCHDOG_TIMEOUT_CYCLES=250000` in source HDL, HLS config, and SmartDesign generated FIC wrapper.
- Libero no-save flow results:
  - `STAGE_OK SYNTHESIZE`
  - `STAGE_OK PLACEROUTE`
  - `STAGE_OK VERIFYTIMING`
  - `STAGE_OK GENERATEPROGRAMMINGDATA`
  - `EXPORT_OK polarfire_hybrid_control_two_slot_2ms`
  - worst setup slack `1.006 ns`; min/hold report had positive slack.
- New job hash:
  - `7956a169d4b1c6f44fce1aee907dc416b039ce16ac532f46b4e1d7e53d68969a  polarfire_hybrid_control_two_slot_2ms.job`
- Rollback idfix2 job hash:
  - `39c8bcf2665ce8b79bcc2abb552ddd2b7b703729d50876744c2cb63c82ca230b  polarfire_hybrid_control_two_slot_idfix2.job`
- Recovery record and exact rollback command: `libero/reports/2026-06-21-watchdog-2ms/RECOVERY_RECORD.md`.
- Pre-program FlashPro scan:
  - artifact: `scan_preprogram_2ms.log`
  - embedded FP6 `F31E000A`
  - IDCODE `1F81A1CF`
  - `Scan and Check Chain PASSED`
- PROGRAM:
  - command script: `program_job_2ms.tcl`
  - log: `program_2ms.log`
  - result: `PROGRAM PASS - 2 ms watchdog image`; `Chain programming PASSED`
  - export/program digests include Fabric `fdb9ca8fe9ce93a8fa5858e45513eca9a56c4cd362adbded87432086b83b0f02` and sNVM `c011b109e3879c06a0abcd593ac8b9ef014b1f12a5d99e91780d834b2e12349c`.
- Post-program checks:
  - `dashboard_status_post_program.json`: LIVE, `csr_version=0x00010000`, watchdog timed out when V250 loop idle.
  - `dashboard_v250_probe_post_program.json`: `INFERENCE COMPLETED`, `error_val=0`, `out0=-2.9506`.
  - `dashboard_live_stream_5_post_program.sse`: guarded idfix2 M0 writes/start pulses and M1 actuator reads produced nonzero actuator values.
  - `dashboard_loop_start_post_program.json` and `dashboard_loop_status_post_program.json`: persistent V250 loop running, watchdog clear, live `u_ai` and `post_clamp` values.
  - `dashboard_loop_stop_post_program.json`: loop stopped and watchdog timed out again.
- Caveat: a physical cold power-cycle remains a recommended operator check, but was not required for the captured post-program V250 probe and dashboard loop checks.
    - report summary matched the previous default/vectorless result exactly: Total `2622.855 mW`, Static `445.612 mW`, Dynamic `2177.243 mW`.
    - no `verifypower.log` or `Annotated Pins` result was produced for this attempt; no nonzero VCD annotation evidence exists.
    - artifact: `libero/reports/2026-06-21-workload-power-topname/smartpower_topname.log`
    - result is ATTEMPTED, NOT CLOSURE; no nonzero VCD annotation was obtained.

### ML Evidence - 2026-06-21

- CONFIRMED: added and ran `~/projects/odmr-edge-ml/experiments/fcnn_v2_int8_float_equivalence.py`.
- Artifacts:
  - `~/projects/odmr-edge-ml/experiments/fcnn_v2_int8_float_equivalence_2026-06-21.json`
  - `~/projects/odmr-edge-ml/experiments/fcnn_v2_int8_float_equivalence_2026-06-21.md`
- Dataset: `~/projects/tychon-shared-data/production_50k_v2_aic`, split `test`, n=5000.
- CONFIRMED results:
  - float-vs-INT8 delta MAE `0.0346 uT`, RMSE `0.0452 uT`, max abs `0.7033 uT`
  - INT8 output saturation fraction `0.0012`
  - float clamped reduction vs PID `4.97%`
  - deployed INT8 clamped reduction vs PID `4.90%`
- Claim update: use "deployed INT8 model gives about 5% reduction"; do not use "bit-exact INT8 equivalence".

### Research Evidence - 2026-06-21

- PARTIAL: created `docs/nn_sector_certificate_plan_2026-06-21.md`.
  - Tool leads checked: alpha,beta-CROWN, auto_LiRPA, LipSDP, Marabou.
  - Local corpus leads: Khalil/Circle-Popov, strengthened Circle/Popov for ReLU feedback, Zames-Falb/IQC NN nonlinearities, and a recent local-sector-bound Lur'e/FFNN paper.
  - No certificate was produced; #10 still depends on a frozen model property plus #11 plant sector/model.
- PARTIAL: created `docs/real_nv_dataset_hunt_2026-06-21.md`.
  - Local corpus path corrected to `~/.corpus/...`.
  - Found close-regime ensemble CW/CLFL ODMR literature leads, including TFM dynamic range near 50 uT and 46 uT tracking examples.
  - No confirmed downloadable 20-70 uT ensemble CW-ODMR spectra dataset was found.
- PARTIAL: created `docs/remediation_status_2026-06-21.md` as the consolidated closeout/status report.

## Roadmap Status

| # | Item | Status | Artifact(s) |
|---|------|--------|-------------|
| 1 | Dashboard and overclaim cleanup | done | dashboard repo edits; idfix2 smoke: `/tmp/idfix2_smoke.csv`; LIVE curl verification above |
| 2 | Measured latency | partial | `docs/latency_measured_2026-06-21.md`; on-kit API/MMIO helper bounds captured, pure cycle/fabric latency still pending |
| 3 | Post-layout resource table | done | `libero/reports/2026-06-21-idfix2-resource/` |
| 4 | Sub-2 ms watchdog bitstream | done | `libero/reports/2026-06-21-watchdog-2ms/`; `WATCHDOG_TIMEOUT_CYCLES=250000`, timing met, job exported, pre-program scan passed, PROGRAM passed, post-program V250/CSR/actuator/watchdog checks captured |
| 5 | Derivative-filter P&R integration | partial | HLS complete in existing docs; integrated P&R deferred |
| 6 | Workload-driven SmartPower | partial | explicit-top VCD import script patched; rerun produced default-equivalent report but no annotation evidence; still no workload-annotated number |
| 7 | INT8-vs-float harness | done | `odmr-edge-ml/experiments/fcnn_v2_int8_float_equivalence_2026-06-21.{json,md}` |
| 8 | Real-time fabric loop closure | partial | `firmware/linux/v250_pid_loop.c`; `docs/v250_pid_loop_2026-06-21.md`; kit-side V250->u_ai->PID helper works with per-row held-out ODMR CSV input and persistent dashboard-controlled userspace daemon mode; FPGA-resident/live-sensor loop remains pending |
| 9 | ZOH/transport delay margins | pending | - |
| 10 | NN sector/Lipschitz certificate | partial | `docs/nn_sector_certificate_plan_2026-06-21.md` |
| 11 | Plant-model identification | pending | - |
| 12 | Real NV data / sim-to-real | partial | `docs/real_nv_dataset_hunt_2026-06-21.md` |
| 13 | Environmental/flight qualification | pending | - |

## Next Action Queue

Detailed sequencing and gates: `docs/everything_else_execution_plan_2026-06-21.md`.

1. For SmartPower, verify whether `smartpower_import_vcd` can map standalone `nv_pid_top_top` VCD hierarchy into the placed design; if not, move to full-design/post-synthesis VCD or GUI-assisted hierarchy mapping.
2. Add a readable fabric cycle counter for pure PID latency and, if desired, a direct watchdog trip-latency helper; `rdcycle` is unavailable from current userspace.
3. Keep dashboard LIVE gated on `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1` and preserve the no-`0x60001000` rule.
4. Run a physical cold power-cycle check when convenient and re-run the captured post-program V250/CSR/loop checks.
