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

## Package mismatch — RESOLVED 2026-05-03

The reference design targets **MPFS250T-FCVG484** (484-ball flip-chip BGA).

**Silicon confirmed:** physical Icicle Kit silkscreen reads
`MPFS250T-FCVG484E`, date code `2241` (ISO week 41 of 2022). Corroborated
by the pristine Beelink project log
`tooldata/MPFS_ICICLE_Vectorblox.log` (2026-04-02).

**Action taken:** `01_scaffold_proj.tcl` updated to
`set DEVICE_PACKAGE "FCVG484"`. The PDCs in this bundle are now
pin-correct for the project device and validate cleanly. The earlier
HW-01 finding that silicon was FCSG536e is superseded; see
`PACKAGE_AUDIT.md` header for the full record.

The April 28 P&R reports in `libero/reports/2026-04-28/` succeeded, which
implies the project was previously built against a working PDC set (likely
imported inside Libero GUI rather than via the Tcl scaffold). With the
scaffold now declaring FCVG484, regenerated runs through `01_scaffold_proj.tcl`
should match the GUI-imported behavior.

## License

Copied verbatim from polarfire-soc/icicle-kit-reference-design, which is
distributed under the MIT License (see LICENSE.md in that repo).
