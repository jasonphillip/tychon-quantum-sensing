# Safety VM-Import Probe - 2026-06-21

Purpose: test whether importing the completed safety-clone Synplify netlist
(`MPFS_ICICLE_KIT_BASE_DESIGN.vm`) back into a cloned Libero project would make
downstream `PLACEROUTE` / `VERIFYTIMING` / programming-data stages runnable
without forcing invalid tool-state edits.

Remote clone:

```text
~/libero_seedsweep/seed7_vbx201_v250_safety_vmimport_20260621_1128
```

Result: attempted, not closure.

- `import_files -verilog_netlist` succeeded.
- `organize_tool_files` for `PLACEROUTE` and `VERIFYTIMING` succeeded.
- `build_design_hierarchy` succeeded.
- All relevant Libero tool states still remained `Tool inputs are out of date`
  before and after the import.
- No P&R, timing, programming-data generation, or job export was run from this
  probe.
- No safety `.job` was created.
- No programming was performed.

Key files:

- `probe_vm_import_state.tcl` - exact Libero Tcl probe.
- `libero_vmimport_state.log` - raw Libero output.
- `final_capture.txt` - process check, key log lines, VM hash/proof lines, and
  safety-job search.
- `SHA256SUMS` - local evidence hashes.

Conclusion: the clean VM-import route did not resolve the headless Libero
handoff blocker. The next useful paths are GUI/job-manager handoff, a clean
project import flow that produces valid Libero state from source, or fixing the
routed database/P&R issue from a fresh seed.
