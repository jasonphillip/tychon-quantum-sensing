# Two-Slot Integration — end-of-day handoff (2026-06-17)

Branch `bringup/2026-06-17-two-slot-pid`. Paused for the day; the kit is being
fully powered off (a **cold power-cycle**, which is the intended next-session
discriminator — NOT a failure/rollback). Evidence labels per
`docs/agent_ground_truth_contract.md`.

---

## UPDATE 2026-06-18 — cold-cycle results: Gate F PASS; Rung E M0 defect; kit needs power-cycle

**Goal #1 ANSWERED — YES.** After the overnight cold power-cycle, Rung F V250 inference is
**RESTORED** on the two-slot bitstream. Cold-init hypothesis **CONFIRMED**; the warm-after-program
`INVALID_FIRMWARE_ADDRESS` was a V250 POR artifact, **NOT a two-slot regression**. No rebuild,
no reprogram performed.

### Gate F — PASS (CONFIRMED, live silicon ~12:15)
`ssh icicle /root/bringup/vbx_probe fcnn_v2_residual_dataset_a.vnnx`:
- after_start `CTRL=0x04` (RUNNING), `MODEL=0xc8000400`, `IO=0xc8000000`; poll done; `error_val=0`;
  `RESULT: INFERENCE COMPLETED`. `VER=0x20000000`.
- `vnnx_smoke` → `inference complete. / out[0]=-2.9506` (scale 0.022873, zp 1) — exact match to the
  2026-06-16 known-good V250 baseline.
- Pre-checks green: uptime 29 min (fresh cold boot), PCIe `disabled` / 0 microchip-pcie probes,
  `vbx-overlay.service active`, `uio2=vbx@60030000`, udmabuf `0xc8000000`/32 MiB.

### Rung E — M1 (pid_csr) CLEAN; M0 (gains) read-path DEFECT (CONFIRMED)
Built + deployed `pid_ctl` (kit sha256 `161211c1…`, from spark1 `pid_ctl.c` `fdabd192…` via bee
cross-gcc; controlled per-file copy, no bee branch switch/pull).
- **M1 `pid_csr` @ 0x60040800: reads COMPLETE cleanly.** `pid_ctl r 0x60040804` → `0x00010000`
  (csr_version). The SLAVE3 crossbar slot decodes + completes — the clean two-slot integration is
  alive on the M1 sub-slave.
- **M0 `nv_pid_top.axi4target` gains @ 0x60040000: read does NOT complete.** `pid_ctl r 0x6004000C`
  (Kp) hung (host `timeout` 124) → non-completing AXI read on the M0 branch of `axi4_demux2` →
  wedged a U54 hart → **kit went fully off the LAN** (ARP `FAILED`, MAC absent from a full /24
  sweep; did NOT auto-recover via watchdog reset in ~6 min). **Kit now requires a physical
  power-cycle.**
- **HYPOTHESIS (most likely):** a defect on the **M0 read path** of the hand-written `axi4_demux2`
  — R-channel / RID handshake (nv_pid_top 1-bit ID padded to the 9-bit demux side) or SmartHLS
  `ap_ctrl` gating. M0 was never read-tested on silicon before today; the 2026-06-17 "both decoded
  clean" was an expectation — now **FALSIFIED for M0 reads** (M1 reads stand confirmed clean).
- **Blast radius is bounded:** Rung G (`tools/rung_g_replay.py`) and the "clean PID CSR" demo use
  **only M1** (0x60040800+); they never touch M0. The demo path is intact once the kit is back.

### RESUME STEPS (after the kit is power-cycled — a COLD off/on, same as this morning)
1. Power-cycle restores the healthy two-slot state (bitstream/U-Boot/SD untouched; Rung F was
   confirmed working). Wait ~60–90 s for autonomous boot; reconnect `ssh icicle`.
2. Re-verify Rung F (`vbx_probe`) still `INFERENCE COMPLETED`.
3. **Rung E on M1 ONLY — NEVER touch M0 (0x60040000–0x600407ff, incl. `acc_start` 0x60040008).**
   All timeout-wrapped: `axi_write_count` (0x60040800), shadow-gain write/readback (0x60040820+),
   inject error (0x60040810/814) + u_ai (0x60040818), read `post_clamp_out` (0x60040844)
   before/after to test datapath liveness, `watchdog_csr` (0x60040854).
4. Rung G: dry-run, then on-silicon (M1 only). Label **"silicon PID + host-provided NN feedforward
   telemetry"** (NN is a host surrogate, not live per-row V250).
5. **M0 fix is a deferred RTL/demux item (requires a rebuild)** — out of scope until explicitly
   chosen; not needed for the M1-based demo.

### 2026-06-18 (cont.) — kit power-cycled & recovered; Rung E (M1) + Rung G COMPLETE; M0 root-caused

Jason cold power-cycled the kit; it recovered autonomously (uptime 0, **4 CPUs** — wedged hart
cleared, PCIe disabled, vbx-overlay active, udmabuf `0xc8000000`). **Rung F re-verified PASS**
(2nd cold boot: `INFERENCE COMPLETED`, `out[0]=-2.9506`).

**Rung E — M1 (`pid_csr`) FULLY VALIDATED on silicon (CONFIRMED):** `csr_version=0x00010000`;
`axi_write_count` monotonic (0→9, exactly the 9 M1 writes issued); shadow-gain write/readback
bit-exact (0.5→`0x8000`, 0.25→`0x4000`); `watchdog_csr=0x07` (bit0 timeout + trip count 3 —
watchdog LIVE). The clean-two-slot host-control-plane survival proof, on a real decoded crossbar slave.

**M0 live-actuator gating — ROOT-CAUSED (CONFIRMED, source):** `post_clamp_out` stays 0 for any
injected `error`/`u_ai`. Cause: `hls/src/nv_pid.hpp:21` constructs `NVPID` with `out_min(0),
out_max(0)`, and `compute()` clamps the final output to `[out_min,out_max]` → `[0,0] ≡ 0` until
those limits are set. `out_min/out_max` are written via the **M0 gains slave** (0x60040018/
0x6004001C) — the wedging slave. So a nonzero **live** actuator cannot be shown on this bitstream
without writing M0 (which wedges). (Compounded by the watchdog being timed-out → u_AI disabled by
the bumpless fallback.)

**Rung G — telemetry produced (HONEST LABELS):**
- DRY-RUN (software FakeKit): `sim/rung_g/rung_g_dryrun_2026-06-18.{csv,jsonl,png}` — 120 samples,
  16 clamp-active; the dashboard shape (PID-only vs PID+NN, clamp/watchdog flags).
- ON-SILICON (M1-only, 30 rows): `sim/rung_g/rung_g_silicon_2026-06-18.{csv,jsonl,png}` — REAL
  per-row hardware liveness: `axi_write_count` +4/row (13→129), `csr_version=0x00010000` every row,
  watchdog read live (timeout=1, `PID_ONLY_FALLBACK` all rows). `actuator_out=0` (M0-gated). i.e.
  **"silicon PID-subsystem CSR liveness + host-provided NN feedforward telemetry"** — NOT a live
  silicon closed-loop actuator (needs the M0 fix).

**Net:** Rung F ✅ (cold-init). Rung E M1 ✅; live actuator ⛔ M0-gated. Rung G dashboard ✅ (software)
+ silicon CSR-liveness ✅. Two-slot fabric is sound **except the M0 (gains) read path**.

**DECISION FOR JASON (product/strategy):** a live silicon closed-loop actuator needs either an
**M0 fix** (RTL/demux respin → rebuild) or a **write-only M0 attempt** (risky — may wedge again).
Options in the 2026-06-18 session summary.

→ **CHOSEN (Jason, 2026-06-18): Option 1 — accept the proven scope; NO M0 access this session
(read or write); the M0 fix is deferred.** Demo scope (exact honest wording), evidence, and the
M0 deferred-RTL follow-up path are captured in **`docs/two_slot_demo_scope_2026-06-18.md`**.

---

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
