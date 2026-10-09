# SmartDesign Two-Slot AXI Canvas Runbook

This runbook is the **production** path for wiring the SmartHLS-generated
`nv_pid_top` axi_target slave **and** the hand-written `pid_csr_block` so
that software can write to one slave, read from the other, and observe
the PID datapath survive synthesis. The corpus is explicit that this is
the architectural proof of survival
(`~/.corpus/polarfire-control-corpus/raw/user-contributed/preserving-real-smarthls-pid-datapath.md:97`):
"Software can write non-default values, read back full-width values, and
observe corresponding changes in output or status counters. **This last
step is architectural proof that the surviving netlist still carries the
semantics you intended.**"

## Why This Cannot Be Regex-Patched

The corpus
(`preserving-real-smarthls-pid-datapath.md:105-119`) says SmartDesign Tcl
object names are design-specific and the safe ground-truth method is
"export the current SmartDesign or component Tcl from your local project
and modify that emitted Tcl, instead of inventing instance or
bus-interface names by hand." Any regex patch over a Libero-generated
`MPFS_ICICLE_KIT_BASE_DESIGN.v` that adds an interconnect with two new
slave slots will likely diverge from what SmartDesign re-emits on
regenerate, leaving the design in a half-edited state.

The **headless Phase I shortcut** for the same observability surface is
in `libero/scripts/patch_smartdesign_pid_csr.py` — it taps the FIC_0
master to drive both slaves as eavesdroppers. That run defeats Synplify
constant-folding (the corpus's first criterion) but does **not** provide
software write-then-readback (the second criterion). Use Phase I for
synthesis closure evidence, then follow-on (this runbook) for full proof.

## Follow-On Path: GUI / Tcl Steps

Open the Libero project and the `MPFS_ICICLE_KIT_BASE_DESIGN` SmartDesign
component.

1. **Add interconnect.** Catalog -> "Bus Interfaces" -> instantiate
   `CoreAXI4Interconnect` (vendor field varies by Libero version; in
   2025.2 try in this order: Microchip, Microsemi, Actel — confirm with
   `query_cores` from the Tcl console if you need to script it). Place
   on the canvas. Configure:
   - 1 master interface (will be wired to FIC_0_PERIPHERALS_1_AXI4mslave0).
   - 2 slave interfaces.
   - Both slaves AXI4-Lite.
2. **Add slot 0 — `nv_pid_top` axi_target.** Set base address
   `0x4000_0000`, size `16 KiB`. The `nv_pid_top` core's existing
   `axi4target_*` ports map to slave port 0 of the interconnect. Match
   the ADDR/DATA widths SmartHLS generated (typically 6-bit address,
   64-bit data — verify in `nv_pid_top.v`).
3. **Add slot 1 — `pid_csr_block`.** Instantiate `pid_csr_block` from
   `libero/hdl/pid_csr_block.v` (already in the HDL list). Set base
   address `0x4001_0000`, size `16 KiB`. Connect its `S_AXI_*` to slave
   port 1.
4. **Wire interconnect master.** Connect the interconnect's master port
   to `FIC_0_PERIPHERALS_1_AXI4mslave0` on the existing MSS bus.
5. **Connect status taps.** `pid_csr_block` requires:
   - `tap_pre_clamp_out`, `tap_post_clamp_out`, `tap_integrator`,
     `tap_derivative`, `tap_saturation_flag`, `tap_watchdog_timeout`,
     `tap_cooldown_remaining`, `tap_ai_active` from `nv_pid_top` and
     `watchdog_timer_0`. Promote these as new top-level observability
     wires inside SmartDesign first; do not invent net names from text.
6. **Wire `vbx_pulse_gen` between Vectorblox.output_valid and the
   watchdog.** Promote `Vectorblox_ss.output_valid` to top-level signal
   `Vectorblox_ss_output_valid`, instantiate `vbx_pulse_gen`, drive
   `watchdog_timer_0.refresh_in` from its `pulse_o`. Citations are in
   `libero/hdl/vbx_pulse_gen.v` (HB0919:361, 499, 784;
   preserving:121-125).
7. **Regenerate component.** Right-click `MPFS_ICICLE_KIT_BASE_DESIGN`
   -> Generate Component. Open the **Memory Map** report and confirm
   both slaves appear at distinct base addresses.
8. **Export design Tcl** from the component (right-click -> Export ->
   Component Tcl). Diff against the prior export to confirm only the
   intended changes are present.
9. **Synthesize.** Run `04_synth_pnr.tcl`. Then audit:
   ```
   make beelink-verify TAG=$(date +%F)-claude-r2-phase2
   ```
   Expected: `make audit-reports-strict` passes with zero critical
   pruning hits, no output_valid wiring issues, no readback-contract
   concern.
10. **Software acceptance.** With firmware loaded:
    - Write `0x12345678` to `0x4001_0020` (Kp_shadow).
    - Read `0x4001_0020` -> must return `0x12345678`.
    - Write the same value to the corresponding offset on the
      `nv_pid_top` axi_target slave at `0x4000_0xxx`.
    - Read the post-clamp output at `0x4001_0044` -> must change when
      stimulus or coefficients change.

## Failure Modes to Watch For

- **Vendor-field mismatch.** If `CoreAXI4Interconnect` does not
  instantiate, the vendor name differs in this Libero install. Use the
  Tcl console: `get_libraries`, then look for the interconnect under the
  matching library.
- **Address overlap.** If the memory-map report shows overlap with
  existing FIC_0 peripherals, move the bases (e.g. `0x6000_0000` /
  `0x6001_0000`).
- **Width mismatch on slot 0.** SmartHLS sometimes emits a 64-bit data
  bus for `axi_target`. The interconnect must be configured to match.
- **Readback returns `0xDEADBEEF` or X.** The interconnect's slot-1
  RREADY/RVALID wiring is incorrect. Re-export the component Tcl and
  verify both slots' read channels are independent (no shared RDATA).
