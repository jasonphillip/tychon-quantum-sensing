# Dispatch 7 — odmr-vector-tracking: adopt v6 as deployable default (policy re-selection first)

**Target session:** `~/projects/odmr-vector-tracking/` on **spark2**.
**Issued:** 2026-07-08, from the increment-6 SUCCESS verdict and the TVW deploy ruling
(`audit-dwell-program-2026-07-07.md` Addendum D). No retrain, no new data — decode-policy
re-selection + default flip + documentation. Zero-retrain, evaluation-and-config only.
**Mode:** run end-to-end without user assistance; stop-and-report conditions below.

## Why

Increment-6 cleared the off-cone acquisition failure (216/216 → 1–2/216) with the v1 lock guard
CI-neutral; TVW ruled v6 the deployable default (acquisition dominates the deployable field
claim; v2 keeps sharper in-cone identity as a pinned reference). The deployed re-decode policy
(A3 on OU/reversal, baseline on held) was selected from **v2's** 2c matrix and does not
automatically transfer to v6 — re-select before flipping.

## Steps

1. **Re-decode policy selection on v6** — re-run the 2c-style per-family re-decode comparison
   (baseline / A1 / A3 / stack5, the standing menu — no new decoders) on the v6 checkpoints:
   (a) the immutable v1 standing eval, per family × rung; (b) the dwell eval in-coverage; and
   (c) the off-cone dwell populations (new territory — report which decode wins there).
   Pre-declare the selection rule in `experiments/increment7_policy.py` BEFORE results (house
   pattern: CI-disjoint + every-seed to switch a family's decode; ties → keep the v2-era
   choice for continuity).
2. **Flip the deployable default** to the v6 checkpoints + the selected policy. Record v6
   checkpoint md5s alongside the pinned v2 md5s.
3. **Pin v2 as the in-cone identity reference:** checkpoints + md5s + a short doc note stating
   exactly which claims remain v2-scoped (the 0.311 held misassoc, 0.045 dwell bounce, and the
   v2 v1-eval lock numbers) — any quotation of v2 numbers must say "v2 checkpoints."
4. **Docs:** README/claims sections updated with (a) the v6 trade-off caveat (v1-eval identity
   regression, CI-disjoint clean→snr10; snr3 lock lean, CI-neutral), (b) the measured boundary
   language — "reliable to ~30–40° generic + the directed geometries exactly; hard cliff past
   the envelope; 3.0 mT floor binds" — geometry-specific, never a blanket angle claim.
5. **Housekeeping:** NAS push of main (b102cf3 and this work) when NAS powers on; report
   final HEAD.

## Constraints

- No retrain; no new decoders; no dataset work. Cue lineage and capacity/curriculum
  (increment-7 retrain) are SEPARATE dispatches pending Jason's go.
- Verdict/selection rules pre-hoc; keep-what-survives; stop-and-report on surprises.
- Branch `increment-7-v6-default`; main promotion after docs land; NAS + private GitHub.
- Outward material untouched (TVW owns it); banned numbers stay banned; IP hold stands.
- Strategic next-steps route UP to TVW.

## Stop-and-report

1. Policy selection produces a family where NO decode is CI-neutral-or-better vs the v2-era
   default on lock (would mean the flip damages the field claim somewhere — do not flip).
2. v6 checkpoint md5s don't match the increment-6 run record.
3. Anything requiring a retrain or a new decoder.
