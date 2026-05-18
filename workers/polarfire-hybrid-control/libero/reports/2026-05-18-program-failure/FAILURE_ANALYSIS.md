# Rung A — PROGRAM FAILED 2026-05-18

**Status: STOPPED per pre-execution rollback rule. No retry. No power-cycle. Surfaced to operator.**

## Symptom (verbatim from FPExpress log)

```
programmer '065D9ACD' : Scan Chain...
programmer '065D9ACD' : Check Chain...
Error:  programmer '065D9ACD' : Device 1: Found: MPFS250(T_ES|TS_ES), Expected: MPFS250T
Error:  programmer '065D9ACD' : Scan and Check Chain FAILED.
Error:  Failed to run Action.
```

## Decoded

- **Scan Chain passed** — FlashPro6 (programmer 065D9ACD, Embedded FP6, firmware EF9B) successfully read a JTAG IDCODE from the device on J11.
- **Check Chain failed** — the IDCODE that came back matches the **engineering-sample** silicon class (`MPFS250T_ES` or `MPFS250TS_ES`), not the production `MPFS250T` that the bitstream's `.ppd` was built for.

## Conflict with prior project assumptions

`fpga_bringup_state_2026-05-18.md` memory + `project_silicon_rev_errata.md` memory both state the kit silicon is **`MPFS250T-FCVG484E Rev 0` (date code 2241)** — claimed as Production silicon.

`libero/scripts/01_scaffold_proj.tcl:27` and the seed_7 closure (audit-006) both target `MPFS250T` Production silicon, confirmed by SmartTime header `Data source: Production` and the +0.728 ns slack closure on FCVG484 STD-grade.

But FPExpress's IDCODE read on the actual silicon returns the **engineering-sample class**, not Production.

Possible root causes (operator must decide which to investigate):

1. **The kit truly has engineering-sample silicon.** The silkscreen "Rev 0" marking may have been misread, or this kit batch was an early engineering-sample run distributed before Production. Date code 2241 (week 41 of 2022) is early enough that engineering samples were still in circulation.
2. **IDCODE / silicon-revision mapping quirk in Libero 2025.2.** Microchip's `chain.def` file may classify some Production silicon as `(T_ES|TS_ES)` due to a Libero metadata bug. (Unlikely but possible — the regex-style class name `MPFS250(T_ES|TS_ES)` looks like a pattern from a chain-definition file.)
3. **Bitstream `.ppd` was built with the wrong silicon-type tag.** The .job file from `04b_export_only.tcl` ran on bee 2026-05-04 against the seed_7 closure. If that .ppd locked in the production-MPFS250T identity but the kit actually has ES silicon, this mismatch would surface here. But that contradicts the SmartTime closure data which says Production.

## Forensic artifacts captured

- `libero/reports/2026-05-18-program-failure/fpexpress.log` (2566 bytes) — full FPExpress run log including programmer detection, .ppd load, action selection, and the failed Scan/Check Chain transcript.
- This `FAILURE_ANALYSIS.md` document.

## What was NOT done (deliberately, per rollback rule)

- **No retry.** Did not re-launch FPExpress.
- **No power-cycle of the kit.** Kit remains in its post-Scan-Chain state — first failure forensic state preserved.
- **No bitstream regeneration with different silicon target.** That would be a major rework decision; operator must call it.
- **No erase / sNVM-touching / eMMC-touching action.** Only the PROGRAM action was attempted, only against fabric.

## What the operator should consider

1. **Re-read the kit silkscreen markings** with magnification. Look for any "ES" / "Engineering Sample" indicator. Date code (assumed 2241) and silicon revision marking — compare against the FCVG484e silicon corpus (`tychon-fpga-mpfs250t-fcvg484e`) device-marking section.
2. **Cross-check with Microchip's IDCODE registry.** What IDCODE values map to `MPFS250T_ES` vs `MPFS250TS_ES` vs `MPFS250T` Production? The corpus has the PolarFire SoC datasheet (DS00004248) which may include the JTAG ID register definition.
3. **If silicon truly is ES**: re-export the .job file from seed_7 with `MPFS250T_ES` as the device target. This requires re-running the Libero export flow on bee against the existing P&R'd seed_7 closure (no new synth or P&R needed; only `export_prog_job` re-run with the corrected device-class spec). Estimated effort: ~30 min if seed_7's prjx is still openable.
4. **If silicon is Production but Libero is misclassifying it**: search Microchip release notes for Libero 2025.2 `chain.def` issues / patches. Unlikely path; ES classification is more probable.
5. **Continue with simulation-only work in parallel** while silicon-identity is resolved: rung B (RPO-6 SmartPower workload closure) is unaffected by this failure and can run independently.

## Programmer + design metadata captured for record

- Programmer: Embedded FP6 '065D9ACD', firmware version EF9B, FlashPro6Lite class, USB 1.1 connection
- Design loaded: `MPFS_ICICLE_KIT_BASE_DESIGN`, .ppd CHECKSUM `9F8A`, PDB_VERSION `1.0`
- JTAG TCK: 4 MHz (per .pro file `<TCK>4000000</TCK>`)
- Bitstream source: `libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job` (sha256 `d5f3eb4e…`)
