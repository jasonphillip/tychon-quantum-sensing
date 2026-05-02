# Icicle Kit Reference PDC Bundle

Mirrored from `https://github.com/polarfire-soc/icicle-kit-reference-design`
(commit `fd0aebb`, 2026-04-13) — `script_support/constraints/`.

These are the canonical Microchip-authored physical constraints for the
PolarFire SoC Icicle Kit (`mpfs-icicle-kit`). The project's
`MPFS_ICICLE_KIT_BASE_DESIGN` top-level uses the same I/O surface as the
reference design (CAN, MMUART, PCIESS, REFCLK, SD/eMMC, SGMII, USB, switches),
so this is the source of truth for pin-locking those ports.

## Usage from the Tcl scaffold

In `libero/scripts/01_scaffold_proj.tcl` (after `new_project`), import the
master `ICICLE.pdc` plus whichever subsystem PDCs the design instantiates:

```tcl
foreach pdc {
    ICICLE.pdc
    ICICLE_PCIE.pdc
    ICICLE_MAC.pdc
    ICICLE_MMUART0.pdc
    ICICLE_USB.pdc
    ICICLE_SDIO.pdc
} {
    import_files -io_pdc [file join $REPO_ROOT libero constraints icicle_reference $pdc]
}
```

The existing `decision-2-option-c.pdc` (XCVR REF_CLK explicit-lock fix) layers
on top and should be imported AFTER `ICICLE_PCIE.pdc`.

## CRITICAL: Package mismatch — must verify before use

The reference design targets **MPFS250T-FCVG484** (484-ball flip-chip BGA).
The current project scaffold (`01_scaffold_proj.tcl`) declares **FCSG536**.

Pin names in these PDC files (e.g. `V19`, `U18`, `W18`, `L19`, `L20`) are the
canonical FCVG484 ball locations and **will fail validation if the project
device package is FCSG536** — those balls don't exist on the FCSG536 substrate.

### Action required

1. Read the part number off the silkscreen of the actual Icicle Kit board.
2. If silkscreen says `MPFS250T-FCVG484E` (canonical Icicle Kit):
   - Update `01_scaffold_proj.tcl`:
     `set DEVICE_PACKAGE "FCVG484"` (was `"FCSG536"`)
   - These PDCs will then validate cleanly.
3. If silkscreen confirms `MPFS250T-FCSG536` (rare variant):
   - These PDCs cannot be used as-is.
   - Pin remapping required — translate FCVG484 ball coords to FCSG536 via
     the Microchip pin-translation tables in `aPA5SOC/PA5SOC250/pinouts/`.

The April 28 P&R reports in `libero/reports/2026-04-28/` succeeded, which
implies the project was previously built against a working PDC set (likely
imported inside Libero GUI rather than via the Tcl scaffold). Compare the
Libero-managed `*.pdc` inside `libero/work/` (when it exists) against this
bundle to identify any local edits.

## License

Copied verbatim from polarfire-soc/icicle-kit-reference-design, which is
distributed under the MIT License (see LICENSE.md in that repo).
