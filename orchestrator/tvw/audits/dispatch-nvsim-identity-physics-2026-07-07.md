# Dispatch — nv-sim identity-physics lineage: dwell-sweep eval + physics identity cues

**Target session:** `~/projects/nv-sensor-sim/` on **spark2** (all compute local; spark1 is
decommissioned). This reopens the nv-sim lane closed 2026-07-02 — the closure listed
"open by design" follow-ons, and this is one of them. **Hyperfine (L=24) stays deferred** —
it is a contract change and is NOT part of this dispatch.
**Issued:** 2026-07-07, from the increment-4 verdict (tracking repo `docs/increment4_results.md`,
branch `increment-4-identity-overlay` 9b82aa1) and TVW
`tvw/audits/research-improvement-search-2026-07-06.md` + its 07-07 outcome addendum.
**Mode:** run end-to-end without user assistance; stop-and-report conditions below.

## Why (the increment-4 result this answers)

All zero-retrain overlay decoders failed on the held family, and the measured root cause is an
**information limit**: during a ~132-frame merged dwell, two lines sit within a linewidth and
neither the association scores nor the physics forward map can separate them — no better
read-out of the existing signal can recover identity. The remaining engineering path injects
**new measurement-space information into the data**, and the honest-claims path **quantifies the
recoverability boundary**. One dataset lineage serves both. Key physics hypothesis to enable
testing (not to assert): *a long merge destroys kinematic identity but lengthens the integration
time on any static differential cue* — ~132 frames of averaging is a ~11× SNR gain on a
persistent per-axis offset or contrast difference that is invisible per-frame.

## Deliverable 1 — `sequence_dwell_v1` (dwell-sweep eval set, cues OFF)

Eval-only dataset (no train split), **contract v1**, stored **noiseless** (measurement noise
stays consumer-side per the standing rule), **951-point grid pinned** via the existing
`freq_range_Hz` override, **same fixed bias geometry as v1/v2** (pin `bias_direction_uvw` to the
v1 manifest value — downstream architectures assume this deployment prior; state it in the
manifest), same per-axis contrast ladder + AR(1) drift as v1, T=256.

Trajectory design (held-template, parameterized dwell):
- Exactly **one coalescing line pair** per sequence: ramp-in → **merged dwell of D frames** →
  ramp-out → hold to sequence end. Merged dwell defined as |f_i − f_j| < 1 linewidth (Γ).
  D ∈ **{8, 16, 32, 64, 128, 192}** frames (target ±10% realized; record realized dwell).
- **Exit topology balanced 50/50 per D bucket: `cross` vs `bounce`.** This is load-bearing:
  if all merges cross (v1's independent-endpoint bias), a constant-velocity prior trivially
  decides identity and the eval measures prior-matching, not information. Bounce = the pair
  separates back to the sides it entered from (reversal-during-dwell). Record per-sequence
  `exit_topology` and `dwell_frames` (realized) as dataset fields.
- All six non-colliding lines separation-protected (min-separation rejection as in v1);
  min-|proj| rejection as in v1.
- Size: **24 sequences per (D, topology) bucket = 288 sequences** (Wilson CIs at the 2c
  granularity). Fixed, recorded seeds; deterministic regeneration (same seed → identical file).

## Deliverable 2 — physics-cue knobs (default OFF) + `sequence_dwell_v1_cues`

Two contract-compatible physics features, each behind a config knob, **default OFF** so
existing lineages are untouched:

1. **Per-axis static strain / E-field offsets** (`axis_offsets_hz`, default OFF; when ON,
   default magnitudes = the Meneses et al. real-device fit **(19.6, −4.2, −3.5, −11.9) kHz**,
   arXiv:2502.14683 — see tracking repo `docs/references.md`). Implement in the Hamiltonian /
   line-position model so the offsets flow into `resonance_freqs` ground truth automatically;
   document the sign convention and the interaction with the splitting-based decode in the
   dataset contract.
2. **NV–NV cross-relaxation** (`nv_density_ppm`, default 0 = OFF). Density-conditional PL
   feature at inter-orientation degeneracy — implement per the cited physics (Espinós/Budker
   arXiv:2512.13835 analytic resonance model; amplitude calibration anchor: Dhungel
   ~1.79% contrast / 0.78 mT width at 3.8 ppm, visible ≳0.9 ppm; sources in the 07-02 memo
   `tvw/audits/research-ml-optimization-levers-2026-07-02.md` Tier 5). **The physics
   implementation is this session's call — ground it in the cited sources; if the sources are
   insufficient to model it credibly, STOP and report rather than invent.** Primary value is
   realism + a merge marker; identity value is measured downstream, not asserted here.

Then generate **`sequence_dwell_v1_cues`**: identical kinematics and **identical seeds** as
`sequence_dwell_v1`, with cues ON (`axis_offsets_hz` = Meneses defaults; `nv_density_ppm` = 3.8,
the calibration point — note in the manifest that deployment-relevant density depends on the
diamond spec). Pairing by seed makes any identity-recoverability delta attributable to the cues.

Contract/manifest additions (backward-compatible, optional keys — update
`docs/dataset-contract.md` with an "optional keys — dwell lineage" subsection): `axis_offsets_hz`,
`nv_density_ppm`, per-sequence `exit_topology` (int8 or enum) and `dwell_frames` (int), plus the
usual manifest stats. Do NOT change the L=8 line contract.

## Pre-flight

1. Repo state clean; note current branch/HEAD in the run log. Work on branch
   `feat/dwell-identity-lineage`.
2. Physics/contract test suite green before changes; determinism check after (regenerate one
   bucket twice with the same seed → identical md5).
3. Verify the 951-grid pin and v1 bias vector are read from the v1 manifest, not hard-coded
   anew. The immutable v1 reference lives at
   `~/archives/spark1-projects-2026-07-05/odmr-vector-tracking/data/sequence_train_v1/` — the
   odmr archive's copy is the real one there (the tracking-repo archive entry is a dangling
   symlink; resolve via the nv-sensor-sim archive if needed). Read-only.

## Handoff + wrap

- Datasets land in nv-sim's standard output location, then **copy both dataset dirs to
  `~/projects/odmr-vector-tracking/data/`** (the established handoff; do not touch tracking-repo
  code). Record md5s in each manifest and in the handoff note.
- Update nv-sim docs: dataset-contract addendum + a short lineage note (what, why, knobs,
  sources). Tests for both knobs (off = byte-identical to pre-change generation; on = expected
  GT shifts / PL feature present).
- Commits on `feat/dwell-identity-lineage`, repo-style messages, specific-path adds. Push to
  internal mirrors (NAS) if reachable — **no GitHub push** (held for Jason). NAS powers off
  ~21:30 ET; don't block on it.

## Stop-and-report

1. Contract/physics tests cannot be made green without changing the L=8 contract or v1 lineage
   files. 2. The CR model cannot be credibly grounded in the cited sources. 3. Anything
   requiring the tracking repo's code, a retrain, the deck, or GitHub. 4. Determinism check
   fails.

## Out of scope

Hyperfine L=24 / `line_mI` (contract change — separate coordinated dispatch); DR/amplitude
ladder; any training; any tracking-repo edits (the consumer-side exploitation — strain-aware
forward map, CR-gated decode, boundary curves — is the NEXT dispatch, issued after this data
exists); outward-facing material.
