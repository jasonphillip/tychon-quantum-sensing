# Codex Compaction Handoff - PolarFire V250 Rung F

Last updated: 2026-06-16 14:21 EDT by Codex.

This note captures the Codex-side context that should survive thread
compaction. Claude is still the active execution agent for the hardware bringup;
avoid editing its active handoff while it is running unless Jason asks.

## User Intent

Jason wanted Codex to diagnose what the parallel Claude session was doing wrong,
then convert that into durable instructions and prompts so Claude could continue
with much less copy/paste mediation.

Key preference learned during the thread: hardware-state changes are acceptable
on this lab FPGA when they are purposeful, logged, and rollback-safe. The
problem is not "changing hardware state"; the problem is changing state without
checkpoint, rollback, or a clear discriminator.

## Durable Instruction Changes Already Made

- `CLAUDE.md`
  - Added `## FPGA Ground-Truth Discipline`.
  - Added `## Autonomous FPGA Debug Operating Envelope`.
  - Updated the envelope to allow explicitly approved hardware-state changes
    when checkpointed and rollback-safe.
- `docs/agent_ground_truth_contract.md`
  - Added claim labels, source priority, conclusion gate, current FIC2/MPU
    cautionary example, and the autonomous debug envelope.
- `~/Desktop/Shared/wiki/CLAUDE.md`
  - Added operational-debugging evidence discipline and autonomous operational
    debugging envelope.
- `~/Desktop/Shared/wiki/CHANGELOG.md`
  - Added 2026-06-16 schema entries for the evidence discipline and autonomous
    operational-debugging envelope.
- Other repo docs were refreshed earlier in this Codex thread:
  - `README.md`
  - `firmware/linux/README.md`
  - `models/README.md`
  - `docs/fpga_reproducibility_inventory_2026-06-16.md`

## Technical State As Of Last Codex Check

Claude completed the read-only Rank-1 audit and the approved MPU3 deny-all
logger. Important facts:

- FIC2 MPU/SEG/clock/reset and address convention were exonerated.
- MPU3 deny-all logger produced the same stuck `CTRL=0x02` behavior and
  MPU3 STATUS stayed `0x0`, indicating no V250 M_AXI transaction reached the
  FIC2 MPU.
- The prior async `RRESP=0b11` DECERR should be treated as stale/risky, not a
  real captured beat.

Claude then found a stronger root cause:

- Live V250 VERSION register was `0x10010100`.
- Generated seed_7 artifact `core_vectorblox_C0.cxf` referenced
  `core_vectorblox` version `1.1.12`.
- VERSION decode indicated major `1`, size config `1` = V500.
- The software stack and model target SDK 2.0.x / core 2.0.1 / V250
  (`.vnnx` compiled `-c V250`).
- Therefore the programmed seed_7 bitstream contained CoreVectorBlox
  `1.1.12 / V500`, while the runtime/model expected `2.0.1 / V250`.

## Rebuild/Program State As Observed By Codex

Claude rebuilt an isolated clone on bee:

- Clone/project:
  `~/libero_seedsweep/seed7_vbx201_v250`
- Core swap:
  `core_vectorblox:2.0.1`, `PRESET:0` = V250, `M_AXI_DATA_WIDTH:128`
- Required resize change:
  `vectorblox_axi_resize` `ID_WIDTH:3 -> 4`, matching the 2.0.1 core's
  4-bit M_AXI ID.
- SmartDesign rewire was regenerated bottom-up and reported clean.
- Timing closed with worst slack `+0.848 ns`.
- New job:
  `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_vbx201_v250.job`
- New job sha256:
  `4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e`

Programming with the new job completed successfully:

- FPExpress stdout/log showed:
  - `JOB_PATH_VERIFIED new-V250-job`
  - device `MPFS250T`, Device Rev `01`
  - `ISC_ENABLE_RESULT: 00000000`
  - `CRCERR: 00`
  - `PROGRAM_PASS`
  - `device 'MPFS250T' : Executing action PROGRAM PASSED`
  - `Chain programming PASSED`
- New programmed digests from FPExpress:
  - BITS: `AEE355E728BED157183D65B414803CA9422E59D42B06365E61DDF1ED5EC41D74`
  - Security: `BFD905DECB768E283EE6627A713C664E806DF8E60D26A0997E38B171FB3795EC`
  - Fabric: `22A40FC163EC6A54A7465E4E61015D5FEA63E12FBC6A3BB978BCD493964D5974`
  - sNVM: `C011B109E3879C06A0ABCD593AC8B9EF014B1F12A5D99E91780D834B2E12349C`
  - EOB: `1CE134BD7A2890AC187089D794384FDCEF3E6D324ECF5C52D826564EB8585C3D`

At Codex's last check, `icicle` / `mpfs-icicle-kit.local` were not resolving
yet from Spark/Bee. That is likely post-program reconfiguration or mDNS/network
lag, but runtime proof was not yet observed by Codex.

## Rollback State

Trusted seed_7 rollback artifact remains:

- `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control.job`
- sha256:
  `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a`

Rollback uses the existing operator-mode FPExpress/programming flow. The rung-A
seed_7 programming evidence remains in `libero/reports/2026-06-15-program/`.

## Remaining Work

When Claude or a future agent resumes:

1. Reconnect to the Icicle Linux target.
2. Read CoreVectorBlox VERSION at `0x60030028`.
   - Expected after new programming: major `2`, size config `0` = V250.
3. Run bounded `vbx_probe`.
   - Expected if root cause is fixed: START should progress to RUNNING and/or
     OUTPUT_VALID instead of sticking forever at `CTRL=0x02`.
4. If `vbx_probe` advances, run bounded `vnnx_smoke` / model inference and
   capture outputs.
5. Revert Libero global vault to `C:/Microchip/Common/vault` and verify/report.
6. Update durable docs and wiki:
   - `docs/rung_f_decerr_handoff_2026-06-16.md`
   - `docs/fpga_reproducibility_inventory_2026-06-16.md`
   - top-level `README.md`
   - `firmware/linux/README.md`
   - `~/Desktop/Shared/wiki/projects/polarfire-hybrid-control/README.md`
   - `~/Desktop/Shared/wiki/CHANGELOG.md`

If the target still does not come back over Ethernet, check serial/MMUART and
DHCP/mDNS before assuming a bitstream failure.

## Current Repo Worktree Notes

At the time this note was written, the repo had pre-existing/uncommitted changes:

- Modified:
  - `README.md`
  - `firmware/linux/README.md`
  - `models/README.md`
- Untracked:
  - `docs/agent_ground_truth_contract.md`
  - `docs/fpga_reproducibility_inventory_2026-06-16.md`
  - `docs/rung_f_clock_inspection_plan_2026-06-16.md`
  - `docs/rung_f_decerr_handoff_2026-06-16.md`
  - `firmware/linux/vbx_probe.c`

`CLAUDE.md` is globally ignored, so its modifications do not appear in
`git status`.

## Suggested Resume Prompt

If Claude stalls after compaction, paste:

```text
Resume from docs/codex_compaction_handoff_2026-06-16.md and your active
docs/rung_f_decerr_handoff_2026-06-16.md. The new V250 .job has already been
programmed successfully. Continue with target reconnect, VERSION read, bounded
vbx_probe/vnnx_smoke, vault reversion, and docs/wiki updates. Do not rebuild
again unless the VERSION read or runtime proof shows the programmed image is
wrong. Use the evidence contract for every conclusion.
```
