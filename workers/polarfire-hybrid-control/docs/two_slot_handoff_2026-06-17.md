# Two-Slot Integration — end-of-day handoff (2026-06-17)

Branch `bringup/2026-06-17-two-slot-pid`. Paused for the day; the kit is being
fully powered off (a **cold power-cycle**, which is the intended next-session
discriminator — NOT a failure/rollback). Evidence labels per
`docs/agent_ground_truth_contract.md`.

## Where things stand

The clean two-slot PID integration is **built, timing-closed, and programmed onto
silicon**. Rung F (V250 inference) is currently failing post-program and needs a
cold power-cycle to discriminate cold-init vs real regression (below).

### Phase 1 — DONE (built, closed, archived)
- `pid_subsystem.v` = `axi4_demux2` (1→2 AXI4 splitter on the only free crossbar
  slot, SLAVE3 `0x60040000`) + `nv_pid_top.axi4target` (gains `0x60040000`) +
  `pid_csr` (`pid_csr_axi4_wrap` 64→32 bridge, CSR `0x60040800`) + `watchdog_timer`
  + `vbx_pulse_gen`. All datapath local. Patcher `libero/scripts/two_slot/patch_two_slot.py`.
- **GATE 1a (synth) PASS:** no multiple-drivers; no whole-instance/coefficient
  prune; all 7 modules survive; 109 DSP / 54491 LUT.
- **GATE 1b (timing) PASS:** worst slack **+0.950 ns** ("constraints met", seed 29).
- **GATE 1c:** closure package archived (`libero/reports/2026-06-17-two-slot/`),
  demo `.job` backed up to NAS (hash-verified).

### Phase 2 — PROGRAM PASS, Rung F regressed (NEEDS COLD POWER-CYCLE)

**Demo `.job`** (62.5e6-cycle = 500 ms host-paced watchdog):
- path (bee): `seed7_vbx201_v250/export/polarfire_hybrid_control_two_slot_demo.job`
- NAS: `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control_two_slot_demo.job`
- **sha256 `a5550f9e486e19f127aad78e97e06e0839d359c91028d4bcd21bb32b98f5b367`** (12,126,495 B)

**PROGRAM PASS (FPExpress, F31E000A, operator mode), CONFIRMED:**
- `JOB_PATH_VERIFIED two-slot-demo`, `ISC_ENABLE_RESULT 00000000`, `CRCERR 00`,
  `device 'MPFS250T' PROGRAM PASSED`, `Chain programming PASSED`, 56 s.
- Programmed **Fabric digest `A77DCEAD3DE3ECC32399CF83AF8F696A295CE449733B76FF0B8A5881A8F687B6`**
  == the export digest byte-for-byte → exact two-slot fabric on silicon.
- sNVM digest `C011B109…` (unchanged); programs Fabric + sNVM only (eNVM/HSS/U-Boot/Linux/SD untouched).
- Device on chain: IDCODE `1F81A1CF`, Production MPFS250T ("Scan and Check Chain PASSED").
- Program log: bee `seed7_vbx201_v250/two_slot_reports/program.log`.

**Kit auto-booted after programming** — no power-cycle was needed for reachability;
`ssh icicle` (192.168.x.x) up, PCIe `status=disabled` (0 microchip-pcie probes,
no boot-loop), `vbx-overlay.service active`, `/dev/uio2 = vbx@60030000`.

**Rung F currently FAILS (V250 inference):**
- VERSION `0x60030028` = **`0x20000000`** (V250 / major 2 — IP is present, control plane alive).
- But `vbx_probe`: **`CTRL=0x10` (CTRL_REG_ERROR), `ERR=0x1`, `error_val=1`**, `RESULT: ERROR`;
  `vnnx_smoke`: `model_start refused (state FULL/ERROR), err=1`.
- **`error_val=1` decodes to `INVALID_FIRMWARE_ADDRESS`** (vbx_cnn_api.h enum) — the V250
  cannot validate/reach its firmware blob in DDR.
- `udmabuf-ddr-nc0` phys_addr = **`0xc8000000`**, identical to the working rung-F baseline
  (size 32 MiB) — so the staging address itself is NOT the problem.
- A **warm Linux `reboot` did NOT clear it** (error persists; the runtime's CTRL soft-reset
  in `vbx_cnn_init` also does not clear it) → fabric-level, not Linux state.
- **Key context:** the V250 has only ever been verified working *after a cold power-cycle*
  (the 2.0.1/V250 rebuild was programmed → MSS halted → user power-cycled → then it worked).
  This program got a *warm* auto-boot, so the V250 has **never been cold-initialized** on
  this bitstream — the most likely missing step.

## NEXT SESSION — exact first step

1. **Cold power-on the kit** (already being done at pause). Wait ~60 s for autonomous boot.
2. **Re-run Rung F non-regression** (do this BEFORE touching PID/Rung E/G):
   ```
   ssh icicle 'cd /root/bringup && ./vbx_probe fcnn_v2_residual_dataset_a.vnnx'   # want RESULT: INFERENCE COMPLETED
   ssh icicle 'cd /root/bringup && timeout 20 ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx'  # want out[0]=-2.9506
   ```
3. **If Rung F passes** → cold-init was the issue. Proceed to Rung E:
   - apply the new overlay `firmware/linux/two_slot_vbx_pid.dtso` (pidsub@60040000),
     cross-build `firmware/linux/pid_ctl.c`, then bounded write/read on
     gains `0x60040000`/CSR `0x60040800` (NO wedge expected — both decoded clean).
4. **If Rung F STILL fails after cold power-on** → real V250 regression in the two-slot
   fabric. Diagnose the V250 M_AXI→DDR path (only V250-subsystem change was routing
   `core_vectorblox_C0_0.output_valid` to the watchdog; the re-P&R re-placed the V250).
   If not quickly fixable, **roll back** (below), then re-spin.

## Rollback (preserved — do NOT overwrite; verified on bee + NAS this session)

| Build | sha256 | bee | NAS |
|---|---|---|---|
| **V250-rebuild (working V250, recommended)** | `4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e` | `seed7_vbx201_v250/export/polarfire_hybrid_control_vbx201_v250.job` | `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control_vbx201_v250.job` |
| **seed_7 rung-A** | `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a` | `dev/projects/polarfire-hybrid-control/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job` | `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control.job` |

Rollback = program either `.job` via the operator-mode flow
(`libero/scripts/program_kit.tcl` points at seed_7; for the V250-rebuild edit JOB_FILE),
then the kit auto-boots. The boot-time PCIe-disable lives in the U-Boot env
(bitstream-independent), so any of these boots Linux without the PCIe boot-loop.

## Environment state at pause
- No Libero/FPExpress/Synplify/programming jobs running on bee (verified).
- All synth/P&R/program background jobs completed cleanly (exit 0).
- bee project `seed7_vbx201_v250` holds the two-slot generated netlist + reports;
  `.pre_two_slot.bak` backups of the 3 patched files are in `component/work/**`.
- Did NOT: start a new build, reprogram, roll back, or run Rung E/G (per instruction).
