# Audit addendum — dwell-lineage program outcome + orchestration reconciliation

**Date:** 2026-07-07 (evening; follows the 00:23 dispatch commit 72bafa7)
**Scope:** verify and record three work products completed since the last audit entry, admit
three findings to the claims accounting with qualifications, reconcile one orchestration-role
error, and issue the successor dispatches.
**Sources read directly (not summaries):** `nv-sensor-sim/logs/sequence_dwell_v1_generation.md`
(branch `feat/dwell-identity-lineage`, HEAD cec6591); `odmr-vector-tracking/docs/increment4_results.md`,
`docs/increment5_results.md`, `experiments/increment5_verdict.py`,
`experiments/increment5_coverage_split.py` (main = dde2a74 on NAS origin and private GitHub, verified);
TVW `research-improvement-search-2026-07-06.md` + 07-07 addendum,
`dispatch-nvsim-identity-physics-2026-07-07.md`, `design-review-odmr-vector-2026-07-01.md`.

---

## 1. dispatch-nvsim-identity-physics-2026-07-07 — DELIVERED, one physics deviation ACCEPTED

nv-sim delivered `sequence_dwell_v1` (288 seqs, eval-only, contract v1, 951-pt pinned grid,
cues OFF; content md5 f84d40ea…) and the seed-paired `sequence_dwell_v1_cues` (strain M_z +
3.8 ppm CR; `B_true`/seeds byte-identical to the cues-OFF set, verified). 188 tests green;
determinism check passed; knob-off byte-identity covered by tests. Branch
`feat/dwell-identity-lineage` (cec6591), mirrored to NAS + private GitHub.

**Deviation (flagged by the session, now ACCEPTED by TVW):** the dispatch asked for exactly one
coalescing pair with six protected spectators. This is physically impossible in the noiseless
L=8 model: a cross-axis degeneracy forces `|B·n_i| = |B·n_j|`, which forces identical per-axis
Hamiltonians, so the NV-mirror pair coalesces exactly and simultaneously — every merge is a
**quartet** (target pair + mirror pair), leaving **four** protected spectators. The session
verified this three ways (first-order condition, direct diagonalization showing 0.000 MHz mirror
separation at every merge, full field scan finding no counterexample) and it coincides with the
cross-relaxation resonance condition (Espinós & Budker, arXiv:2512.13835 Eq. 3). Building a
single-pair merge would require inventing unphysical asymmetry, which the dispatch forbade.
**Ruling: the deviation is inherent physics, not a spec miss; no regeneration required.**
Downstream consequence, already handled correctly in increment-5's scoring note: frame-wise
in-collision misassoc has a 0.5 attribution floor on these quartet merges, so **IDSW/opportunity
(exit identity) is the discriminative identity statistic on this lineage.**

## 2. dispatch-4-identity-overlay — verdict already recorded

Increment-4's NOTHING-SURVIVES verdict (best D-UM r=2, 0.298 vs baseline 0.311, not CI-disjoint,
one seed regresses, OU/reversal guards trip; root cause = information limit at ~132-frame merges)
was recorded in the 07-07 outcome addendum to `research-improvement-search-2026-07-06.md`
(commit 72bafa7). No change; the zero-retrain/decode-side tier remains EXHAUSTED.

## 3. Increment-5 — outcome record + retroactive ratification

**Process:** increment-5 (the consumer-side exploitation that `dispatch-nvsim-identity-physics`
explicitly deferred to "the NEXT dispatch, issued after this data exists") was executed directly
in the odmr session on Jason's verbal go-ahead, without a TVW dispatch. Mitigations verified:
verdict rules were declared pre-hoc in `experiments/increment5_verdict.py` (docstring states the
house pattern — Wilson 95% CI-disjoint, pooled 3 seeds, every-seed consistency — "declared here,
before reading results"); `b_est` purity asserted throughout; the immutable-archive and
no-GitHub-main-without-approval rules were respected. **TVW retroactively RATIFIES increment-5
as if dispatched** — the work followed every standing constraint except the dispatch channel
itself. The channel error is addressed in §5.

**Verdicts (from `docs/increment5_results.md`, confirmed against the verdict script):**
- **Cue robustness: GUARD TRIPPED** — the ~1.8% CR dip drives learned field lock-loss 432/864 →
  783/864 (CI-disjoint at every rung). Cues as rendered are not deployable with current
  checkpoints. (CV-KF is robust and even improves — the cue is physically informative; the
  learned conv front-end is what breaks. Exploiting cues = retrain-tier.)
- **Cue exploitation: NO SURVIVOR** — strain offsets invisible at ~MHz candidate resolution
  (exact null); CR gate correct-but-unhelpful on a field estimate broken by the same dip.
- **Boundary (primary result) + a discovered training-coverage gap** — see findings below.
- **Ships nothing; deployable default unchanged** (wave-2 `gated+linear+aug`, A3 on OU/reversal,
  baseline on held).

## 4. Three findings admitted to the claims accounting — WITH qualifications

**(a) CV-KF's identity crown is CV-prior-matching, now measured.** On the topology-balanced
dwell eval (in-coverage, clean), KF bounce exit-identity = 0.407 switches/opportunity vs learned
A3 0.045 (~9×); cross 0.233 vs 0.111. ADMITTED with three qualifications:
1. *Conditioning check required before any outward quotation of the ~9×:* KF loses field lock on
   107/144 of the same in-coverage sequences; whether its exit-identity denominator is
   conditioned on lock survival is not stated in `increment5_results.md`. The 2c house rule
   ("report KF identity conditioned on lock, never unconditioned") must be applied here too.
2. *Denominator conventions differ across the in-coverage table* (learned 0/216 vs KF 107/144)
   and need a one-line clarification in the results doc before quotation.
3. Dwell-eval-scoped: this does NOT overturn the v1-held numbers (KF 0.099 vs learned 0.311
   in-collision misassoc on v1 held stands).

**(b) New positive learned claim (dwell-eval-scoped, in-coverage).** Learned beats KF on BOTH
field lock (0/216 vs 107/144) and exit identity (both topologies), with no observed dwell cliff
(A3 exit-identity 0.059–0.099 across D=8→192). ADMITTED as **HELD-INTERNAL** with:
1. **Never quote without finding (c)** — the same eval discovered a deterministic out-of-coverage
   failure; quoting the win without the boundary is cherry-picking.
2. "Flat in dwell" → say "no observed cliff (CI-limited)": 24 seqs/bucket gives wide Wilson CIs.
3. Scoped to engineered quartet merges (the §1 physics), clean→snr10; snr3 degrades gracefully.
4. **Standing IP hold**: outward use is Jason's call; coalescence/dwell/cue mechanisms stay out
   of outward material; a novelty re-run (open Q5) is a precondition of any external claim.

**(c) Deterministic field-coverage gap — the new top program lever.** Merge templates (0,2)/(4,6)
require 41–53° off-bias at 3.9/3.3 mT to force their degeneracy; cold field acquisition fails
216/216, all 3 seeds, every dwell length and topology; templates (0,6)/(2,4) (6–15° off-bias,
|B| ≈ 4.9–5.0 mT, inside the ≤18° training envelope) never fail (0/216). ADMITTED with one
correction to the summary wording: **the failing geometries are jointly outside the training
envelope on BOTH off-bias angle (41–53° vs ≤18°) AND field magnitude (3.3–3.9 mT vs trained
~4.7–5.8 mT)** — do not attribute to angle alone until the v3 lineage + fieldcone eval ablate
which axis binds. This supersedes the improvement-search ranking: **angular/magnitude field
coverage is now ranked above all identity mechanisms.**

**Claims-table actions (this commit):** three rows appended to
`tvw/outreach/briefing-deck/claims_map.csv` — (i) slide-2 identity-caveat qualification per (a);
(ii) slide-2 lock-claim scope boundary per (c); (iii) finding (b) as HELD-INTERNAL, not for any
deck surface pending Jason's release. Deck v6 artifacts are NOT edited by this addendum; if the
deck is ever re-rendered, the gate must pick these rows up.

## 5. Orchestration reconciliation (role error, closed)

The odmr session, acting as orchestrator, relayed a `sequence_train_v3` dataset request directly
to nv-sim (Jason pasted it; nv-sim is now acting on it). Per the standing lane roles
(global CLAUDE.md, updated 2026-07-07: TVW orchestrates; worker lanes hand strategic next-steps
UP), that relay should have routed through TVW. **Resolution: the request is RATIFIED and
formalized as `dispatch-nvsim-sequence-train-v3-2026-07-07.md`**, which supersedes the relayed
text, resolves the design forks the nv-sim session raised (envelope mechanism = hybrid;
scale/split; dwell holds OFF; cues config-only; push targets), and adds a held-out fieldcone
eval companion the relayed request lacked. The technical content of the relayed request was
sound — the error was channel, not substance. No correction to nv-sim's in-flight work is
required beyond adopting the formal dispatch.

## 6. Dispatch decisions

1. **`dispatch-nvsim-sequence-train-v3-2026-07-07.md`** (nv-sim, active now) — the v3
   angular/magnitude coverage lineage + `sequence_eval_fieldcone_v1` held-out eval companion.
2. **`dispatch-6-coverage-retrain-2026-07-07.md`** (odmr, conditional: execute when the v3
   handoff lands) — frozen-recipe retrain on v3, tri-eval (immutable v1 standing eval as
   regression guard; dwell-eval coverage split as primary; fieldcone boundary chart), pre-hoc
   verdict rules, plus two immediate doc patches (finding-(a) conditioning + denominator
   clarification).
3. **Cue-retrain lineage: NOT dispatched.** It needs its own go-ahead after v3 lands — the CR
   dip must enter the training distribution to be exploitable, and that retrain should not be
   confounded with the coverage retrain. Recorded as the next candidate after increment-6.
