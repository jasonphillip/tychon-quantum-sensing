# DISPATCH → nv-sensor-sim session: `sequence_train_v2` (~4× scale)

**From:** TVW orchestration session, 2026-07-02. **Approved by Jason.**
**Trigger:** the tracking repo's standing decision rule fired — the B3 motion prior was a
clean negative (improves val, regresses the closed-loop matrix; tracking commit 1a3e787),
so the identity gap persists after the architecture lever and the next lever is data scale.

> **BOUNDARY (standing TVW rule):** Do NOT touch the slide deck, email drafts, or any
> outreach surface — those are TVW-only, and emails send only on Jason's explicit go.
> Deliver data + manifest + lineage in this repo. Do NOT push to GitHub without Jason's
> OK (nas push is fine). Do NOT run `vnnx_compile` or anything on bee — out of scope here.

## What to build

`sequence_train_v2`: same physics, same recipe, same contract as `sequence_train_v1` —
**~4× the sequences, new disjoint seeds**. No recipe changes; v2 is a scale run, not a
redesign. Deltas from v1 are listed explicitly below; everything not listed is IDENTICAL.

- **Scale:** 3072 sequences × T=256 (train/val/test = 2048/512/512). v1 was 768 (512/128/128).
- **Seeds:** new, disjoint from v1's. Record the seed range in the manifest and lineage table.
- **Identical to v1 (do not drift):**
  - Pinned v0 grid, bit-identical: F=951, `freq_range_Hz` override
    `[2667390522.8636284, 3074609477.1363726]`.
  - Trajectory family mix ≈50/25/25 hold-ramp-hold / reversal-in-dwell / OU-perturbed.
  - ±1.4 mT envelope (grid-pin forced), min-|proj| ≥ 0.4 mT rejection.
  - Per-axis contrast ladder [1.0, 0.85, 0.7, 0.55] + seeded AR(1) drift (0.05, window 64).
  - **Measurement noise stays OUT of stored data** — consumers apply
    `nv_sensor_sim.physics.shot_noise` (0524686) at train/eval time.
  - Contract v1 HDF5 layout (`docs/dataset-contract.md` "HDF5 Layout — Time-Series"),
    `contract_version: "v1"` stamped, top-level `/bias`, diagonalized `resonance_freqs`,
    `line_axis`/`line_transition`/`collision_mask`/`line_collision`/`seeds`.
- **Manifest stats + lineage:** same stats block as v1 (family counts, collision counts,
  contrast/drift realization stats, rejection counts) + a lineage-table entry with the v1→v2
  delta ("4× scale, new seeds, recipe frozen").

## Pre-flight (required before the full run)

Per the standing long-job rule: (1) dry-run a 10-sequence slice; (2) report estimated wall
time and output size for 3072×256 (v1 took a known time — scale it); (3) verify the slice's
manifest stats look like v1's per-family distributions before unleashing the full run.
If the full run exceeds ~30 min, run it `nohup` + pidfile with periodic progress lines.

## Report back (to Jason, for TVW)

Commit hashes (data lineage + generation log), manifest stats summary, family/collision
counts vs v1 expectations, wall time, output path + size, nas mirror status. One paragraph,
numbers first. The tracking session's retrain dispatch (`dispatch-2c-v2-retrain-2026-07-02.md`)
consumes your output path — state it exactly.
