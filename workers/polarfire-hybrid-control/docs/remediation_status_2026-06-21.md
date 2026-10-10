# Max-Throughput Remediation Status - 2026-06-21

## Executive Summary

This pass completed the highest-ROI cleanup: the dashboard LIVE path is now idfix2-aware and guarded, stale overclaims were removed from the dashboard surface, measured latency/resource/FlashPro evidence was captured, and the deployed INT8-vs-float harness was added and run.

Follow-on positioning decision: the near-term credible demo finish line is now "hardware-real hybrid control with an honest modest NN assist" plus a verified 2 ms fabric watchdog target (`WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz). The previous 1 ms build remains useful evidence/aspiration, but an exact 1 ms watchdog is no longer the Phase-I credibility gate. See `docs/credible_demo_finish_criteria_2026-06-21.md`.

An additional FPGA push on 2026-06-21 added on-kit V250/PID latency helpers, a V250-to-PID userspace loop helper, a per-row ODMR CSV input loader for that helper, persistent daemon mode plus dashboard start/stop/status controls, attempted cloned 1 ms watchdog safety builds, a completed 2 ms watchdog build/programming pass, and an attempted SmartPower explicit-VCD-top rerun. The helper measurements succeeded. The new `v250_pid_loop` helper runs V250 inference on the kit, optionally quantizes held-out ODMR rows into the V250 input buffer, dequantizes `out[0]`, writes M1 `u_ai`, pulses M0 `acc_start`, and streams or persists M1 `post_clamp_out`; after initializing M0 `inner_clamp_setpoint=0.045`, dashboard rows show the V250-derived correction in the actuator output with watchdog clear. The 1 ms safety attempts remain historical evidence of the failed stricter route. The revised `WATCHDOG_TIMEOUT_CYCLES=250000` image closed synthesis, P&R, VERIFYTIMING, programming-data generation, and FlashPro job export; rollback hashes, scan-chain visibility, and exact rollback commands were recorded before PROGRAM; FlashPro PROGRAM passed; post-program V250/CSR/actuator/watchdog checks passed. The SmartPower report remained default-equivalent with no annotation evidence.

Persistent programming was performed only for the dated 2 ms watchdog image. No writes were made to `0x60001000`.

2026-06-22 demo portability follow-up: the live Spark dashboard working tree was copied to the Mac
at `~phillip/projects/fpga-demo-dashboard`, backend dependencies were installed into its
local `.venv`, a Python 3.9 compatibility dependency was added, and a Mac-local `/api/health` smoke
passed in DRY-RUN mode. The FPGA was unplugged for this step, so Mac-to-FPGA LIVE validation still
requires the travel-router LAN and `KIT_HOST=<FPGA IP or alias>`.

## Roadmap Status

| # | Item | Status | Evidence / artifact |
|---|------|--------|---------------------|
| 1 | Dashboard and overclaim cleanup | DONE | `~/projects/fpga-demo-dashboard`; LIVE curl evidence in `docs/remediation_progress_2026-06-21.md` |
| 2 | Measured latency | PARTIAL | `docs/latency_measured_2026-06-21.md`; on-kit API/MMIO helper bounds captured, pure cycle/fabric latency still pending |
| 3 | Post-layout resource table | DONE | `libero/reports/2026-06-21-idfix2-resource/` |
| 4 | Sub-2 ms watchdog bitstream | DONE | `libero/reports/2026-06-21-watchdog-2ms/`; `WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz, timing met, job exported, pre-program scan passed, PROGRAM passed, V250 probe passed, guarded stream passed, and V250 loop clear/stop-trip behavior captured. Prior 1 ms attempts remain in the `2026-06-21-safety-*` bundles as historical evidence. |
| 5 | Derivative-filter P&R integration | PARTIAL | existing HLS evidence; integrated P&R deferred |
| 6 | Workload-driven SmartPower | PARTIAL | explicit-top VCD import script patched; rerun produced default-equivalent report but no annotation evidence; still no workload-annotated number |
| 7 | INT8-vs-float harness | DONE | `~/projects/odmr-edge-ml/experiments/fcnn_v2_int8_float_equivalence_2026-06-21.{json,md}` |
| 8 | Real-time fabric loop closure | PARTIAL | `firmware/linux/v250_pid_loop.c`; `docs/v250_pid_loop_2026-06-21.md`; kit-side V250->u_ai->PID helper works with per-row held-out ODMR CSV input and dashboard-controlled persistent daemon mode; FPGA-resident/live-sensor loop remains pending |
| 9 | ZOH/transport delay margins | PENDING | depends on #2/#8 timing |
| 10 | NN sector/Lipschitz certificate | PARTIAL | `docs/nn_sector_certificate_plan_2026-06-21.md` |
| 11 | Plant-model identification | PENDING | depends on rig/real trace or validated sim |
| 12 | Real NV data / sim-to-real | PARTIAL | `docs/real_nv_dataset_hunt_2026-06-21.md`; no confirmed regime-matched dataset |
| 13 | Environmental/flight qualification | PENDING | Phase II/deferred |

## Key Hardware Evidence

- Kit inventory: `ssh icicle 'uptime; for u in /sys/class/uio/uio*; do ...; done'`
  - `uio2 vbx@60030000`
  - `uio3 pid@60001000` label is stale; the safe idfix2 PID window used here is `0x60040000..0x60040fff`.
- V250 probe:
  - `ssh icicle 'cd /root/bringup && ./vbx_probe fcnn_v2_residual_dataset_a.vnnx && timeout 20 ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx'`
  - observed `RESULT: INFERENCE COMPLETED`, `error_val=0`, `out[0]=-2.9506`.
- CSR version:
  - `ssh icicle '/root/bringup/pid_ctl r 0x60040804'`
  - observed `0x00010000`.
- Bounded M0 smoke:
  - `python3 tools/rung_g_replay.py --host icicle --rows 5 --out /tmp/idfix2_smoke --plot`
  - observed nonzero M1 `post_clamp_out`: `0.399994`, `0.381943`, `0.360153`, `0.335236`, `0.307739`.
  - observed `axi_write_count`: `4`, `8`, `12`, `16`, `20`.
  - watchdog was already tripped/current demo-state: post-smoke `0x60040854 = 0x00000011`.

## Dashboard Verification

Commands run in `~/projects/fpga-demo-dashboard`:

```bash
python3 -m compileall backend
cd frontend && npm run typecheck
cd frontend && npm run build
KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1 ./run_demo.sh
```

LIVE checks:

```bash
curl -s -X POST http://localhost:8077/api/mode \
  -H 'content-type: application/json' \
  -d '{"mode":"LIVE"}'

curl -s -X POST http://localhost:8077/api/v250/probe

curl -sN 'http://localhost:8077/api/telemetry/stream?rows=5&period=0'
```

Confirmed LIVE stream used guarded M0 writes/start pulses and M1 `R_POST_CLAMP` actuator reads. Sequential samples included nonzero actuator values from `0.399994` to `0.472351`, and `axi_write_count` changed from `50` to `66`.

V250 loop dashboard check:

```bash
curl -sN 'http://localhost:8077/api/telemetry/stream?rows=5&period=0&nn=v250-loop&stunt=none'
```

Confirmed the dashboard can invoke the on-kit helper with per-row held-out ODMR CSV input. Representative rows had `watchdog_timeout=0`, `mode=PID_NN`, changing `nn_u_ai`, and actuator output shifted from PID-only (`pid_only_out=-0.456650`, `actuator_out=-0.496338` on row 0). A 120-row stream had watchdog unique `[0]`, mode unique `[PID_NN]`, `nn_u_ai` min/max `-0.045746/-0.035739`, and mean `|actuator_out - pid_only_out|=0.03888945`. The dashboard daemon API also started a persistent kit loop (`pid=1514`), observed row advance `105 -> 370 -> 669` with watchdog clear, marked `idfix2_smoke_ok=true`, and stopped the loop cleanly. This proves kit-side V250 output is reaching the PID actuator path once M0 `inner_clamp_setpoint` is initialized. Current limitation: this is Linux userspace control, not autonomous FPGA-resident wiring.

Offline/invalid-host check:

```bash
KIT_HOST=definitely-not-icicle KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1 ./run_demo.sh
```

Switching LIVE reported `online=false` with `bad read reply: ''` and did not crash.

## Bee / Libero Evidence

Rollback/job hashes from bee:

```text
a5550f9e486e19f127aad78e97e06e0839d359c91028d4bcd21bb32b98f5b367  polarfire_hybrid_control_two_slot_demo.job
7907a83f9fc6e99ca25ebc3c389c802d6d07e42b71403767ee644103783dff6e  polarfire_hybrid_control_two_slot_idfix.job
39c8bcf2665ce8b79bcc2abb552ddd2b7b703729d50876744c2cb63c82ca230b  polarfire_hybrid_control_two_slot_idfix2.job
4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e  polarfire_hybrid_control_vbx201_v250.job
```

FlashPro scan command run on bee:

```bash
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpExpress \
  SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/scripts/scan_chain.tcl" \
  LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-scan/scan.log"
```

Confirmed Embedded FP6 `F31E000A`, IDCODE `1F81A1CF`, part `MPFS250(T|TS|TL|TLS|TC)`, and `Scan and Check Chain PASSED`.

Rollback idfix2 recovery/program command recorded before the 2 ms PROGRAM action:

```bash
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
  SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/program_job_idfix2_rollback.tcl" \
  LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/rollback_idfix2_program.log"
```

2 ms PROGRAM result: FlashPro PROGRAM PASSED on `F31E000A` / `MPFS250T`; post-program dashboard captures show `csr_version=0x00010000`, V250 `out[0]=-2.9506`, nonzero guarded actuator telemetry, watchdog clear while the V250 loop runs, and watchdog timeout after the loop stops.

Safety-spec build attempts:

```text
First remote clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_20260621
Retry remote clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_retry_20260621_1015
Direct retry clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_direct_20260621_1025
Clean-handoff clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055
State-probe clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_stateprobe_20260621_1117
Run-synthesis clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_runsynth_20260621_1118
Export-unverified clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_export_unverified_20260621_1120
VM-import clone: ~/libero_seedsweep/seed7_vbx201_v250_safety_vmimport_20260621_1128
Patched timeout: WATCHDOG_TIMEOUT_CYCLES=125000
Status: ATTEMPTED, NOT A PASS. The latest clean-handoff retry completed
Synplify/map, then the headless Libero wrapper did not return from
run_tool SYNTHESIZE; no STAGE_OK SYNTHESIZE, no PLACEROUTE, and no safety
.job exported. A follow-on force-state probe showed all downstream tools still
reported "Tool inputs are out of date"; set_tool_state with StateSuccess failed
as an unknown state. A broader state-probe rejected numeric states 0..6 and
obvious success names. run_synthesis -target failed on encrypted VectorBlox VHDL.
An unverified export probe from the safety-direct P&R state failed in
GENERATEPROGRAMMINGDATA with repeated Incorrect XY loc errors and was stopped.
A clean .vm import probe succeeded at import/organize/build-hierarchy but still
left all downstream Libero tool states "Tool inputs are out of date."
Artifacts: libero/reports/2026-06-21-safety-build/
           libero/reports/2026-06-21-safety-retry/
           libero/reports/2026-06-21-safety-direct/
           libero/reports/2026-06-21-safety-cleanhandoff/
           libero/reports/2026-06-21-safety-force-state/
           libero/reports/2026-06-21-safety-stateprobe/
           libero/reports/2026-06-21-safety-runsynth/
           libero/reports/2026-06-21-safety-export-unverified/
           libero/reports/2026-06-21-safety-vmimport/
```

The clone proof lines captured in the manifests show the timeout edits in
`component/work/FIC_0_PERIPHERALS/FIC_0_PERIPHERALS.v`, `hdl/pid_subsystem.v`,
and the safety export job name in `build_two_slot_pnr.tcl`.

SmartPower explicit-top rerun:

```text
Patched import intent: smartpower_import_vcd -auto_detect_top_level_name {FALSE} -top_level_name {nv_pid_top_top}
Run log: libero/reports/2026-06-21-workload-power-topname/smartpower_topname.log
Report: Total 2622.855 mW, Static 445.612 mW, Dynamic 2177.243 mW
Status: ATTEMPTED, NOT CLOSURE. Report is default-equivalent and no Annotated Pins/nonzero VCD annotation result exists.
```

This leaves the earlier `Annotated Pins 0.00% / Unannotated 100.00%` finding as the current SmartPower truth.

## Latency Evidence

On-kit helper binaries were built on bee and copied to `/root/bringup` on the kit:

```text
a9752426ca834a2deee72bb0403c965958e4a0fa63c45c1d146ac6e86154f32c  vnnx_latency
5e1485fa94c1ed7cf6fbdc346e36da59eda9e2707cbc1bdce3f02184b0127930  pid_latency
```

Key measurements:

- `vnnx_latency`: `rdcycle=0`, `rdtime=1`, 1 MHz timebase; V250 start+poll n=1000, median `32 us`, p99 `33 us`, max `58 us`; `out0=-2.950607`.
- `pid_latency`: `rdcycle=0`, `rdtime=1`, 1 MHz timebase; M0 start pulse + M1 `post_clamp_out` read n=5000, median `4 us`, p99 `4 us`, max `50 us`; `csr_version=0x00010000`.
- `tools/rung_g_replay.py --rows 120`: host-paced inter-sample median `10122 us`, p99 `15412 us`.
- `v250_pid_loop`: dashboard-shaped rows stream in under 1 ms for a 5-row smoke with embedded input, the per-row ODMR CSV path streams 120 rows with watchdog clear, and persistent daemon mode keeps the loop running with a 5 ms inter-row sleep; per-row V250 start+poll is around `31-34 us` in the helper CSV/state.

These are confirmed API/MMIO and host-visible bounds, not internal V250/fabric cycle counts.

## ML Evidence

Command run in `~/projects/odmr-edge-ml`:

```bash
python3 experiments/fcnn_v2_int8_float_equivalence.py
```

Result on `production_50k_v2_aic` test split, n=5000:

- float-vs-INT8 delta MAE: `0.0346 uT`
- RMSE: `0.0452 uT`
- max abs delta: `0.7033 uT`
- INT8 output saturation fraction: `0.0012`
- float clamped reduction vs PID: `4.97%`
- deployed INT8 clamped reduction vs PID: `4.90%`

Dashboard/report claim should be "about 5% deployed INT8 reduction," not "8.71%" and not "bit-exact INT8 equivalence."

## Remaining Risks

- #2 latency still lacks actual `rdcycle` V250 timing and pure fabric PID cycle timing because Linux userspace traps `rdcycle`.
- #5/#6 still require clean integration/report cycles. #4 is closed for the 2 ms acceptance target, but a tighter direct on-silicon microsecond trip measurement would require an additional helper or readable fabric counter.
- #8 is only partially closed: the kit-side helper proves V250 output can feed the PID path from per-row held-out ODMR CSV inputs, including dashboard-controlled daemon mode, but live sensor input or FPGA-resident wiring is still needed before claiming continuous autonomous hardware-only sensor-driven NN control.
- SmartPower is not workload-driven until VCD annotation is nonzero and tied to a representative switching workload; the 2026-06-21 explicit-top rerun did not provide annotation evidence.
- #10 cannot close without a model-bound artifact and a plant sector/model.
- #12 remains the largest credibility gap: no confirmed real, regime-matched ensemble CW-ODMR dataset yet.

## Next Actions

The detailed execution order is now captured in
`docs/everything_else_execution_plan_2026-06-21.md`.

1. Add a real live sensor/input transport or FPGA-resident wiring path if the demo needs hardware-only autonomous sensor-driven control; dashboard daemon mode is now available for the held-out ODMR row loop.
2. Add a readable fabric cycle counter or kernel/perf path for pure latency numbers; userspace `rdcycle` is unavailable on the current image.
3. Add a direct watchdog-trip timing helper or readable fabric counter if the demo needs measured microsecond trip latency beyond the verified `250000`-cycle bitstream/programming evidence.
4. Fix the SmartPower VCD activity import until annotation is nonzero; explicit `nv_pid_top_top` alone produced only a default-equivalent report.
5. Start #10 with ONNX export plus alpha,beta-CROWN/auto_LiRPA feasibility.
6. Continue #12 by checking supplementary data links for the close-regime CLFL/CW-ODMR ensemble papers.
