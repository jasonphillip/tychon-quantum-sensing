# Dispatch — nv-sim `sequence_train_v3`: angular/magnitude field-coverage lineage + fieldcone eval

**Target session:** `~/projects/nv-sensor-sim/` on **spark2** (all compute local).
**Issued:** 2026-07-07, from the increment-5 coverage finding (odmr `docs/increment5_results.md`
+ `experiments/increment5_coverage_split.py`, main dde2a74) and TVW
`audit-dwell-program-2026-07-07.md`.
**Status note:** this RATIFIES and SUPERSEDES the `sequence_train_v3` request relayed to this
session earlier today via the odmr lane (channel error, reconciled — see the audit §5). The
technical content of that request stands; this dispatch resolves the design forks the session
raised at its clarification gate, and adds Deliverable 2 (the held-out fieldcone eval). If a v3
design doc has already been drafted from the relayed text, reconcile it against this file —
this file wins on conflicts.
**Mode:** run end-to-end without user assistance; stop-and-report conditions below.

## Why

Increment-5 discovered a **deterministic training-coverage gap in the field claim**: cold field
acquisition fails 216/216 (all 3 seeds, every dwell length, both exit topologies) on merge
geometries requiring **41–53° off-bias at 3.3–3.9 mT** — jointly outside the v1/v2 training
envelope (≤18° off-bias, |B| ≈ 4.7–5.8 mT) on both angle and magnitude. In-envelope geometries
never fail (0/216). This is now the **top program lever**, ahead of all identity mechanisms.
v3 attacks it with training data; the fieldcone eval makes the post-retrain boundary measurable
and keeps the claim honest.

## Deliverable 1 — `sequence_train_v3` (train/val)

**Contract v1. 951-pt pinned grid** (`freq_range_Hz` read from the v1 manifest, not re-derived).
**Same deployment prior**: `bias_direction_uvw` and B0 = 5 mT bias pinned to the v1 manifest
values — the bias geometry does not change; what widens is the **external/target field
trajectory envelope**. Same per-axis contrast ladder + AR(1) drift as v1/v2; T=256; stored
noiseless (measurement noise stays consumer-side).

**Envelope extension:** off-bias angular coverage to **≥60°** and |B| floor to **~3.0 mT**
(ceiling unchanged), explicitly including the template-2/3 degeneracy geometries
((0,2)/(4,6) merge directions and their symmetry siblings at their required field points).

**Sampling design — FORK RESOLVED: hybrid (the session's option 1):**
1. **Majority (~70–75%): grid-guarded isotropic widen.** Existing trajectory families
   (held/ou/reversal per the v1/v2 recipe) drawing larger off-bias scalars, with a
   reject-and-redraw **window-containment guard** (all 8 lines inside the pinned 951-pt window
   at every frame) and the existing min-per-axis-|B∥| guard unchanged.
2. **Minority (~25–30%): directed merge sub-population** aimed along the (0,2)/(4,6) merge
   directions and symmetry siblings, reusing the dwell lineage's `merge_direction`/`a_merge`
   machinery, **v1-style pass-through crossings only** — FORK RESOLVED: **no long dwell holds
   in v3** (dwell-hold training data belongs to the future cue-retrain lineage; mixing it here
   would confound the coverage-retrain attribution).
3. Record per-sequence **`sampling_family`** (isotropic-widened vs directed), realized max
   off-bias angle, and min |B|; manifest histograms of both + rejection-rate stats. This
   preserves post-hoc attribution (did the fix come from directed density or the wider
   envelope?) and lets the consumer build coverage splits.

**Scale/split — FORK RESOLVED:** match v2's sequence count and train/val split recipe exactly
(~4× v1), **fresh seeds disjoint from v1/v2/dwell**. Holding size and recipe fixed makes the
increment-6 retrain a controlled comparison — the only variable is coverage. No test split
(eval lives in the dwell eval + Deliverable 2).

**Cues — FORK RESOLVED: config-only.** Commit the seed-paired `_cues` variant **config**
(strain Meneses defaults + 3.8 ppm CR, as in the dwell lineage) so a later cue-retrain can be
generated reproducibly, but **do NOT generate cues-on data now** — the CR dip guard-tripped the
current checkpoints and the cue retrain needs its own dispatch, unconfounded with coverage.

## Deliverable 2 — `sequence_eval_fieldcone_v1` (eval-only, held out)

Purpose: (i) confirm post-v3 that the 216/216 failure clears; (ii) chart the NEW acquisition
boundary as a function of (off-bias angle × |B|); (iii) probe generalization BEYOND the v3
training envelope. Design intent (exact bucketing is the session's call):

- A grid of (off-bias angle × |B|) buckets spanning roughly **10°→75° × 2.5→5.5 mT**, and it
  must include: the exact template-2/3 failure geometries (41°/3.9 mT, 53°/3.3 mT — same merge
  machinery as the dwell eval), an in-envelope control bucket, and **beyond-v3 probe buckets**
  (>60° and <3.0 mT) that stay OUTSIDE the v3 training envelope by design.
- ≥12 sequences per bucket, v1-style crossings, fresh seeds disjoint from everything above,
  eval-only. Keep total size modest (a few hundred sequences).
- Per-sequence fields: realized off-bias angle, min |B|, merge template where applicable.

## Pre-flight

1. Repo clean; note branch/HEAD in the run log. Branch **`feat/train-v3-field-coverage`** cut
   from `feat/dwell-identity-lineage` (cec6591 — you need its merge machinery and knob code).
2. Test suite green before changes; determinism check after (same seed → identical content md5,
   using the content-md5 convention from the dwell run log).
3. v1 pins (grid, bias vector, linewidth, contrast ladder) read from the archived v1 manifest
   via the nv-sensor-sim archive path (the odmr archive symlink is dangling — known).

## Handoff + wrap

- Datasets to nv-sim's standard output location, then copy to
  `~/projects/odmr-vector-tracking/data/` with md5s in each manifest and a handoff note
  (the established pattern). Do not touch tracking-repo code.
- Docs: lineage-table entry + dataset-contract addendum for any new manifest keys
  (`sampling_family`, realized-angle/|B| stats). Tests for the new sampler (guard behavior,
  directed aim correctness, family stats recorded).
- Commits on the feature branch, repo-style messages, specific-path adds. Push to NAS and
  **private GitHub** (both authorized; NAS by ~21:25 ET — don't block on it).

## Stop-and-report

1. Window containment is unachievable at the requested envelope on the pinned grid — report the
   achievable envelope; do not silently clip. 2. Reject-and-redraw rates make generation
   impractical (>10× redraw on any family) — report the binding guard. 3. Determinism fails.
4. Anything requiring a contract change, tracking-repo code, or a retrain.

## Out of scope

Cues-ON data generation (config only); dwell-hold training sequences; hyperfine L=24; DR /
amplitude ladder; any training; outward-facing material.
