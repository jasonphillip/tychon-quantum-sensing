# Discriminating Experiment Verdict — Gain-Fold Hypothesis

**Date**: 2026-04-29
**Branch**: decision-2-option-c @ ba573d6
**Result**: HYPOTHESIS CONFIRMED

## What was tested

Whether the post-Tasks-1+2 closure numbers (24.67% 4LUT, +1.269 ns
slack) reflected a real PID datapath or a constant-folded shell. The
post-integration hier-resources CSV showed `nv_pid_top_0` and
`watchdog_timer_0` completely absent from per-instance breakdown
(`pid_io_block_0` was present at 104 LUT / 171 DFF), suggesting
Synplify had collapsed the entire PID compute to zero despite Tasks 1+2
having freed `error[63:0]` and `u_AI_in[31:0]` from constant ties.

The hypothesis: the AXI4-target inputs of nv_pid_top (Kp, Ki, Kd,
out_min, out_max, inner_clamp_setpoint) were still tied to literal zero
via `axi4target_*_const_net_0` assignments, so every gain multiplier
constant-folded to zero, collapsing the entire datapath regardless of
the freed `error`/`u_AI_in` inputs.

## How tested

`libero/scripts/patch_smartdesign_axi_target_experiment.py` rewires 6
axi4target inputs from constants to non-constant FIC_0 master taps:

| axi4target signal | Pre | Post |
|---|---|---|
| awvalid | GND_net | FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID |
| wvalid | GND_net | FIC_0_PERIPHERALS_1_AXI4mslave0_WVALID |
| awaddr  | 6'h00 | FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[5:0] |
| wdata   | 64'h0 | FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA[63:0] |
| wstrb   | 8'h00 | 8'hFF (always strobe) |
| bready  | GND_net | 1'b1 |

Then re-synthesised (synth-only, no PLACEROUTE) and compared Synplify
resource counts to the prior runs.

## Results

| Metric | Pruned baseline | Tasks 1+2 only | + axi_target experiment | Δ vs Tasks 1+2 |
|---|---|---|---|---|
| Total LUTs | 48,038 | 48,192 | 50,367 | **+2,175 (+4.5%)** |
| CFG1 | 216 | 220 | 348 | +128 |
| CFG2 | 3,864 | 3,879 | 3,969 | +90 |
| CFG3 | 22,356 | 22,303 | 22,639 | +336 |
| CFG4 | 13,286 | 13,479 | 13,541 | +62 |
| CL279 reg pruning | — | 95 | 111 | +16 |
| CL168 prune | 1 | 0 | 0 | clean |

The +2,175 LUT delta is ~14× the +154 LUT delta produced by Tasks 1+2
alone. Sizing matches expected PID compute: 6 × ~17×17 multipliers
(Kp×error, Ki×integral, Kd×derivative, plus saturation/clamp paths) at
~289 LUTs each = ~1,700 LUTs, plus AXI4-target write-channel decode
(~100) plus restored integrator/state logic (~300) = ~2,100 LUTs.

## Implication

The published "Tasks-1+2 closure" numbers (`libero/reports/2026-04-29-pid-integrated/`)
do **not** represent a real PID datapath in the placed netlist. They
represent the integration shell — pid_io_block AXI4-Lite slave
register file (104 LUT / 171 DFF) plus a constant-folded nv_pid_top
that has been collapsed to a near-zero footprint. The audit gate
correctly verified structural reachability (CL168 = 0, modules in
synthesis source list), but structural reachability is not the same
as semantic preservation.

For Phase II, freeing `error`/`u_AI_in` is necessary but not
sufficient. The AXI4-target inputs must also see non-constant traffic.
Two options:

1. **Proper AXI4-Lite interconnect routing.** Route `nv_pid_top_0`'s
   AXI4 target into the FIC_0 AXI interconnect at a dedicated address
   slot. MSS firmware writes Kp/Ki/Kd via standard AXI4 to that slot.
   Substantial SmartDesign canvas work, but software-clean.
2. **Keep the FIC_0 master tap as test stimulus permanently.** The
   experiment patch already does this. Synthesis numbers are real;
   gain values are not software-addressable; runtime PID computes on
   whatever bits land in axi4target_wdata when AWVALID fires. Useful
   as a phase-bridge signoff state but not a deliverable end-state.

## Artifacts

- `MPFS_ICICLE_KIT_BASE_DESIGN.srr` — Synplify report from the experiment
- `MPFS_ICICLE_KIT_BASE_DESIGN.patched.v` — top-level Verilog with all
  3 patches applied (Tasks 1+2 + experiment)
