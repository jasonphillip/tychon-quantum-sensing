# 2026-06-21 Safety Build Attempt

Status: ATTEMPTED, NOT A PASS.

A cloned seed directory on bee was patched for a 1 ms watchdog safety-spec image:

```text
~/libero_seedsweep/seed7_vbx201_v250_safety_20260621
WATCHDOG_TIMEOUT_CYCLES=125000
```

The run entered Synplify/map setup and then stopped making progress. Only the cloned run was stopped. No safety `.job` was exported, and no programming was performed.

Contents:

- `MANIFEST.txt` - commands, proof lines, and source/clone paths.
- `safety_synth_20260621.log` - Libero run log.
- `synplify.log` - Synplify log.
- `MPFS_ICICLE_KIT_BASE_DESIGN.srr` - Synplify report from the attempt.
- `MPFS_ICICLE_KIT_BASE_DESIGN_cck.rpt` - clock/check report from the attempt.
- `SHA256SUMS` - hashes for this bundle.
