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

---

## Addendum A (2026-07-07, later) — dispatch-6 §1 complete; conditioned KF numbers; cross edge RETRACTED

The odmr session executed dispatch-6 §1 (doc-only, main dde2a74 → ac65ddf, commits
0adcdc7/ac65ddf, pushed NAS + private GitHub; verified by TVW). Both §4 flags are resolved:

1. **Conditioning (finding a):** the KF exit-identity figures were UNconditioned. Conditioned
   on KF's own lock survival (2c house rule; recomputed with hard asserts reproducing
   `coverage_split.json` byte-for-byte): cross 24/176 = **0.136** [0.093–0.195]; bounce
   61/120 = **0.508** [0.420–0.596]; pooled **0.287** [0.239–0.341] vs learned A3 0.078
   [0.070–0.088]. Survivor-bias caveat recorded: KF's lock survivors are exclusively the two
   shortest dwells (D=8/16), i.e. the conditioned comparison favors KF's easiest sequences —
   and the learned margins still hold.
2. **Denominators:** now stated in-doc — learned 0/216 = per-topology cell (3 seeds × 72
   seqs; 0/432 pooled); KF 107/144 = single deterministic run, both topologies; exit-identity
   denominators count (crossing × lock) opportunities with valid capture-radius majorities.

**Consequences for the admitted findings:**
- **Finding (a) STRENGTHENS on bounce and pooled:** conditioned bounce 0.508 is an actual
  coin flip on KF's easiest survivors — the gap vs A3 0.045 widens to ~11×, CI-disjoint;
  pooled is CI-disjoint too. The ~9×/~11× figure is now quotable (conditioning check passed).
- **The CROSS edge is RETRACTED from finding (b):** conditioned KF 0.136 overlaps A3 0.111 —
  not separable. Finding (b) now reads: learned beats CV-KF on field lock and on **bounce and
  pooled** exit identity (NOT "both topologies"). The claims table is amended accordingly;
  the HELD-INTERNAL row's "both topologies" wording is superseded.
- The lock-loss claim is unaffected (0 in-coverage learned losses: conditioned ≡ unconditioned).

§2 (increment-6 retrain) remains correctly blocked awaiting the nv-sim v3 handoff; the trigger
condition is carried in the odmr session's memory and in `dispatch-6-coverage-retrain-2026-07-07.md`.

---

## Addendum B (2026-07-07) — Rieckmann arXiv:2606.02749 re-filed: acquisition-fallback candidate

Jason's recall prompted a re-read of the 07-06 sweep's Q5 note. **Rieckmann et al.
arXiv:2606.02749** (2026-06-01; already in odmr `references.md` per hygiene item H1) was logged
solely as a NOVELTY footnote — "static single-shot NN vector solver, NOT a tracker, does not
break our claim." That filing predates the increment-5 coverage discovery, and against the NEW
top problem the paper reads differently: it demonstrates **NN vector solving over essentially
unconstrained field directions (no bias beyond Earth's field)** — i.e., the wide-off-bias regime
where our cold acquisition fails deterministically. It does NOT transplant directly (different
modality: two broadband MW pulses vs our swept CW-ODMR), but it (a) independently validates
v3's premise — NN field solvers handle wide envelopes when trained over them — and (b) suggests
a concrete FALLBACK if the v3 retrain does not fully clear acquisition: a dedicated
**static-frame wide-envelope acquisition head** (cheap to train — single frames, not sequences)
used only to initialize the tracker. **No dispatch now** — v3 is the cheaper, direct attack and
must be measured first (fieldcone eval). Recorded as a post-increment-6 candidate alongside the
cue retrain. Wang/Wrachtrup APL 2026 (the other recent find) remains a classical comparator
(lock+DDS-hop, identity assumed, ≲1 G excursions) — a citation, not a mechanism.

---

## Addendum C (2026-07-07, evening) — v3 + fieldcone DELIVERED and VERIFIED; increment-6 GO

nv-sim completed the v3 dispatch end-to-end (branch `feat/sequence-train-v3-coverage` @ 3231c1c,
NAS + private GitHub; 215 tests green; one mid-run edge-case bug in the widened OU base at the
guard boundary found and fixed by the session). TVW verification against the handoff
(`odmr data/sequence_train_v3_HANDOFF.md`) — all PASS, checked on disk, not from the report:

| check | result |
|---|---|
| raw md5s (v3 / fieldcone) | f32bcd72b7bf6f5eaf0125853b03fcb4 / b152cb6bd1b5090b54389f6404856c23 — MATCH |
| content data_md5 (v3 / fieldcone) | be28fab5a129ff3b757ce77a92e60b47 / 92dc06692d1975f6fcd101e70cc02d99 — MATCH |
| Amendment-1 cond. 1 (draw law in manifest) | `stratification_law` present (angle U[0,62°], |B| U[3,6] mT, cold_start_fraction, carry laws) |
| Amendment-1 cond. 2 (cold-start diversity) | realized 0.531 (785 acquire / 694 carry), per-sequence `start_mode` |
| envelope ≥60°, 53.2° interior | max 65.5°; frac ≥53.2° = 0.076; frac ≥41.5° = 0.285 |
| |B| floor as constraint | min 3.008 mT (floor 3.0 honored); max 5.81 (window-contained) |
| directed sub-pop | 0.278; templates ≈139/148/135/147 incl. hard (0,2)/(4,6) |
| per-sequence fields | sampling_family, max_offbias_angle_deg, min_B_T, directed_template_idx, start_mode |
| fieldcone buckets | failure (exact (0,2)/(4,6)) / control (10–52°, 3.6–5.0 mT) / beyond (66–70° or 2.0–2.5 mT); realized 10–70°, 1.98–5.0 mT; deterministic |
| immutability | v1/v2/dwell/archive untouched (dwell md5s re-verified by producer); seeds disjoint from 20260701/02 |

Observation for increment-6 reading: density at the extreme rim is thin by design (2.3% of train
≥60°) — the fieldcone chart, not the training histogram, is the boundary statement.

**Increment-6 §2 trigger SATISFIED → GO issued to the odmr lane** (per
`dispatch-6-coverage-retrain-2026-07-07.md`; verdict rules pre-hoc; tri-eval; report finding-(b)
re-measurement). Merge ruling for nv-sim: merge `feat/sequence-train-v3-coverage` into
`feat/sequence-generator` directly (dwell precedent; private solo repo; no PR ceremony), keep the
feature branch, push both remotes.

*Merge ruling EXECUTED and TVW-verified (same evening): fast-forward cec6591..3231c1c (no merge
commit — linear history preserved; tests re-verified 215 green pre-merge), both branches at
3231c1c on NAS origin AND private GitHub (ls-remote checked by TVW). Feature branch kept;
cue-twin config staged-not-generated; nv-sim lane CLOSED. All program activity now waits on the
odmr increment-6 tri-eval verdict.*

---

## Addendum D (2026-07-08) — increment-6 VERDICT: SUCCESS; measured trade-off; v6 deploy RULING

**Verified by TVW on disk:** `docs/increment6_results.md` at odmr main b102cf3 (GitHub current;
NAS push pending power-on); pre-hoc rules commit 6074f41 timestamped 2026-07-07 18:58 UTC, ~8 h
before the verdict doc (2026-07-08 02:46 UTC) — the pre-registration held. Frozen v2 recipe
byte-matched; classical parity exact vs matrix_2c_final.

**The four results:**
1. **PRIMARY CLEARS.** Off-cone acquisition 216/216 → **1/216 (cross) / 2/216 (bounce)**,
   CI-disjoint every seed, clean AND snr30. In-cone intact (0/216). Fieldcone directed failure
   geometries **72/72 → 0/72 with zero never-acquires**. Data, not architecture, was the
   binding constraint — dispatch-6's premise confirmed.
2. **Guard holds** (scope = lock, per dispatch): CI-neutral all 12 cells; classical parity
   exact. Honest lean recorded: snr3 point estimates worse (reversal 12/69→22/69, ou
   16/90→25/90, CI-overlapping, wide per-seed spread) — real, not a trip.
3. **Measured trade-off (report-only per dispatch):** v6 identity on the v1 standing eval
   regresses CI-disjointly clean→snr10 (held misassoc 0.311→0.540, IDSW/opp 0.171→0.398;
   reversal 0.424→0.538 / 0.181→0.382; ou 0.505→0.576 / 0.204→0.273). Same capacity
   (175,790 params) spread over a ~3.4× wider cone. **The next binding constraint is
   capacity/recipe, not data breadth.**
4. **Boundary is now a measured chart** (`artifacts/increment6/fieldcone_boundary.png`):
   directed aim points exact (0/72); generic reliability ends ~30–40°; 45–52° controls
   majority-lost; **hard cliff** past the envelope / below the 3.0 mT floor (never-acq
   135–144/144 — generalization: none). **v2's true envelope was <30°** (36/36 lost at the 30°
   control) — the documented ≤18° was the training draw, not the capability edge.
   Finding (b) RECONFIRMS on v6 (bounce 0.077 vs KF-cond 0.508, pooled 0.122 vs 0.287,
   every seed; cross stays no-claim — v6 0.166 vs 0.136 neutral). New territory: v6 is the
   only tracker with measurable off-cone through-merge identity (A3 0.048 bounce / 0.158
   cross; KF vacuous off-cone).

**TVW DEPLOY RULING (the routed-up trade):** **Adopt v6 as the deployable default; pin v2 as
the in-cone identity reference.** Rationale: the deployable, outward-facing claim is the FIELD
claim, and v6 strictly dominates it — acquisition across the widened cone (a capability v2
does not have at any price), in-cone lock intact, guard CI-neutral. The identity claims were
never outward (held-internal) and finding (b) survives the checkpoint swap with margin. An
acquisition failure is a dead instrument; an identity misassignment is a degraded label on a
field estimate that `b_est` purity keeps intact by construction. Conditions:
- The default flip requires **re-selecting the per-family re-decode policy on v6** first (the
  A3-on-OU/reversal / baseline-on-held policy was chosen from v2's 2c matrix and does not
  automatically transfer) → dispatch-7.
- v2 checkpoints stay pinned (md5s recorded) as the identity-reference; v2-derived numbers in
  any material must say "v2 checkpoints."
- Jason veto window: this is an internal default (no outward surface changes); flagged for
  awareness, reversible by a one-line ruling.

**Consequences for candidates:** Rieckmann acquisition-head fallback (Addendum B) is **MOOT —
retired** (acquisition cleared via data). New top retrain-tier candidate: **increment-7
capacity/curriculum** (capacity bump or v2+v3 curriculum — recipe change, fresh dispatch,
Jason's go) to buy back in-cone identity at coverage. Cue retrain remains queued behind it;
do not combine (one variable at a time).

---

## Addendum E (2026-07-08) — external red-team review intake; honesty pass; increment-7 dispatch DRAFTED

Jason ran three external LLM reviews and relayed them: (1) on the ODMR_Vector README, (2) on the
PROGRAM_RECORD, (3) on how to approach increment-7. Processed here as a free adversarial pass. TVW
verified each claim against the repos before accepting or rejecting; the single most valuable item
came from that verification, not from the reviews.

**The verification finding (repo check, not from the reviews):** review-3's INT8 "quantization
eraser" gotcha prompted a check of our own INT8 language. Result: **no INT8/TFLite export of the
tracker exists.** The odmr design docs show the architecture is *built to* the V250 INT8 op-whitelist
(ops-guard passes) and the recurrence/association run in float on the RISC-V host — but the original
design-doc "Increment 3 (deployment) → TFLite" never happened (the actual increment-3 became the
appearance-fingerprint lever). `docs/increment6_results.md` has zero export/quantization content. So
the README line "≈175k params, INT8 … already running on real silicon" conflated three things: the
model is **float today**; the INT8 export + parity is **pending**; what is on silicon is the older
**FPGA-demo model**, not this tracker. Corrected on every surface (README, PROGRAM_RECORD 4.1). New
open item **O11** (INT8 export + on-target parity; QAT route per Jacob 2018; cross-repo odmr→polarfire).

**ACCEPTED and acted on this session:**
1. "Beats every classical method" → scoped to "the competent classical baselines we tested"
   (KF/Hungarian, NLS, PID). MHT/JPDA/labeled-RFS are a pending challenger lane (**O12**, folds in the
   old Stone Soup GLMB/LMB check). README + claims-register 4.1.
2. Identity-impossibility → qualified as **frequency-only / channel-specific**, not absolute (a Rabi/
3. Sim-to-real named the largest unproven link → **O13** hardware-validation planning (blinded real-ODMR
   run, v2 vs v6 vs best classical). README one-liner note added.
4. A 2025 NV real-time vector-tracking paper (MW freq-mod + feedback; classical, not a sequential ML
   tracker) → **O14**, identify + ETL into `odmr-pnt-nv-docs`, feed the Q5 novelty queue. Background
   agent in flight (also ETL'ing Hinton 2015 / Jacob 2018 / Yu 2020 for increment-7 grounding).
5. Increment-7 design absorbed the two good method contributions — **knowledge distillation** (FP32
   teacher → v6-identical student) and **geometry-weighted "foveated" identity loss** — plus optional
   **PCGrad** for the diagnosed field↔identity gradient conflict, all **deployment-neutral**
   (architecture/param-count frozen). Capacity bump demoted to a separate **increment-8** (it carries
   an NPU-budget + `.vnnx`-recompile cost the training-signal arms don't). → dispatch-8 DRAFT.

**REJECTED (recorded so the errors don't propagate):**
- Review-3 **conflates increment-7 with the cue retrain** — its central "adding CR-dip physics in
  increment-7 causes catastrophic forgetting" describes a plan we do not have. Increment-7 = fixed-data
  identity recovery; the CR cue is a separate later dispatch; the one-variable rule already forbids the
  combination it warned about.
- "CR dips at ~51.4 mT / ESLAC" is a **physics pattern-match**. Our CR cue is the **cross-axis
  degeneracy** condition (|B·n_i| = |B·n_j|), geometry-dependent throughout the 3–6 mT operating band —
  which is precisely why it coincides with merges and carries identity. (Its "compute a CR-proximity
  scalar upstream and feed it in" idea survives translation but brushes the `b_est`-purity rule, since
  that scalar derives from the field estimate — an architecture question for the cue increment, flagged.)
- **EWC (Kirkpatrick 2017) is misapplied.** v6 was trained **from scratch** on v3 under the frozen v2
  recipe — no sequential fine-tuning, so catastrophic forgetting is not the failure mode. The regression
  is capacity allocation under joint training; PCGrad is the apt tool from that family (kept). EWC not
  ETL'd.
- Review-2's broad agreement with our rulings is **circular** — it read this record, which already
  encodes them. Not counted as independent corroboration.

**Meta-lesson (recorded):** the external models reliably *retrieve the right toolbox* (distillation,
QAT, PCGrad — all real, correctly cited) and unreliably *bind it to program state* (which increment
does what, which physics regime, sequential vs from-scratch training). The binding step is the
orchestration lane's value-add — and it is what surfaced the only finding that survived contact with
the repos (no INT8 export).

**Artifacts this session:** README + PROGRAM_RECORD honesty pass (float-status, tested-baselines,
frequency-only); `dispatch-8-increment7-identity-recovery-2026-07-08.md` (DRAFT, gated on Jason's go +
dispatch-7 completion); PROGRAM_RECORD open items O11–O14 + ledger D16; prior-art/method-paper ETL in
flight into `odmr-pnt-nv-docs`.
