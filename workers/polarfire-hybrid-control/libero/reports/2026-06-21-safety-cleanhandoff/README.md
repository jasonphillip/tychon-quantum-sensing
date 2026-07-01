# Safety Clean-Handoff Attempt - 2026-06-21

Remote clone:

```text
~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055
```

Result: attempted, not closure. This fresh clone was patched for
`WATCHDOG_TIMEOUT_CYCLES=125000`, and `build_two_slot_pnr_cleanhandoff.tcl` was
modified to run `SYNTHESIZE` first, then save, route, verify timing, generate
programming data, export `polarfire_hybrid_control_two_slot_safety`, close the
project, and exit.

Synplify completed logic synthesis with `exit status=0`, and the mapper report
contains `Mapper successful!`. After that, the headless Libero wrapper did not
return from `run_tool SYNTHESIZE`; there was no `STAGE_OK SYNTHESIZE`, no
`run_tool PLACEROUTE`, no safety `.job`, and no programming.

Key evidence:

- `final_capture.txt`: remote clone path, process check, patch proof lines,
  hashes, synthesis/map markers, remote output hashes, and export job state.
- `build_two_slot_pnr_cleanhandoff.tcl`: exact clean-handoff Tcl script.
- `libero_cleanhandoff.log`: headless Libero wrapper log, flat after project
  source loading while child synthesis completed in separate logs.
- `synplify.log`, `synplify_job.log`, `MPFS_ICICLE_KIT_BASE_DESIGN.srr`,
  `MPFS_ICICLE_KIT_BASE_DESIGN.srm`, and
  `MPFS_ICICLE_KIT_BASE_DESIGN_fpga_mapper.srr`: successful synthesis/map
  evidence.

The next FPGA step should avoid relying on Libero's headless `run_tool
SYNTHESIZE` return path. Good candidates are GUI/job-manager handoff, a Libero
batch mode option that avoids the detached Synplify handoff, or a script that
imports the completed Synplify `.vm` into a fresh Libero project state before
`PLACEROUTE`.
