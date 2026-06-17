# Two-Slot Integration — closure package (2026-06-17)

Clean two-slot PID integration (branch `bringup/2026-06-17-two-slot-pid`), built
in-place in `seed7_vbx201_v250` on bee. Full design/register map:
`docs/two_slot_register_map_2026-06-17.md`.

## Demo-watchdog build (PRIMARY, for Rung G dashboard)

| Field | Value |
|---|---|
| Job | `polarfire_hybrid_control_two_slot_demo.job` (12,126,495 B) |
| Job sha256 | `a5550f9e486e19f127aad78e97e06e0839d359c91028d4bcd21bb32b98f5b367` |
| Fabric bitstream digest | `a77dcead3de3ecc32399cf83af8f696a295ce449733b76ff0b8a5881a8f687b6` |
| sNVM digest | `c011b109e3879c06a0abcd593ac8b9ef014b1f12a5d99e91780d834b2e12349c` |
| Entire bitstream digest | `517ebf18f8b4a48e4021eef25bb7f95df3558e62b590d30e07184fc3db83b6bb` |
| Worst slack | **+0.950 ns** (multi-pass seed 29; "Timing constraints have been met") |
| Watchdog | `62_500_000` cycles = **500 ms @125 MHz** (host-paced demo; NOT the 1 ms bound) |
| Synth (GATE 1a) | no multiple-drivers; no whole-instance/coefficient prune; 109 DSP / 54491 LUT |
| Bee export | `seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_demo.job` |
| NAS backup | `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control_two_slot_demo.job` (sha256 verified) |

Programs **Fabric + sNVM only** (eNVM/HSS/U-Boot/Linux/SD untouched). Timing
report: `two_slot_timing_r10_s29.rpt`. Programming digest: `two_slot_demo_job.digest`.

## Safety-spec build (1 ms watchdog) — TODO (second build)

Same netlist, `patch_two_slot.py --watchdog-cycles 125000`; exported as
`polarfire_hybrid_control_two_slot_safety.job`. Kept separate by filename + sha256
+ program log. Built after the demo build's Rung E/F/G validate.

## Rollback (preserved — do NOT overwrite)

| Build | Job sha256 | Location |
|---|---|---|
| V250-rebuild (working V250, recommended) | `4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e` | bee export + NAS |
| seed_7 rung-A | `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a` | bee + NAS |

Boot-time PCIe-disable lives in the U-Boot env (bitstream-independent), so a
two-slot or rollback program still boots Linux without the PCIe boot-loop.
