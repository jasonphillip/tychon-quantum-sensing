# Safety Retry Bundle - 2026-06-21

## Summary

This bundle records the isolated Libero/Synplify retry for a
`WATCHDOG_TIMEOUT_CYCLES=125000` safety-spec build.

Remote clone:

```text
~/libero_seedsweep/seed7_vbx201_v250_safety_retry_20260621_1015
```

Result: attempted, not a pass. The clone was patched correctly and synthesis
advanced through compile and premap, then stopped making progress after entering
`fpga_mapper`. The stalled run was stopped. No P&R run completed, no safety
`.job` was exported, and no programming was performed.

## Key Evidence

- `final_stall_capture.txt`: final timestamps, post-stop process check, proof
  lines, source hashes, and synthesis/report tails.
- `safety_synth_retry.log`: Libero wrapper output through source loading.
- `synplify.log`: Synplify run log showing compile, premap, and map entry.
- `synplify_job.log`: Synplify job log.
- `MPFS_ICICLE_KIT_BASE_DESIGN.srr`: synthesis report.
- `MPFS_ICICLE_KIT_BASE_DESIGN_cck.rpt`: constraint checker report.

## Patch Proof

The captured proof lines show:

- `hdl/pid_subsystem.v`: `WATCHDOG_TIMEOUT_CYCLES = 125_000`
- `hdl_two_slot/pid_subsystem.v`: `WATCHDOG_TIMEOUT_CYCLES = 125_000`
- `component/work/FIC_0_PERIPHERALS/FIC_0_PERIPHERALS.v`:
  `.WATCHDOG_TIMEOUT_CYCLES(125000)`
- `build_two_slot_pnr.tcl`: safety export name
  `polarfire_hybrid_control_two_slot_safety`

## Stop Reason

The final log timestamps stayed flat from `2026-06-21 10:17:40 -0400` through
the final capture at `2026-06-21T10:21:48-04:00`; the process check after stop
showed no remaining `libero`, `synbatch`, or `synplify_pro` entries.
