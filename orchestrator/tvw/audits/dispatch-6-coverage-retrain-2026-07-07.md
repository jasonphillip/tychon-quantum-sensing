# Dispatch 6 — odmr-vector-tracking: v3 coverage retrain + tri-eval (increment-6)

**Target session:** `~/projects/odmr-vector-tracking/` on **ws2**.
**Issued:** 2026-07-07 from TVW `audit-dwell-program-2026-07-07.md`; successor to the ratified
increment-5 (`docs/increment5_results.md`, main dde2a74).
**Trigger:** CONDITIONAL — execute the retrain (§2) only when the nv-sim v3 handoff lands in
`data/` (`sequence_train_v3` + `sequence_eval_fieldcone_v1`, md5s verified against the nv-sim
manifests). §1 lands now, before the data exists.
**Mode:** run end-to-end without user assistance; stop-and-report conditions below.

## §1 — Immediate doc patches (no data needed; land on main as doc-only commits)

1. **Finding-(a) conditioning:** state in `docs/increment5_results.md` whether the KF
   exit-identity numbers (0.233 cross / 0.407 bounce) are conditioned on KF's own lock survival
   (KF loses lock on 107/144 of the same in-coverage sequences). Apply the 2c house rule: report
   KF identity conditioned-on-lock, never unconditioned. If the current numbers are
   unconditioned, add the conditioned figures alongside.
2. **Denominator clarification:** one line explaining the in-coverage table denominators
   (learned 0/216 vs KF 107/144 — seeds × sequences conventions), so the numbers are quotable
   without reverse-engineering the matrix.

## §2 — Coverage retrain (on v3 arrival)

**Retrain:** wave-2 `gated+linear+aug` architecture, **frozen v2 recipe** (no architecture, loss,
or hyperparameter changes), same 3 seeds (20260701/11/21), trained on `sequence_train_v3` only
(not v2+v3 mixed — v3 matches v2's size and split recipe by design, so coverage is the only
variable). Cues-OFF data only. `b_est` purity assertions as standing.

**Verdict rules pre-hoc:** declare them in `experiments/increment6_verdict.py` BEFORE reading
results (house pattern: Wilson 95% CI-disjoint, pooled 3 seeds, every-seed consistency, per-seed
spread reported, no single-seed claims).

**Tri-eval:**
1. **Immutable v1 standing eval (REGRESSION GUARD):** the v1/v2 claims must survive — field
   lock at every rung × family CI-disjoint-or-neutral vs the v2 checkpoints; identity metrics
   reported. A CI-disjoint lock regression at any rung/family = guard trip = stop-and-report.
2. **Dwell-eval coverage split (PRIMARY):** re-run `increment5_coverage_split.py` logic on the
   new checkpoints. Success = the deterministic 216/216 template-2/3 acquisition failure clears
   (CI-disjoint improvement, every seed, clean AND snr30); report the new in/out-of-coverage
   split honestly, whatever it is.
3. **Fieldcone boundary chart:** lock-loss vs (off-bias angle × |B|) over
   `sequence_eval_fieldcone_v1`, including the beyond-v3 probe buckets (>60°, <3.0 mT) —
   this is the new claim boundary AND the generalization statement (in-envelope fixed vs
   out-of-envelope behavior, reported separately by `sampling_family`-relevant geometry).

**Also re-measure, do not assume:** the increment-5 balanced-topology identity result (learned
vs KF exit identity, both topologies) on the new checkpoints — finding (b) is
checkpoint-specific until reconfirmed.

## Constraints

- Keep-what-survives; stop-and-report on guard trips — do not tune past a tripped guard.
- No cue data in training (cue retrain = separate future dispatch); no architecture search.
- Branch `increment-6-coverage-retrain`; NAS + private GitHub pushes authorized; main promotion
  after the verdict doc lands. Spark1 archive read-only as standing.
- Strategic next-steps (new dataset requests, program direction) route UP to TVW — no direct
  worker-to-worker dispatches (standing rule, 2026-07-07).
- Outward material untouched; retracted numbers stay banned; findings under IP hold stay internal.

## Stop-and-report

1. v3 handoff md5 mismatch or manifest/contract surprise. 2. Regression guard (tri-eval §1)
trips. 3. Training diverges under the frozen recipe on v3 (report, don't tune). 4. Anything
requiring nv-sim regeneration, a recipe change, or outward material.
