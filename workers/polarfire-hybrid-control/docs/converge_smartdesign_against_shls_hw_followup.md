# Follow-up: Converge `02_import_ip.tcl` + `03_smartdesign.tcl` against actual SmartHLS `hw` output

**Status:** Deferred work (filed 2026-05-04). The demo bring-up took the
`04b_export_only.tcl` path against the audit-006 `seed_7` clone instead
of running the repo-native Tcl pipeline. That gets a `.job` to the kit
quickly but does **not** unblock Tcl-driven re-runs of synthesis from
the current `hls/src/*.cpp` sources. This document captures what was
discovered while triaging that path so a future session can finish the
job without re-discovering it.

## Why this matters

The repo's intended Tcl pipeline (`00_full_pipeline.tcl` →
`01_scaffold_proj.tcl` → `02_import_ip.tcl` → `03_smartdesign.tcl` →
`04_synth_pnr.tcl`) is the only path that produces a bitstream traceable
to commits on a `bringup/*` branch. Every alternative (seed_7 clone,
patch_smartdesign_pid_csr.py) introduces lineage drift and has
demo-relevant compromises (see
`docs/seed_7_register_map_2026-05-04.md`).

Without a working Tcl pipeline, **future RTL changes have no automated
synthesis path**. Hand-editing seed_7's prjx in the GUI to pick up new
SmartHLS output is the alternative, and that's exactly what the
two-slot canvas runbook costs us in human time.

## Ground truth now available

`shls hw` was successfully run on Beelink 2026-05-04 (cygwin/MSYS2
clang collision documented in `track0_bringup_runbook.md`). Outputs:

- `hls/hls_output/rtl/nv_pid_top_nv_pid_top.v` — generated Verilog
  containing the inner `nv_pid_top` module + the AXI-wrapped
  `nv_pid_top_top` outer module
- `hls/hls_output/rtl/nv_pid_top_nv_pid_top.vhd` — VHDL wrapper (same
  outer module)
- `hls/hls_output/rtl/ram_primitives/*.v` — memory primitives
- `hls/hls_output/rtl/mem_init/*.mem` — memory init files (Synplify
  needs `MEM_INIT_DIR` define)
- `hls/hls_output/.hls/Interfaces.json` — interface metadata
- `hls/hls_output/scripts/libero/create_hdl_plus.tcl` — top-level
  Libero import script (sources the per-module variant below)
- `hls/hls_output/scripts/libero/create_hdl_plus_nv_pid_top_top.tcl` —
  per-module HDL+ core registration with full AXI4 bus-interface
  signal mapping for the `axi4target` slave

These artifacts let every `VERIFY_AFTER_SHLS_HW` marker in the current
02/03 scripts be **resolved by reading**, not by guessing. Each marker's
ground-truth source is now diffable.

## Known mismatch table (discovered 2026-05-04)

| Script | Line | Current (wrong) | Should be | Source of truth |
|---|---|---|---|---|
| `02_import_ip.tcl` | 38 | `HLS_OUTPUT_DIR = hls_output` | (correct) | `find hls_output/` |
| `02_import_ip.tcl` | 44 | `HLS_TOP_MODULE = nv_pid_top` | `nv_pid_top_top` | shls log: `Outputting top-level module: nv_pid_top_top` + `create_hdl_plus_nv_pid_top_top.tcl:44` (`-module {nv_pid_top_top}`) |
| `02_import_ip.tcl` | 76-99 | manual `import_files -hdl_source <glob>` | replace with `source $hlsPrjAbsPath/hls_output/scripts/libero/create_hdl_plus.tcl` — handles the .v + ram_primitives glob, builds hierarchy, sets MEM_INIT_DIR define, AND registers the HDL+ core with full AXI4 bus interface | SmartHLS-shipped script |
| `03_smartdesign.tcl` | 52 | `PID_COMPONENT = nv_pid_top` | `nv_pid_top_top` | same as 02 above; this is the HDL+ core name |
| `03_smartdesign.tcl` | 293 | `${PID_INSTANCE}:axi_target_0` | `${PID_INSTANCE}:axi4target` | `create_hdl_plus_nv_pid_top_top.tcl` line ~50: `hdl_core_add_bif -bif_name {axi4target}` |
| `03_smartdesign.tcl` | 204 | `${PID_INSTANCE}:clk` | (verify) | read `nv_pid_top_nv_pid_top.v` port list |
| `03_smartdesign.tcl` | 214 | `${PID_INSTANCE}:reset` | (verify, may need ARESETn polarity flip for CoreVectorBlox) | same |
| `03_smartdesign.tcl` | 332-348 | bus port creation: `error_in[63:0]`, `u_AI_in[31:0]`, `actuator_out[31:0]` | (likely correct widths) verify via `Interfaces.json` against actual SmartHLS-emitted bit ranges (may have `_V` suffix on names) | `Interfaces.json` keys for non-AXI ports |
| `03_smartdesign.tcl` | 355-364 | `${PID_INSTANCE}:error / u_AI_in / ai_watchdog_timeout / actuator_out` | verify port names; SmartHLS may add `_V` suffix or word-pack | grep generated `.v` for the port list |

## Other VERIFY items still requiring resolution

These are 03's `VERIFY_AFTER_SHLS_HW` markers that depend on tool
catalog state, not on shls output:

- **MSS configurator parameters** (lines 106-121): the param set is
  labeled "representative" with comment "RECOMMENDED: Use the MSS
  Configurator GUI for the initial setup, then export to Tcl". This is
  the path forward — open MSS Configurator, save, export Tcl, paste
  into 02. Could also pull the MSS component out of seed_7 directly
  (`seed_7/component/work/ICICLE_MSS/`) since that one is already
  validated against this silicon and license footprint.
- **CoreVectorBlox VLNV + parameter set** (02 lines 123, 132-137):
  vendor field is "Microsemi" — needs validation against
  `query_cores` output in Libero 2025.2. Audit-006 used
  `Microchip:DirectCore:CoreVectorBlox:2.0.1` per the seed_7 prjx
  catalog references — diff against 02's current value.
- **CoreVectorBlox AXI port names** (03 lines 247-258): `AXI4_S` /
  `AXI4_M` are guessed; check seed_7's wiring of `Vectorblox_ss` for
  the actual names.
- **PF_CCC PLL parameters** (02 lines 175-182): 125 MHz reference, 200
  MHz output. Audit-006 closed timing at 125 MHz — the OUT0 frequency
  here may need to be 125 not 200 to match the validated baseline, or
  the SDC needs to follow the 200 MHz target. Decide before next
  pipeline run.
- **PF_INIT_MONITOR version** (02 line 188): pinned at `2.0.307` — may
  not match the catalog. Use `*` for latest or query the catalog.

## Recommended convergence approach

**Don't try to fix all 12 VERIFY items before running the pipeline.**
The lossy step is converging unknowns; 02 + 03 should fail fast and
specifically. Sequence:

1. **02 first.** Apply the three known fixes (mismatch table rows 1-3),
   plus the create_hdl_plus.tcl source replacement. This gets the PID
   datapath module imported correctly with full AXI bus interface.
   Skip the CoreVectorBlox + CCC + INIT_MONITOR sections initially —
   stub them as "TODO" so the script returns success on PID-only.
2. **Run pipeline up through 02.** Confirm `build_design_hierarchy`
   shows `nv_pid_top_top` as a discoverable HDL+ core with AXI bus
   interface attached. This is the cheap milestone.
3. **03 PID-only path.** Comment out the VBX/CCC/INITMON instantiation
   blocks. Wire MSS → PID directly (FIC_1 → axi4target). Promote the
   simple-wire ports to top level. Generate component. This is the
   minimum viable Tcl-driven design — no CoreVectorBlox required.
4. **Run synthesis end-to-end on PID-only.** Audit results against
   audit-006's r6_s25 baseline (timing slack, resource utilization).
   Should be very close to the seed_7 design minus the VBX block.
5. **Layer in CoreVectorBlox + CCC** once PID-only is closing. Each
   addition is a separate iteration on a separate branch.

This phased convergence avoids the "12 unknowns at once" failure mode
and produces a working Tcl pipeline within a tractable number of
Beelink iterations.

## Hard constraint: do NOT introduce pid_csr_block here

The current `libero/hdl/pid_csr_block.v` is **not yet
netlist-validated** (per `CLAUDE.md` and
`docs/smartdesign_two_slot_canvas_runbook.md`). The two-slot AXI
canvas it requires is the runbook's Phase II GUI work. Conflating
that work with this convergence task triples the surface area.

If pid_csr_block-bearing demos are needed, do that on a **separate
branch** that follows the two-slot canvas runbook, with the converged
Tcl pipeline as its starting point — not the other way around.

## Estimated effort

- Phase 1 (steps 1-2 above, PID-only import): 1-2 hr including one or
  two Beelink iterations
- Phase 2 (step 3, SmartDesign wiring): 1 hr
- Phase 3 (step 4, full synth + audit): 30-60 min (mostly wall time)
- Phase 4 (step 5, VBX layer-in): 2-4 hr depending on what surfaces

Total: ~1 day of focused work, vs. open-ended hand-debugging with no
plan.
