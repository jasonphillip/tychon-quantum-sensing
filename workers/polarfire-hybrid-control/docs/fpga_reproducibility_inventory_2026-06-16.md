# FPGA Reproducibility Inventory (2026-06-16)

This file answers: can a future session reproduce the FPGA programming and
model-deploy workflow without rediscovering the whole bring-up history?

## Ledger Sources

- Project state and programming runbook: `docs/track0_bringup_runbook.md`.
- On-target Linux evidence: `firmware/linux/reports/2026-06-15-bringup/rung_cdef_results_2026-06-15.md`.
- Programming script and proof log: `libero/scripts/program_kit.tcl`,
  `libero/reports/2026-06-15-program/program.log`.
- Model provenance: `models/README.md`.
- External decision ledger: `~/projects/tychon-sbir/docs/03_phase1_planning/decision_log/tychon_phase1_decision_log_v1.3_2026-05-02.md`
  through DLOG-055.
- Shared wiki project state: `~/shared/wiki/projects/polarfire-hybrid-control/README.md`.

## Known-Good Programmed Bitstream

Seed/design: `MPFS_ICICLE_Vectorblox.prjx`, seed_7 r6_s25 closure.

Programming artifact:

- Beelink repo path: `~/dev/projects/polarfire-hybrid-control/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job`
- NAS backup: `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control.job`
- sha256: `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a`
- Target: Production `MPFS250T-FCVG484E`
- Program evidence: `libero/reports/2026-06-15-program/program.log`
- On-silicon fabric digest from program log:
  `07691012481460800402377C4342DF4936432271E80C03E3248F9D3A06C03DF8`
- On-silicon sNVM digest from program log:
  `EBF80EDE6776E1B3C053FA31A33F8414E61E9F4D01778BEBBC2BD8F363D32507`

To reprogram the known-good bitstream on bee:

```bash
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
  SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/scripts/program_kit.tcl" \
  LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/$(date +%Y-%m-%d)-program/program.log"
```

Do not replace the seed_7 board image with a new bitstream unless the new build
is on a branch, timing/power/programming artifacts are archived, and rollback to
the seed_7 `.job` remains available.

## Changing Only The Model

This path is reproducible enough.

1. Produce an INT8 TFLite in `odmr-edge-ml`.
2. Copy it to bee.
3. Compile with VectorBlox SDK v2.0.3 in Beelink WSL:

```bash
ssh bee "wsl -d Ubuntu -u jason -- bash -c '
  source ~/vbx-env/bin/activate &&
  cd /tmp &&
  vnnx_compile -c V250 -t <model>_int8.tflite -o <model>.vnnx
'"
```

4. Copy the `.vnnx` back to `models/`.
5. Update `models/README.md` with source TFLite path, file size, sha256, SDK
   version, and exact compile command.
6. Copy the `.vnnx` to the kit and run from `/root/bringup` with
   `./vnnx_smoke <model>.vnnx` after the current Rung F blocker is cleared.

The canonical current artifact is `fcnn_v2_residual_dataset_a.vnnx`, 12,832
bytes, sha256
`6c5cd21ae9d4ce9793f8bc143c2c53d564140bde3df1fda1ec08a5a1602512eb`.

## Changing The Bitstream

This path is partially reproducible but still higher risk.

What is solid:

- The tool host is bee: Libero SoC 2025.2 + SmartHLS 2025.2.
- The known-good programming script is captured in `libero/scripts/program_kit.tcl`.
- The seed_7 closure identity and on-silicon digests are captured.
- The branch-only rule is clear: do not overwrite the rung-A seed_7 fallback.

What is not yet a one-command recipe:

- The active seed_7 project lives under `~/libero_seedsweep/seed_7/`
  and is not reconstructed solely from the repo Tcl scripts.
- `libero/scripts/03_smartdesign.tcl` still contains older FIC mapping comments
  and should not be trusted as the canonical representation of seed_7.
- The clean two-slot integration is documented in
  `docs/smartdesign_two_slot_canvas_runbook.md`, but it is not yet
  netlist-validated.
- New bitstreams need a fresh closure package: timing reports, `.job`, sha256,
  program log, on-silicon digest, and a decision-log entry.

Recommended next reproducibility improvement: create a branch-only
`docs/new_bitstream_release_checklist.md` that requires artifact paths, timing
slack, source project path, `.job` sha256, program command, program log, digest
readback, rollback path, and DLOG/wiki updates.

## Current Open Hardware State

CONFIRMED:

- Production kit programming works.
- SD Linux boot works.
- MMUART0/HSS = COM8, MMUART1/Linux = COM10.
- `/dev/udmabuf-ddr-nc0` exists at physical `0xc8000000`.
- V250 control plane responds at `0x60030000`.
- The stock SDK runtime and custom smoke test both stall at START on seed_7.
- Rank-1 read-only diagnosis exonerated the MSS-side FIC2 path at register
  level: MPU3 is open with STATUS failed=0, SEG1 maps `0xc8000000` correctly,
  FIC2 clock is enabled, FIC2 soft-reset is deasserted, and the resize bridge
  preserves a 38-bit address.

STALE/RISKY until the active Rung F diagnosis completes:

- Any root-cause claim for the V250 stall.
- The single async SmartDebug `RRESP=0b11` DECERR snapshot; downstream
  MSS-side DECERR causes have now been checked and are not supported.

Known unsafe action:

- Do not read/write `pid_poke` against `0x60001000` on seed_7; it can wedge a U54
  core and require power-cycle.
- Do not run the proposed MPU3 deny-all address logger without explicit approval;
  it is designed to be reversible and scoped to FIC2, but it is still an MSS
  register write.
