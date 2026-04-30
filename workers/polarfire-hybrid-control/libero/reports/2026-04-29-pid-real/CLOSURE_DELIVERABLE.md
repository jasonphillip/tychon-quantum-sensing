# PolarFire Hybrid Control — Real PID-In-Loop Closure

**Date**: 2026-04-29
**Branch**: decision-2-option-c @ 7dba7a0
**Run**: r6_s25 (Run 6, Seed 24, single-seed closure)
**Status**: Full closure SUCCEEDED — SYNTHESIZE → PLACEROUTE → VERIFYTIMING → VERIFYPOWER

This is the first time this design has produced post-P&R numbers that
reflect the actual integrated PID compute datapath rather than a
constant-folded paper-shell.

## Headline numbers

### Timing (post-layout, multi-corner, slow_lv_ht)

| Clock domain | Period | Worst slack |
|---|---|---|
| FIC_0 PLL OUT0 (200 MHz internal / 125 MHz clock) | 8.000 ns | **+0.728 ns** |
| PLL OUT1 (125 MHz) | 8.000 ns | +1.829 ns |
| PLL OUT3 (50 MHz) | 20.000 ns | +1.177 ns |

### Resources (MPFS250T, post-Place-and-Route)

| Type | Used | Total | % |
|---|---|---|---|
| 4LUT | 65,834 | 254,196 | **25.90** |
| DFF | 66,713 | 254,196 | **26.24** |
| Logic Element | 82,102 | 254,196 | **32.30** |
| MACC blocks | (11+ used by PID multipliers) | — | — |

### Power (typical conditions, default toggle rates)

| Component | Power |
|---|---|
| **Total** | **2,692.88 mW** |
| Static | 445.61 mW (16.5%) |
| Dynamic | 2,247.27 mW (83.5%) |
| Rail VDD (1.050 V) | 2,244.88 mW (2,137.98 mA) |

### Jitter

| Source | Peak-peak |
|---|---|
| System (worst aggressor REF_CLK_50MHz) | 0.054 ns |
| Vectorblox PLL | 0.135 ns |
| 80 MHz clock divider | 0.600 ns |

## Structural verification — nv_pid_top is preserved

`compile_netlist_hier_resources.csv` shows the integrated PID is one of
the largest instances in the whole design:

| Rank by 4LUT | Instance | 4LUT | DFF |
|---|---|---|---|
| 1 | Vectorblox MSC_i_37 | 2,818 | — |
| 2 | Vectorblox MSC_i_391/MSC_i_392 | 2,420 | — |
| **3** | **nv_pid_top_0/.../nv_pid_top_inst** | **2,058** | **1,079** |
| ... | (Vectorblox internals) | ... | ... |

PID-related instances captured per-instance in the hier-CSV:
- `nv_pid_top_0/nv_pid_top_inst/nv_pid_top_inst/Primitives` — 2,058 LUTs / 1,079 DFFs (core compute)
- `nv_pid_top_0/axi4slv_inst/genAccelCtrl.accel_controller/Primitives` — 123 LUTs / 192 DFFs
- `nv_pid_top_0/axi4slv_inst/wr_controller/Primitives` — 209 LUTs / 98 DFFs
- 11+ `legup_mult_signed_*` instances — pipelined multipliers using **18×18 MACC blocks** (one MACC per multiplier)
- `pid_io_block_0/Primitives` — 146 LUTs / 205 DFFs (AXI4-Lite slave)
- `watchdog_timer_0/Primitives` — 26 LUTs / 20 DFFs (200 MHz × 200,000-cycle timeout)

## Comparison to prior closures

| Metric | Pruned baseline (r3_s22) | Tasks 1+2 paper-shell (r5_s24) | **Real PID-in-loop (r6_s25)** | Δ vs Tasks 1+2 |
|---|---|---|---|---|
| Worst slack (FIC_0 OUT0) | +1.215 ns | +1.269 ns | **+0.728 ns** | −541 ps tighter |
| 4LUT count | ~62,810 | 62,706 | **65,834** | +3,128 |
| 4LUT % | 24.71 | 24.67 | **25.90** | +1.23 pp |
| DFF % | ~25.0 | 25.24 | **26.24** | +1.00 pp |
| LE % | ~30.9 | 30.95 | **32.30** | +1.35 pp |
| Total Power | 2,672 mW | (incomplete) | 2,692.88 mW | — |

The slack tightening (−541 ps) and resource growth (+3,128 LUTs)
together confirm a real datapath was routed: more logic created more
critical paths, slack shrank from the prior paper-shell value as the
multiplier and integrator chains competed for routing.

CL168 prune count remained 0 throughout. Audit gate passed. nv_pid_top
moved from "absent from per-instance hier-CSV" (paper-shell) to
"3rd-largest instance in the whole design" (real PID).

## What landed in this run

Three patches stacked on the SmartDesign top:

1. `patch_smartdesign_top.py` (Task 1 + LED tap + WVALID fix)
   - pid_io_block_0 instantiated with 5×32-bit AXI4-Lite slave
   - error_const_net_0 / u_AI_in_const_net_0 driven by pid_io_block outputs
   - actuator_out_write_data/_en captured into pid_io_block
   - LED0 OR-tap for top-level observability (defeats CL168 prune cascade)
   - S_AXI_WVALID independently tapped (vs prior conflation with AWVALID)

2. `patch_smartdesign_watchdog.py` (Task 2)
   - watchdog_timer_0 instantiated with 200,000-cycle counter
   - timeout drives nv_pid_top_0.ai_watchdog_timeout (replacing GND_net)
   - ai_heartbeat from MSS_WRAPPER_1_GPIO_2_M2F_28 (test stimulus, Phase II
     swap to CoreVectorBlox output_valid pending sub-component canvas work)

3. `patch_smartdesign_axi_target_experiment.py`
   - axi4target_awvalid/wvalid → FIC_0 master AWVALID/WVALID
   - axi4target_awaddr → FIC_0 master AWADDR[5:0]
   - axi4target_wdata → FIC_0 master WDATA[63:0]
   - axi4target_wstrb → 8'hFF (always-strobe)
   - axi4target_bready → 1'b1 (always-ready)
   - This is the change that defeated the gain-fold and produced the
     above numbers; same FIC_0 master tap pattern as pid_io_block, not
     address-decoded for nv_pid_top's address slot — Phase II proper
     AXI4-Lite interconnect routing is the clean replacement.

## Phase II next steps

1. **Real AXI4-Lite interconnect routing for nv_pid_top's gain registers.**
   Replace the FIC_0 master tap with a dedicated AXI4-Lite slave slot at
   a stable base address so MSS firmware can program Kp/Ki/Kd via real
   AXI transactions. Substantial SmartDesign canvas work; software-clean.
2. **CoreVectorBlox output_valid wiring** for watchdog.ai_heartbeat.
   Requires patching Vectorblox_ss.v + FIC_0_PERIPHERALS.v sub-components
   to propagate the IP-level export up.
3. **Workload-driven SmartPower run** for accurate dynamic power.
   Current 2,692.88 mW reflects default toggle rates; a VCD-driven run
   with the actual PID activity profile will give better numbers.

## Reproduction

```bash
# On Spark, with Beelink reachable via `ssh bee`:
cd ~/projects/polarfire-hybrid-control
ssh bee "git pull --ff-only" # syncs the patcher scripts to the Beelink

# Apply all three patches to the SmartDesign top:
ssh bee "cp <REF>/component/work/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN.v.pre_pid_io.bak <REF>/.../MPFS_ICICLE_KIT_BASE_DESIGN.v"
ssh bee "cat <REF>/.../MPFS_ICICLE_KIT_BASE_DESIGN.v" > /tmp/work_top.v
python3 libero/scripts/patch_smartdesign_top.py /tmp/work_top.v
python3 libero/scripts/patch_smartdesign_watchdog.py /tmp/work_top.v
python3 libero/scripts/patch_smartdesign_axi_target_experiment.py /tmp/work_top.v
ssh bee "cat > <REF>/.../MPFS_ICICLE_KIT_BASE_DESIGN.v" < /tmp/work_top.v

# Run full closure with hang-watchdog:
ssh bee "bash ~/dev/projects/polarfire-hybrid-control/libero/scripts/closure_with_watchdog.sh"

# Extract reports back to Spark:
bash libero/scripts/extract_reports.sh 2026-04-29-pid-real
```

## Artifacts in this directory

- `MPFS_ICICLE_KIT_BASE_DESIGN.srr` — Synplify report (CL168=0, full netlist)
- `MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_hier_resources.csv` — per-instance LUT/DFF/MACC breakdown
- `MPFS_ICICLE_KIT_BASE_DESIGN_layout_log.log` — full P&R log including resource summary
- `MPFS_ICICLE_KIT_BASE_DESIGN_iteration_summary.rpt` — multi-pass placement summary
- `MPFS_ICICLE_KIT_BASE_DESIGN_timing_r6_s25.rpt` — full multi-corner timing
- `MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max/min_r6_s25.rpt` — corner-specific violations
- `MPFS_ICICLE_KIT_BASE_DESIGN_power_report.xml` — SmartPower analysis
- `smartpower.spw` — SmartPower binary database
- `place_and_route_jitter_report.txt` — P&R-stage jitter
- `timing_analysis_jitter_report.txt` — VERIFYTIMING-stage jitter
