# DISPATCH → odmr-vector-tracking lane — bench data requirements spec (2026-07-09)

**STATUS: HOLD — do not relay.** Gated on Jason's elevation decision.
Hardware choice and purchasing are Jason's call at the TVW level and are not
referenced here; this dispatch is pure data-spec work.

**From:** TVW orchestration lane
**Authority:** eval-bench-elevation-2026-07-09.md (TVW). A minimal
real-hardware CW-ODMR bench demo is under consideration; decision pending.
If approved, the data consumer defines what "usable data" means before any
acquisition script is finalized.
**Paste this whole file into an odmr-vector-tracking session — only after
Jason approves elevation.**

---

## Context

- xTech Round 1 Judge #5: synthetic-data / no-hardware criticisms (~45% of
  rubric weight). One recorded real CW-ODMR sweep set flips these for every
  future submission.
- `polarfire-hybrid-control/docs/real_nv_dataset_hunt_2026-06-21.md` (read
  it): no public regime-matched dataset exists. Target regime: ensemble NV,
  CW-ODMR, 20–70 µT, enough raw spectra for a PCA/sim-to-real fidelity check
  plus a small validation/fine-tune split.
- The bench will have a **fixed bias-field geometry** (magnet jig). That
  matches the fixed-direction deployment prior your architectures exploit —
  and it means geometry metadata is load-bearing, not optional.

## Task: write the data requirements spec

Produce `docs/bench_data_spec_v1.md` (in your repo) defining, with numbers:

1. **Sweep parameters.** Frequency span and step around 2.87 GHz (must
   resolve 20–70 µT Zeeman splittings, ~0.6–2 MHz per line shift at
   28 Hz/nT), dwell time per point, MW power, and modulation scheme if any
   (plain swept CW is acceptable for v1 — say so explicitly if it is).
2. **Quantities.** How many sweeps, at how many distinct field
   magnitudes/orientations, for (a) the PCA/sim-to-real fidelity check
   against nv-sensor-sim output, (b) a validation split, (c) an optional
   fine-tune split. State the minimum viable set (what B1 must deliver) vs
   the nice-to-have set.
3. **Metadata schema (per sweep).** Bias-field magnitude + orientation
   w.r.t. diamond crystal axes (or the measured 8-line splitting pattern it
   implies), temperature (D-shift is ≈ −74 kHz/K), excitation power,
   detector/TIA settings, timestamps, diamond ID ([NV] density, HPHT/CVD).
   Pick a concrete format (CSV header block or sidecar JSON) so the
   polarfire acquisition script can implement it directly.
4. **Acceptance criteria.** What makes a delivered sweep set PASS for the
   fidelity check (SNR floor, line-visibility, repeatability across
   sweeps) and what makes it a regime mismatch you'd reject — so the bench
   session knows the target before first photons, not after.
5. **Time-series requirements (B2, forward-looking).** If/when the lock
   closes, what logged error-signal traces do you want (rate, duration,
   field-step profile) to evaluate tracking claims on real data.

## Constraints

- Spec only — this lane does not build hardware and does not dispatch to
  polarfire directly. Return the spec UP to TVW; TVW relays it into the
  polarfire bench session (mechanical file handoff sibling-to-sibling is
  fine once TVW has seen it).
- Keep claims discipline: this data is for fidelity checking and honest
  evaluation, not for resurrecting retracted claims (no 16/16 / 0.811 /
  DR-5mT framings).

## Return format

Path to `docs/bench_data_spec_v1.md` + a 5-line summary of the minimum
viable B1 set, reported back to TVW.
