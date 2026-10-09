# Rung F — V250 (CoreVectorBlox 2.0.1) Rebuild: Post-Program Handoff (2026-06-16)

> **✅ RESOLVED later 2026-06-16 — see `docs/rung_f_v250_on_silicon_results_2026-06-16.md`.** The kit
> was reached via bee serial (it was boot-looping, not dead). VERSION `0x60030028`=`0x20000000`
> (V250/major2); `vbx_probe` → INFERENCE COMPLETED (3/3); `vnnx_smoke` → `out[0]=-2.9506`. The
> "can't reach the kit" blocker below was the Linux **fabric-PCIe probe hang** (`microchip-pcie` @
> `0x3000000000`) → silent boot → 28 s watchdog loop; worked around by booting with the PCIe DT node
> disabled. bee Libero vault reverted to `C:/Microchip/Common/vault` (`change_vault_location` OK).

**Read first:** the root-cause analysis + fix rationale is in `docs/rung_f_decerr_handoff_2026-06-16.md`
§7.2 / §7.3. This file is the **post-program** handoff: the fix bitstream is built and **programmed
(PASS)**, the kit was power-cycled, and we are blocked only on **reconnecting to the kit** to run the
decisive on-silicon verification. Do not continue in the prior high-context session.

Evidence labels per the wiki evidence-discipline rule (CONFIRMED = verified against live artifact/log
this session; PENDING = not yet observed).

---

## Why this rebuild (one line)
The rung-A seed_7 bitstream shipped the **wrong NPU IP — CoreVectorBlox `1.1.12` / size `V500`** —
while the software stack (SDK 2.0.3 runtime + `-c V250` `.vnnx`) targets **`2.0.1` / `V250`**. That
version+size mismatch is why inference latched START but never advanced (`docs/rung_f_decerr_handoff_2026-06-16.md`
§7.2, CONFIRMED from the generated `.cxf` + the live VERSION register). This rebuild swaps the IP to
2.0.1/V250 to fix it.

## CONFIRMED this session

- **New bitstream built** from the isolated clone `~/libero_seedsweep/seed7_vbx201_v250`
  (project `MPFS_ICICLE_Vectorblox.prjx`; rung-A seed_7 left untouched). Changes:
  - `core_vectorblox_C0` → **2.0.1 / PRESET:0 (V250)**, 128-bit M_AXI — CONFIRMED in generated
    `core_vectorblox_C0.cxf` (`version="2.0.1"`, `PRESET value="0"`).
  - `vectorblox_axi_resize` (COREAXI4INTERCONNECT 2.9.100) `ID_WIDTH:3→4` to match the 2.0.1 core's
    4-bit M_AXI ID (the documented porting step). SmartDesign instances refreshed
    (`sd_update_instance`) bottom-up (Vectorblox_ss → FIC_0_PERIPHERALS → MPFS_ICICLE_KIT_BASE_DESIGN);
    `build_design_hierarchy` clean.
  - **Timing CLOSED: worst slack +0.848 ns** (multi-pass seed 28; "Timing constraints have been met").
- **Job artifact (CONFIRMED):**
  - Path: `~/libero_seedsweep/seed7_vbx201_v250/export/polarfire_hybrid_control_vbx201_v250.job`
  - sha256: `4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e` (12,126,232 B)
  - Programs **Fabric + sNVM only**; **eNVM NOT generated/programmed** (`Warning: Bitstream not
    generated for eNVM`) → HSS/U-Boot/Linux/SPI/eMMC/SD untouched.
- **PROGRAM PASS (CONFIRMED)** via FPExpress (`/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe`,
  operator mode, PROGRAM action) on the new job:
  - `JOB_PATH_VERIFIED new-V250-job` (guardrail: programmed the new job, not the rollback), `STEP1_OK`,
    `STEP2_OK_chain`, **`PROGRAM_PASS`**.
  - `programmer 'F31E000A' : Scan and Check Chain PASSED`, `ISC_ENABLE_RESULT 00000000`, `CRCERR 00`,
    `device 'MPFS250T' : Executing action PROGRAM PASSED`, `Chain programming PASSED`.
  - **Fabric component bitstream digest: `22A40FC163EC6A54A7465E4E61015D5FEA63E12FBC6A3BB978BCD493964D5974`**
    (matches the export digest → programmed fabric == the built V250 fabric; differs from rung-A `0769…`).
  - sNVM digest `C011B109…`; entire-bitstream digest `671C8472…`.
  - Program logs on bee: `~/program_vbx201_stdout.log`, `~/program_vbx201_fpx.log`.
- **Power-cycle required + done.** Post-program the MSS was halted (not pingable, mDNS down, HSS serial
  console COM8 silent for 5 s) — expected after an Icicle JTAG fabric reprogram. **User power-cycled the
  kit and reported it is fully up.**

## CURRENT BLOCKER (where the next session starts)
- **Cannot reach the kit.** `mpfs-icicle-kit.local` mDNS does **not** resolve from spark1 (retried),
  and the old lease **`192.168.x.x` is stale** (the kit got a new dynamic DHCP IP this boot).
- **DO NOT mass-scan or key-probe the shared subnet** (192.168.x.x/24). A blanket SSH-key probe was
  attempted and correctly blocked — do not repeat it.

## NEXT ACTIONS (in order)
1. **Find the kit's current DHCP IP** by an in-scope method:
   - **bee COM10 Linux serial console** (MMUART1 = COM10 = `/dev/ttyS9` on bee; 115200 8N1) — the boot/
     login banner / `ip addr` shows the IP; or
   - the **router DHCP lease table** (Verizon CR1000A, 192.168.x.x); or
   - **user-provided IP**.
   (The `icicle` ssh alias is `root@mpfs-icicle-kit.local`, key `~/.ssh/id_ed25519`,
   `StrictHostKeyChecking no` — use it if mDNS recovers; else `ssh -i ~/.ssh/id_ed25519 root@<IP>`.)
2. **Read CoreVectorBlox VERSION at `0x60030028`** (via `/dev/mem`, page `0x60030000`, word 10).
   **Expected (the decisive gate): `size_config=0` (V250) and `major=2`** → confirms the 2.0.1/V250
   swap took on silicon. (Old/wrong was `0x10010100` → V500/major1.)
3. If VERSION confirms V250/major2: ensure the runtime overlay is applied (`/dev/uio2` = `vbx@60030000`;
   re-apply `/root/bringup/seed7_vbx_pid.dtbo` via configfs if not), then run **bounded `vbx_probe`**
   (`/root/bringup/vbx_probe fcnn_v2_residual_dataset_a.vnnx` — internally bounded ≤600 polls) — the real
   test: does inference now advance past `CTRL=0x02` to RUNNING/OUTPUT_VALID? Then **bounded `vnnx_smoke`**
   (wrap in `timeout`; its poll loop is otherwise infinite) and record dequantized outputs.
4. **Revert the global Libero vault on bee** to `C:/Microchip/Common/vault` (it is currently pointed at
   the MegaVault — `change_vault_location` — set during the swap to source 2.0.1) and verify the setting.
5. **Update docs/wiki** with the on-silicon result (latency now measurable for the first time;
   `[NC]` 100/200 vs 75/150 de-rate becomes checkable).

## ROLLBACK (unchanged, CONFIRMED)
- Trusted rung-A seed_7 `.job`: `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control.job`,
  sha256 `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a`.
- Reprogram via the operator-mode PROGRAM flow in `libero/scripts/program_kit.tcl` (it points at this
  rollback `.job`). Use only if the V250 build proves bad on silicon.

## ENVIRONMENT STATE / CLEANUP NOTES
- **bee global Libero vault = MegaVault** (`C:/Microchip/.../MegaVault/Libero_SoC_v2025.2_MegaVault`) →
  **revert to `C:/Microchip/Common/vault`** (action #4 above). This is a global, all-projects setting.
- Clone project `seed7_vbx201_v250` retained on bee for re-runs; staged Tcl on bee:
  `recfg_vbx4.tcl` (core swap), `recfg_resize.tcl` (ID_WIDTH:4), `recfg_cascade.tcl` (SD update),
  `build_vbx201.tcl` (synth/P&R/timing), `export_job.tcl`, `program_vbx201.tcl`.
- All background watchers from the build/program session were stopped at handoff.

## STILL PENDING (not yet observed on silicon — do not claim until verified)
- VERSION = V250/major2 on silicon.
- Inference advancing past START (the actual rung-F success criterion).
- On-silicon latency figure.
