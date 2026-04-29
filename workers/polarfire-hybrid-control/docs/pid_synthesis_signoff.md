# PID Synthesis Signoff

This checklist separates three different claims that can otherwise be easy to
mix together in Libero/Synplify runs:

1. The PID RTL source was included in the synthesis project.
2. The PID instance was structurally reachable and not removed as a whole.
3. The PID datapath semantics survived constant propagation and bit-vector
   minimization.

Only the third claim is sufficient before publishing PID-in-loop resource,
timing, or power numbers.

## Required Evidence

For each candidate run, archive or record paths to these artifacts:

- Synplify `.srr` report from the run.
- `compile_netlist_hier_resources.csv` from the compile stage.
- P&R layout log only after the synthesis checks below pass.
- A short run manifest with git commit, branch, tool versions, applied patchers,
  and the exact script invoked.

## Hard Synthesis Gates

The run is not a valid PID-in-loop synthesis if any of these are true:

- Synplify emits `CL168` for `nv_pid_top_0`, `pid_io_block_0`, or any required
  integration instance.
- `compile_netlist_hier_resources.csv` does not contain `nv_pid_top_0`,
  `pid_io_block_0`, and `watchdog_timer_0` after the integration patchers are
  applied.
- `nv_pid_top_0` has near-zero hierarchy resources.
- Synplify removes PID state registers such as `nv_pid_top_pid_integral`,
  `nv_pid_top_pid_prev_error`, or `nv_pid_top_u_AI_latch`.
- Synplify removes PID multiplier instances because they do not drive other
  logic.
- Synplify removes PID RAM or accelerator state due to constant propagation.
- The watchdog timeout register is removed because it does not drive other
  logic.

`libero/scripts/audit_synthesis.sh` is the automated gate for these conditions.
Run it after `SYNTHESIZE` and before any P&R closure run.

## Port Binding Checklist

Before launching a long run, maintain a port table for `nv_pid_top_0` with one
row per input and output:

| Port group | Required source or consumer |
|---|---|
| `error[63:0]` | Runtime-variable register or external signal, not a literal constant |
| `u_AI_in[31:0]` | Runtime-variable register or CoreVectorBlox result path |
| `ai_watchdog_timeout` | Watchdog timeout state driven from a nonconstant heartbeat source |
| `Kp`, `Ki`, `Kd` | Runtime-writable control registers or simple inputs from a register block |
| `out_min`, `out_max` | Runtime-writable control registers or simple inputs from a register block |
| `inner_clamp_setpoint` | Runtime-writable control register or simple input from a register block |
| `actuator_out_write_data[31:0]` | Exact full-width consumer, preferably software-readable |
| `actuator_out_write_en` | Exact consumer or status/capture strobe, not only an OR reduction |

A one-bit OR tap can prove structural reachability, but it does not prove exact
datapath semantics. The preferred consumer is a full-width AXI-readable capture
register that firmware can poll.

## Recommended Corrective Architecture

Use one of these two paths for signoff-quality numbers:

1. Route the SmartHLS `axi_target` interface for `nv_pid_top_0` into FIC_0 as a
   real AXI4-Lite slave at a dedicated address slot.
2. Regenerate the HLS top with PID gains and limits as `simple` inputs, then
   drive those inputs from a real AXI4-Lite register block.

The second path is usually easier to audit because each PID control value has a
direct register source, and the full actuator output can be captured in the
same block.

## Run Manifest Template

```text
Run label:
Date/time:
Git branch:
Git commit:
Libero version:
Synplify version:
Project path:
Script invoked:
Patchers applied:
Synthesis report:
Hierarchy CSV:
P&R report paths:
Audit command:
Audit verdict:
Notes:
```
