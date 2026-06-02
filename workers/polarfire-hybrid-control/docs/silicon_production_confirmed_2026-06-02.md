# Production Silicon Confirmed — New Icicle Kit (2026-06-02)

**Bottom line: the newly-installed kit carries Production `MPFS250T` silicon, its JTAG IDCODE matches what the seed_7 bitstream expects, and FPExpress's chain check now PASSES. Rung A (PROGRAM PASS) is unblocked — the existing `program_kit.tcl` will work as-is, no bitstream re-export needed.**

## Context

On 2026-05-18 rung A was blocked: the original kit carried Engineering-Sample silicon (`MPFS250T_ES`) while the seed_7 `.ppd` targets Production `MPFS250T`. FPExpress's Scan-Check-Chain rejected the mismatch and the run-time override path was proven closed (the `.ppd` payload header — not FPExpress chain config — is the source of the "Expected" silicon class). A Production-SKU kit was ordered. It arrived and was installed; this document records the confirmation scan.

See `libero/reports/2026-05-18-program-failure/FAILURE_ANALYSIS.md` and `libero/reports/2026-05-18-program-attempt-2/FAILURE_ANALYSIS_APPENDIX.md` for the original ES-block forensics.

## Read-only scan evidence

Ran `libero/scripts/scan_chain.tcl` (FPExpress `scan_chain_prg` — read-only, scans + analyzes the JTAG chain, programs nothing). Full transcript: `libero/reports/2026-06-02-scan/scan.log`.

```
Programmer: Embedded FP6 'F31E000A' : Version = EF9B
programmer 'F31E000A' : Scan Chain...
programmer 'F31E000A' : Found 8 instruction register bits.
programmer 'F31E000A' : Checking IDCODEs...
programmer 'F31E000A' : Device 1: 1F81A1CF Mfr: Microsemi Part: MPFS250(T|TS|TL|TLS|TC)
programmer 'F31E000A' : Check Chain...
programmer 'F31E000A' : Scan and Check Chain PASSED.
```

### Decoded

| Field | Value | Significance |
|---|---|---|
| **JTAG IDCODE** | `1F81A1CF` | First clean 32-bit ID captured for this project's silicon. The ES board's raw IDCODE was never recoverable (SmartDebug wouldn't run headless in 2025.2). This is the canonical Production-kit signature. |
| **Part class** | `MPFS250(T\|TS\|TL\|TLS\|TC)` | **No `_ES` suffix** — Production family, not the `MPFS250T_ES` that blocked rung A on 2026-05-18. |
| **Mfr** | Microsemi | Expected. |
| **IR bits** | 8 | Single PolarFire SoC device on the chain, as expected (FlashPro6 itself enumerates separately as HID — not on the JTAG chain). |
| **Chain check** | **PASSED** | This is the exact step that FAILED on 2026-05-18. The seed_7 `.ppd` (built for Production `MPFS250T`) now matches the silicon. |

## Hardware enumeration (bee, 2026-06-02)

New board, distinct from the ES board (different physical hardware → different USB serials):

- **FlashPro6 (J11)**: serial **`F31E000A`**, Status OK, Present=True. (Old ES board's `065D9ACD` now shows as a stale "Unknown"/not-present registry ghost.)
- **CP2108 quad-UART (J33)**: live ports are now **COM7 / COM8 / COM9 / COM10** per `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` (`Silabser0..3` → COM7..COM10). The old board's COM3–COM6 are stale ghosts. **The MMUART0→COM mapping must still be confirmed empirically at rung D** (open all four, reset kit, watch for the banner) — do NOT assume Interface 0 = MMUART0.

## What this unblocks

- **Rung A** runs as-is: `libero/scripts/program_kit.tcl` (PROGRAM action against device `MPFS250T`). The chain check that failed before now passes, so the run will proceed to actually program the fabric. Expect PROGRAM PASS.
- The seed_7 bitstream (`libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job`, sha256 `d5f3eb4e…`, V250 NPU in fabric by construction) is the artifact to program. Unchanged.

## Two-board reality (record for provenance)

There are now **two** physical Icicle Kits in play:
1. **ES board** (original, serial `065D9ACD`, silicon `MPFS250T_ES`) — set aside. Forensics in `libero/reports/2026-05-18-program-*`.
2. **Production board** (new, serial `F31E000A`, silicon `MPFS250T` IDCODE `1F81A1CF`) — the active board for all bring-up from 2026-06-02 forward.

Errata 80001031 caveats apply to both revisions and are unchanged (see memory `project_silicon_rev_errata.md`).
