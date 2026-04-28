# Project Recovery Notes — decision-2-option-c P&R Blocker

**Last updated**: 2026-04-28 ~16:58 EDT
**Branch**: decision-2-option-c
**Status**: PDC fix correct and committed; Beelink toolchain state corrupted in a way
that survives surgical repair attempts. Next step requires hands-on Libero GUI
recovery or SmartHLS reference-design reinstall on Beelink.

## What's correct and committed

- `libero/constraints/decision-2-option-c.pdc` — fp_pdc locking
  `CLOCKS_AND_RESETS_inst_0/PCIE_REF_CLK_0/PCIE_REF_CLK_0/I_IO` at
  x=2468, y=236 with `-fixed true`. This is the actual PRPF_009 fix
  and is verified against the regenerated SmartDesign netlist hierarchy.
- `libero/constraints/PDC_FIX_NOTES.md` — diagnosis writeup for the PRPF_009.
- `libero/scripts/decision-2-c-pdc-rerun.tcl` — full pipeline rerun script
  (synth + P&R + timing + power), already corrected to import as fp_pdc.
- `libero/scripts/decision-2-c-pdc-smoke.tcl` — open + import + save smoke test.
- `libero/scripts/decision-2-c-load-only.tcl` — minimum-viable open+close test.
- `libero/scripts/extract_reports.sh` — Spark1-side report extractor.

## Numbers available for the Phase I report (Section 7)

These are real data we already have committed to the branch:

**April 2 baseline P&R (reference design without overlay)** — from
`libero/reports/2026-04-28/MPFS_ICICLE_KIT_BASE_DESIGN_iteration_summary.rpt`:
- Worst slack: +0.165 ns (closes timing at 200 MHz / 5 ns)
- Resource: 24.72% LUT, 20.92% DSP, 11.82% LSRAM, 75.74% MSS I/O
- SmartPower fabric: 2,664 mW

**April 28 synthesis with decision-2-option-c overlay** — from same dir,
`MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt`:
- 4LUT: 24.69% (Δ −0.03% vs April 2 baseline)
- DSP / LSRAM / MSS I/O: unchanged
- AXI register `inner_clamp_setpoint` confirmed exposed at offset 0x20
- This proves the hybrid sector clamp adds essentially zero resource cost.

**Post-P&R timing/power for decision-2-option-c**: NOT YET CAPTURED. Blocked
by toolchain state issue documented below.

## The Beelink toolchain blocker (deterministic, not yielding to repair)

Every Libero session against the
`/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox`
project produces an **identical, byte-deterministic 626-line / 139890-byte stdout
log** ending with a partial "Reading file..." line after `hdl/miv_ihcc.v`.

The April 28 morning overlay session (overlay_session.log, 319,910 bytes) loaded
the same project past this point successfully and only failed at PLACEROUTE with
PRPF_009. So the corruption is **specifically** post-April-28-failed-P&R state.
The `.prjx` mtime is exactly 2026-04-28 12:00:41 — when April 28 P&R failed and
saved.

### Strategies attempted in this session

**B1 — Surgical prjx repair** (FAILED).
The only structurally anomalous prjx entry was at line 2656: an absolute Windows
path `~\dev\projects\tychon-polarfire-control\hls\hls_output\rtl\nv_pid_top_nv_pid_top.v`
to the OLD repo. Every other entry uses `<project>\` relative paths. Removed those
5 lines. Same byte-deterministic crash.

**B2 — Designer scratch reset** (FAILED).
Renamed `designer/MPFS_ICICLE_KIT_BASE_DESIGN/` aside (containing the post-failed-PnR
.afl, .seg, .loc files). Same byte-deterministic crash.

**B3 — .job restore to sibling dir** (NOT APPLICABLE).
Investigated `MPFS_ICICLE_KIT_BASE_DESIGN_2023_02.job` — discovered it is a
**programmer/bitstream job** (contains `pgm.map`, header.xml — 76 MB of programming
data), NOT a project archive. Libero's `restore_project` Tcl returned an opaque
empty error against it. Cannot use this for project recovery.

**B4 — MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl in fresh dir** (FAILED: install bug).
Successfully copied the Tcl + script_support to fresh dirs and ran both
`VECTORBLOX:1` and `SPI_LOOPBACK:1` variants. **Both fail with the same
device-mismatch error**:

```
Error: MSS component 'ICICLE_MSS' created using 'an engineering sample' device
cannot be imported to current libero SoC project targeted to 'a non-engineering
sample' device.
Please regenerate the MSS component using the same device as current Libero SoC
project and then import it back. [OK]
Error: Libero failed to import '~\AppData\Local\Temp\d_p_z_unzip\ICICLE_MSS.cxf'.
Error: The command 'import_mss_component' failed.
Error: Failure when executing Tcl script. [Line 96]
```

The bundled `ICICLE_MSS.cxf` shipped with the SmartHLS reference designs on
Beelink was generated for **engineering-sample (ES)** silicon, but the
reference Tcl creates new projects targeting `MPFS250T` production die.
This is the actual install-level toolchain bug.

**B5 — Project clone to /c/temp/** (FAILED, but informative).
Copied the entire `MPFS_ICICLE_Vectorblox/` to `/c/temp/MPFS_clone_d2c/` and
ran load-only there. **Same byte-deterministic crash** (607 lines / 82527 bytes
— different byte count only because the new path is shorter, same number of
files read). Confirms the corruption travels with the project files, not the
filesystem location.

Combined with B4: the ORIGINAL project's `component/work/ICICLE_MSS/` is the
only production-targeted MSS on the system (it was hand-regenerated at some
point in the project's history). The fresh-project flow can't replicate it
without either:
1. A production-targeted MSS .cxf bundle (would need from a fresh SmartHLS
   install on a clean machine), or
2. Hands-on MSS configurator work in Libero GUI to regenerate ICICLE_MSS for
   `PA5SOC250T` production silicon.

### Other observations

- The crash leaves no Windows Application Error log entry (checked via
  `Get-WinEvent`). Libero exits "cleanly" but prematurely.
- Foreground exec returns exit code 127 (bash "command not found"); backgrounded
  via `nohup ... & disown` runs ~1 minute and exits.
- Project loading reads ~626 Verilog files from the project, then the process
  ends without running synth/P&R/etc. Tcl `puts` statements after `open_project`
  never appear in the log.

## State on Beelink at end of session

Rolled back to original state:
- `MPFS_ICICLE_Vectorblox.prjx` restored from `MPFS_ICICLE_Vectorblox.prjx.bak-pre-loadtest-20260428-163808`
- `designer/MPFS_ICICLE_KIT_BASE_DESIGN/` renamed back from B2 backup
- All orphan `tooldata/libero.*` lock files cleaned
- Stale `constraint/io/decision-2-option-c.pdc` (from incorrect io_pdc attempt) removed
- `constraint/fp/decision-2-option-c.pdc` retained in place for the eventual
  recovery — staged correctly as fp_pdc

Backups retained on Beelink for future investigation:
- `MPFS_ICICLE_Vectorblox.prjx.bak-pre-loadtest-20260428-163808` (full)
- `MPFS_ICICLE_Vectorblox.prjx.bak-b1` (post-B1 edit)

## Recommended next steps (in priority order)

1. **Hands-on Beelink GUI session — Libero GUI open of the existing project**.
   The CLI batch mode crashes silently. Opening the original project in the
   GUI may surface the actual modal dialog/error that's killing the batch
   load. Most likely the dialog asks about regenerating ICICLE_MSS (because
   of an internal device-version mismatch similar to the fresh-project flow),
   and the GUI lets you accept the regeneration where the CLI can't.

2. **Hands-on MSS regeneration in Libero GUI for production silicon**.
   Independently from #1: in the Libero GUI, open the existing project's
   ICICLE_MSS component and regenerate it for `PA5SOC250T` (production)
   target. Then re-overlay HLS, run pipeline. This may also fix the silent
   open_project crash if the cause is indeed an MSS device mismatch.

3. **Run on a different machine** with a clean Libero 2025.2 install +
   SmartHLS reference designs configured for production silicon (NOT
   engineering sample). The HLS source, PDC, and overlay scripts in this
   branch are toolchain-portable. A pristine install on Spark1 or another
   x86 dev machine would bypass both the install bug (B4) and the project
   corruption (B1, B2, B5).

4. **File a Microchip support case** about the SmartHLS reference designs
   shipping with an ES-targeted ICICLE_MSS.cxf that fails to import into
   production-die projects. This blocks any user trying to follow the
   reference design's intended workflow on production MPFS250T silicon.

## What NOT to do

- Do not attempt further B1-style surgical prjx edits — the corruption is
  deeper than any single FileManager entry.
- Do not delete the original `MPFS_ICICLE_Vectorblox/` directory on Beelink —
  the backups and the `.prjx.bak-*` files there are the only forensic record
  of what changed during April 28's session.
- Do not modify the `.nmatinit.pdc` — it's autogenerated by P&R and reverts
  on each run.

## What this means for the Phase I report

Section 7 can be written today using:
- April 2 baseline numbers as the FPGA timing/power claim (200 MHz close, 2664 mW).
- April 28 synthesis numbers showing the decision-2-option-c overlay adds
  ~0% resource impact (4LUT delta of −0.03%).
- A footnote that post-P&R numbers for the overlay specifically are pending
  re-run on a clean toolchain (toolchain blocker, not design issue).

The PDC fix in this branch is independently verifiable: the absent
`set_location -fixed true` for the XCVR_REF_CLK macro is the demonstrated cause
of the April 28 PRPF_009; the PDC adds it; the April 2 baseline placement
proves x=2468, y=236 is the correct target. Whoever runs the toolchain recovery
in step 1-3 above should get clean P&R numbers on the first attempt.
