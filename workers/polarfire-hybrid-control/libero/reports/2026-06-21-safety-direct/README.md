# Safety-Direct Build Attempt - 2026-06-21

Remote clone:

```text
~/libero_seedsweep/seed7_vbx201_v250_safety_direct_20260621_1025
```

Result: attempted, not closure. The cloned design was patched for
`WATCHDOG_TIMEOUT_CYCLES=125000` and the safety export name
`polarfire_hybrid_control_two_slot_safety`. Synplify logic synthesis completed
and the mapper reported success. The Libero synth wrapper did not return to a
clean saved-project handoff, so the run was stopped after the successful
Synplify/map evidence was captured.

The follow-on P&R/export attempt reached `STAGE_OK PLACEROUTE`, then VERIFYTIMING
hit repeated Ptolemi `not ROUTED_CONNECT` exceptions. No new safety `.job` was
exported, and no FPGA programming was performed.

Key evidence:

- `final_capture.txt`: remote clone path, process check, patched-file proof
  lines, patched-file hashes, P&R markers, export job hashes, and safety-job
  search result.
- `libero_synth.log`: Libero synthesis wrapper log.
- `synplify.log`, `synplify_job.log`, `MPFS_ICICLE_KIT_BASE_DESIGN.srr`,
  `MPFS_ICICLE_KIT_BASE_DESIGN_fpga_mapper.srr`: successful synthesis/map
  evidence.
- `libero_pnr.log`: P&R/timing/export attempt log. Important markers:
  `SYNTHESIZE Tool inputs are out of date`, `STAGE_OK PLACEROUTE`, then
  repeated `PTOLEMI EXCEPTION` / `not ROUTED_CONNECT` entries.
- `MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt` and `.xml`:
  post-compile resource reports copied from the clone.
- `timing_analysis_jitter_report.txt`: timing-analysis side artifact from the
  failed verify/export attempt.

The next FPGA step should rerun synthesis in a mode that lets Libero save the
project state after `SYNTHESIZE`, then rerun VERIFYTIMING/export. If the Ptolemi
`not ROUTED_CONNECT` exceptions reproduce after a clean saved handoff, investigate
that as the primary Libero/P&R blocker before programming.
