# Safety Export-Unverified Probe - 2026-06-21

Purpose: clone-only probe to test whether Libero can generate programming data
and export a deliberately quarantined job from the safety-direct P&R state after
prior `VERIFYTIMING` failed with `not ROUTED_CONNECT`.

Remote clone:
`~/libero_seedsweep/seed7_vbx201_v250_safety_export_unverified_20260621_1120`

Command:

```sh
ssh bee 'cd ~/libero_seedsweep/seed7_vbx201_v250_safety_export_unverified_20260621_1120
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/libero.exe "SCRIPT:~/libero_seedsweep/seed7_vbx201_v250_safety_export_unverified_20260621_1120/export_unverified_from_pnr.tcl"'
```

Result:

- The script intentionally skipped `VERIFYTIMING` and attempted
  `GENERATEPROGRAMMINGDATA`.
- Libero warned about generating FPGA array data without all IOs assigned and
  locked.
- Generation then emitted a large stream of `Incorrect XY loc (384434489, 32766)`
  errors tied to the same broken routed database family seen in timing.
- The probe was manually interrupted after the failure mode was clear.
- No safety job was exported.

Conclusion: the safety-direct P&R database is not usable for job export. This
bundle is evidence only and contains no programming candidate.
