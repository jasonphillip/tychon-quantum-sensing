# 2 ms Watchdog Programming Recovery Record - 2026-06-21

## Image Hashes

New 2 ms watchdog job:

```text
7956a169d4b1c6f44fce1aee907dc416b039ce16ac532f46b4e1d7e53d68969a  polarfire_hybrid_control_two_slot_2ms.job
```

Rollback jobs available in the same export directory:

```text
39c8bcf2665ce8b79bcc2abb552ddd2b7b703729d50876744c2cb63c82ca230b  polarfire_hybrid_control_two_slot_idfix2.job
7907a83f9fc6e99ca25ebc3c389c802d6d07e42b71403767ee644103783dff6e  polarfire_hybrid_control_two_slot_idfix.job
a5550f9e486e19f127aad78e97e06e0839d359c91028d4bcd21bb32b98f5b367  polarfire_hybrid_control_two_slot_demo.job
4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e  polarfire_hybrid_control_vbx201_v250.job
```

## Pre-Program Chain Visibility

Command:

```bash
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
  SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/scan_chain_2ms_preprogram.tcl" \
  LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/scan_preprogram_2ms.log"
```

Result: `Scan and Check Chain PASSED` on embedded FP6 `F31E000A`; device IDCODE `1F81A1CF`; part `MPFS250(T|TS|TL|TLS|TC)`.

## Program Command

```bash
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
  SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/program_job_2ms.tcl" \
  LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/program_2ms.log"
```

## Exact Rollback Command

Rollback target: known-good idfix2 job, sha256 `39c8bcf2665ce8b79bcc2abb552ddd2b7b703729d50876744c2cb63c82ca230b`.

```bash
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
  SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/program_job_idfix2_rollback.tcl" \
  LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms/rollback_idfix2_program.log"
```

## Notes

- The new job export log says the generated bitstream programs Fabric and sNVM.
- Dashboard kit loop was stopped before programming prep.
- Do not use M0 base `0x60001000`; dashboard/live validation remains on the idfix2-safe `0x60040000` page.
