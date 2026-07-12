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

**ETL landed (2026-07-08, same session):** background agent ingested 4 papers into
`~/.corpus/odmr-pnt-nv-docs` (66 raw / 762 chunks; local Qwen3-Embedding-4B on spark2, provenance
verified — no cloud fallback, index extended additively). Prior-art paper (O14) **IDENTIFIED with
high confidence:** Fu, Yang, Ren, et al., "Integrated NV real-time vector magnetometer with high
sensitivity and wide dynamic range," *Opt. Express* **33**(11), 22385–22395 (2025), DOI
10.1364/OE.548080. **Q5 delta (favorable):** it is a **classical** multi-channel microwave-FM +
per-NV-axis feedback (frequency-lock-loop) system — zero "machine learning"/"neural network" in the
full text — a **continuous steady-state lock, not a sequential estimator**; each control channel
stays captured on an already-resolved, well-separated resonance and there is **no mechanism to
re-associate lines near degeneracy**. It does not treat crossings/merges as data association — the
exact regime our sequential ML tracker exists for. Net: it narrows the loose phrase "real-time NV
vector tracking" but does not reach our claim; **novelty position strengthened, pending the formal
Q5 re-run (O7).** Method papers Hinton 2015 / Jacob 2018 / Yu 2020 embedded for increment-7 and O11
grounding (EWC deliberately excluded).

---

## Addendum F (2026-07-09) — outreach gate check: incr-5/6 numbers for external pre-read (SPLIT ruling)

Outreach lane requested clearance to cite increment-5/6 results in an outbound pre-read to a
prospective advisor (name withheld). TVW verified every number against
`docs/increment5_results.md` / `docs/increment6_results.md` at odmr main b102cf3 and gated against
PROGRAM_RECORD §4 (claims register). No banned numbers (16/16, 0.811, DR ~5 mT) in the request.

**RULING — split:**

1. **APPROVED — incr-5 field lock-loss contrast** (learned 0/216 vs CV-KF 107/144), as a
   §4.1-class field-lock claim, with mandatory language: (a) "v2 checkpoints" label; (b)
   tested-baselines scope ("the competent classical baselines we tested" — CV-KF+Hungarian, NLS,
   PID; MHT/JPDA/labeled-RFS pending, O12 — never "all classical methods"); (c) population scope:
   this is the IN-COVERAGE dwell eval (≤~18° off-bias training envelope); (d) denominator
   harmonization — learned 0/216 is the per-topology cell (0/432 pooled, 3 seeds × 72 seqs),
   KF 107/144 is a single run pooling both topologies; recommend "0 lock losses across all 432
   in-coverage runs vs 107/144 for CV-KF" to avoid apples-to-oranges reading.
2. **APPROVED — incr-6 acquisition numbers** (216/216 → 1/216 cross, 2/216 bounce, CI-disjoint
   every seed clean+snr30; directed 72/72 → 0/72; guard CI-neutral no trips; identity regression
   report-only; no defaults changed) — already admitted at §4.1 COVERAGE. Mandatory language:
   (a) the measured-boundary wording ("reliable to ~30–40° generic + the directed geometries
   exactly; hard cliff past the envelope; 3.0 mT floor binds" — geometry-specific, never blanket);
   (b) the v6 trade-off caveat alongside any v6 number (v1-eval identity regresses CI-disjoint
   clean→snr10); (c) label checkpoints (v2 vs v6) so the pre-read stays accurate through the
   pending dispatch-7 default flip; "no defaults changed" is accurate as of 2026-07-09 only.
   NOTE for drafting: incr-5's 0/216 (in-coverage lock) and incr-6's 216/216 (off-cone
   acquisition, the v2 failure mode) are DIFFERENT populations — the pre-read must scope both or
   a technical reader hits an apparent contradiction.
3. **DENIED (for now) — exit-identity bounce contrast (0.045 vs 0.407).** This is finding (b),
   §4.3 HELD-INTERNAL: release requires Jason's explicit O4 decision + the Q5 novelty re-run
   (O7, not yet run) + IP review (US10921394B2 adjacency). Not TVW's to approve, and the O4
   prerequisites cannot complete before 7/15. Additionally the request as phrased is technically
   deficient: 0.407 is the UNCONDITIONED KF figure — the Addendum-A house rule requires
   conditioning on KF lock survival (0.508), and the cross edge is retracted (no-claim). Safe
   alternative offered: a qualitative, number-free line ("an additional identity-continuity
   result vs classical baselines is held internal pending IP review") — no numbers, no mechanism.
4. **Cross-cutting mandatory framing (both approvals):** all metrics are FP32 simulation results
   on synthetic ODMR data from our simulator; sim-to-real unvalidated (O13); no INT8/TFLite
   export exists; nothing about this tracker is on silicon (§4.1 DEPLOYMENT STATUS wording if any
   edge/silicon language appears). [MODEL]/synthetic framing as proposed by outreach: required.

**Embargo (c):** none on repo-sync grounds — all cited docs are on odmr main b102cf3, mirrored to
private GitHub and NAS (NAS push executed by TVW 2026-07-09). Repos remain PRIVATE: quote numbers,
do not share repo access or doc files; proof-bank entry may cite doc paths + commit b102cf3 as
provenance. Real embargoes: §4.3/O4 on identity numbers (item 3); checkpoint-labeling through the
dispatch-7 flip (item 2c).

---

## Addendum G (2026-07-09) — dispatch-7 COMPLETE, TVW-verified; v6 is deployable default

Worker session (Opus 4.8) executed dispatch-7 end-to-end in ~19 min, no stop conditions triggered.
TVW verified on disk before booking:

1. **Pre-hoc integrity (STRICT, file-mtime level):** rule commit 9d9a554 (19:21:16 UTC,
   `experiments/v6_redecode_policy.py` only — 401 lines, zero results) → re-decode surfaces
   `matrix_6_redecode.json` written 19:21:54 → selection artifacts 19:22:23 → flip commit
   2f52d69 (19:26:31, docs-only: deployable_default.md + increment6 addendum + README). The
   5-min window is legitimate: fast eval, not peeking. Rule content was additionally
   pre-registered in the dispatch text itself (issued 07-08).
2. **md5s independently recomputed** on the three on-disk v6 `best.pt` files: bf5bfa77…,
   0d531c2e…, 842e867c… — all match the deployable_default.md table exactly.
3. **Selection artifact** (`v6_redecode_policy.json/.md`) matches the report: NO family
   switched (held→baseline, ou/reversal→A3, dwell→A3 all populations). The held call is
   correct per rule: A3 misassoc is CI-neutral (not disjoint), continuity keeps baseline.
4. **Language audit:** banned numbers absent from all touched docs; v2-scoped claims (0.311,
   0.045, v2 lock) carry mandatory "v2 checkpoints" attribution; v6 trade-off caveat and
   geometry-specific boundary wording present.
5. **Repo state:** main = v6-default-flip = 2f52d69 on local, NAS (origin), and private
   GitHub. No library code changed (commits touch experiments/ + docs only) — test-suite
   claim (175 green) accepted without re-run on that basis.

**RULING: dispatch-7 CLOSED — SUCCESS.** v6 is the deployable default with the re-selected
(unchanged) per-family policy; v2 pinned as in-cone identity reference; canonical registry
`docs/deployable_default.md`. Outreach note: Addendum F item 2c's "no defaults changed"
wording is now STALE — any pre-read drafted after 2026-07-09 evening must say v6 is the
deployable default (checkpoint labels already mandated, so approved numbers are unaffected).

**Dispatch-8 gate status:** gate 2 (dispatch-7 complete) CLEARED. Gate 1 — Jason's explicit
go — remains and is the only gate. Baseline-to-beat is now concrete: v6 @ 2f52d69 with policy
held→baseline, ou/reversal→A3. One correction to the worker's routing note: dispatch-8 as
drafted (post-Addendum-E) is the TRAINING-SIGNAL increment (7a foveated identity loss, 7b
distillation, 7c optional PCGrad — deployment-neutral, frozen data/architecture), NOT
"capacity bump or curriculum" — the capacity bump is increment-8, a separate later decision.

---

## Addendum H (2026-07-11) — dispatch-8/increment-7 COMPLETE, TVW-verified; verdict KEEP-NOTHING (escalate); increment-8 decision now open

Worker session executed dispatch-8 (increment-7 identity recovery) 2026-07-09 → 07-11 on branch
`increment-7-identity-recovery`, final HEAD d8773f3, on NAS + private GitHub (both verified to
contain d8773f3); main NOT promoted — correct, keep-nothing leaves nothing to promote. TVW
verified on disk before booking:

1. **Pre-hoc integrity (STRICT):** rules commit a7b3061 (2026-07-09 20:08:47 UTC) contains the
   full 345-line `experiments/increment7_verdict.py` with BOTH design-freedom points frozen —
   the 7a foveated bin schedule (angle bins normalized to train-set mean 1.0, wide-angle 0.5×)
   and the 7b teacher/KD spec (4× teacher via feat_dim 64/assoc 32/state 128/conv 16, α=0.5,
   T=2.0 per Hinton 2015). First training artifact mtime 20:09:36 — 49 s after the rules
   commit. The worker also self-flagged the shared-teacher seed-correlation caveat in the
   rules text. §0 quantization paragraph present and stated first, per dispatch.
2. **Verdict application is correct and is the interesting part.** 7b distillation pooled held
   misassoc 0.402 — CI-improve AND below the 0.425 material threshold — but seed 20260721
   landed at 0.604, worse than its v6 counterpart (0.581), so the every-seed rule fails
   PRIMARY. Per-seed spread 0.262/0.340/0.604. This is the same seed-instability signature
   that killed increment-3 lever B; the rule did exactly what it was registered to do. ou
   recovery ~100% and reversal 65% DID clear CI+every-seed, but the headline gate is held.
   7a foveated: no effect on target (held 0.548 vs 0.540, neutral) — reweighting gradient
   location at fixed capacity with hard labels doesn't buy identity back. Verdict artifact
   decision field = `keep-nothing-escalate`; kept/survivors empty. GUARD-A/B never tripped
   by any arm (directed 0/72 every seed; off-cone CI-neutral; lock neutral).
3. **7c PCGrad: declined by Jason 2026-07-11** (dated disposition in the results doc,
   scaffolding committed untrained). Sound premise-weakening rationale recorded: no
   field-vs-identity guard conflict was ever observed, so gradient-surgery's target mechanism
   is unsupported by the evidence.
4. **Language audit clean:** banned numbers absent; the only "on-silicon" string in the new
   docs is the §0 sentence prohibiting the claim. Deployment-neutrality asserted on all 6
   candidates (params == 175,790, state-dict shape-identical to v6, ops-guard pass). Teacher
   (699,982 params) correctly marked throwaway/never-deployed.
5. **Diagnosis refinement accepted into the program record:** the pre-registered escalation
   framing was "capacity tension"; the evidence sharpens it to **reliability-at-fixed-
   capacity** — no arm ever traded acquisition for identity (the objectives are not in hard
   opposition at eval time), and 2 of 3 distilled seeds held BOTH, one into v2 territory. The
   student CAN fit both; it cannot do so reproducibly across seeds at 175,790 params with one
   teacher. Teacher premise confirmed real dark knowledge existed (teacher val 0.579 vs v6
   0.658).

**RULING: dispatch-8 CLOSED — executed correctly; verdict KEEP-NOTHING per pre-hoc rules.**
Deployed default remains v6 @ 2f52d69 with the dispatch-7 policy. v2 remains the pinned in-cone
identity reference. No outward-claims impact: nothing in §4 changes (no new default, no new
outward number; increment-7 results are internal evidence). Fieldcone boundary not re-charted
(no survivor — per dispatch).

**Escalation received — the increment-8 decision is now open at TVW.** Two candidate paths,
NOT yet dispatched, decision is Jason's:
  (a) **Capacity bump** (increment-8 as originally framed) — raise param count; carries the
      NPU-budget re-check + `.vnnx` recompile Beelink handoff (cross-repo, hardware cost).
  (b) **Distillation-recipe refinement** (deployment-neutral, new recipe = fresh dispatch) —
      attack the seed instability directly: e.g. teacher ensemble (kills the shared-teacher
      correlation), stronger/longer KD schedule, seed-selection-with-holdout is NOT eligible
      (post-hoc selection violates house discipline).
  The 7b evidence favors trying (b) first: the failure is reproducibility, not capacity to
  fit, and (b) costs no hardware path. A (b) failure with an ensemble teacher would then be
  clean evidence for (a). HOLD — no dispatch drafted until Jason picks a direction.

---

## Addendum I (2026-07-11) — increment-8 options audit + literature ETL; the (a)/(b) dichotomy is NOT exhaustive

Per Jason's directive, TVW ran a three-agent research sweep (KD-reliability lit; training-stability
lit; adversarial option-space completeness) against the Addendum H diagnosis
(reliability-at-fixed-capacity) before any increment-8 direction is picked. Full deliverable:
**`tvw/audits/increment8-options-audit-2026-07-11.md`**. Headlines:

1. **The Addendum H two-path framing is superseded.** The audited option space has SIX
   constraint-surviving families: (A) capacity bump [orig. a]; (B) target-signal refinement
   [orig. b, widened: ensemble teacher, logit standardization, consistent-view+patience,
   co-distillation]; (C) trajectory-stability levers [NEW: SAM, SWA/EMA, shared-early-checkpoint
   seed branching — the only family whose literature directly targets seed variance];
   (D) cross-seed weight aggregation into one same-shape model [NEW, gray-zone: valid via
   branch-then-soup, NOT via cross-init re-basin at 176k width]; (E) two-stage + EWC retention
   [NEW]; (F) collapse-exact over-parameterized training, ExpandNets-style [NEW — option (a)'s
   optimization benefit with zero deployment cost; sharpest structural miss].
2. **Load-bearing literature findings:** seed variance is trajectory instability, not any single
   noise source (arXiv:2103.04514 — kills "pin the RNG"); KD is *partial* variance reduction
   dependent on α (2305.17581 — explains 7b's 2/3); inter-student variance shrinks O(1/k) with
   k averaged teacher responses (2601.18909, 2026 — theoretical backbone for ensemble teacher);
   co-distillation/churn methods measurably cut cross-seed disagreement (2102.03349, 2106.02654,
   2204.04735); soups need a shared basin — branch seeds from an early stable checkpoint
   (1912.05671, 2203.05482); don't just scale the teacher (1910.01348).
3. **Governance question flagged for Jason (§5 of the audit, HOLD):** every-seed recipe
   reliability vs a pre-registered per-run acceptance gate — a policy choice that changes what
   increment-8 must achieve. TVW recommends keeping the every-seed standard.
4. **TVW recommendation (§6, decision Jason's):** deployment-neutral "B+C stack" first (ensemble
   teacher + logit standardization + EMA/SWA + shared-early-branch seeds, optional SAM; free
   branch-then-soup report-only arm), family F second, true capacity bump (A) only after those
   fail — at which point the hardware-cost evidence would be clean.
5. **ETL booked:** 26 arXiv method papers (24 full-text via ar5iv/Jina, 1 native-HTML full text,
   1 abstract-only — 2601.18909, no HTML render available) into `~/.corpus/odmr-pnt-nv-docs`
   `raw/arxiv.org/` with provenance headers; manifest 28→54 sources; acquisition.log appended;
   corpus reprocessed with Qwen3-Embedding-4B (Spark2). Residual gaps (index-verified only, NOT
   ingested): 2407.04600, 2206.15047, 2512.13905, ASAM/GSAM/Switch-EMA variants.
6. **Novelty note:** no paper directly addresses seed-stable KD for tiny fixed-architecture
   embedded students — a positive B+C result would be a defensible novelty point (feeds the Q5
   ledger / O7 when it runs).

**Status: increment-8 direction remains OPEN — expanded menu on the table; no dispatch drafted.**

---

## Addendum J (2026-07-11) — AWS training fan-out capability built (`gpu-fanout`); data-posture ruling recorded

1. **Data-posture ruling (Jason, 2026-07-11):** Jason directed TVW to set up AWS
   parallelization for the increment-8 training matrix, with the synthetic-data caveat
   explicitly on the table — this constitutes approval to send (i) the synthetic v3 training
   set (`sequence_train_v3/dataset.h5`, 2.9 GB, simulator output) and (ii) git-archived
   tracked SOURCE of odmr-vector-tracking + nv-sensor-sim to AWS S3/EC2 (private account,
   us-east-1). NOT approved / not sent: eval datasets, checkpoints history, repo .git
   history, any SBIR document material, anything CUI-adjacent. Evals and pre-hoc verdicts
   run LOCALLY on spark2 only — the cloud executes training and returns checkpoints; the
   local verdict re-derives every number, so cloud execution cannot contaminate the audit
   chain.
2. **Placement ruling:** new fleet-infra repo `~/projects/gpu-fanout` (private GitHub
   `jasonphillip/gpu-fanout`, main @ da1dd37) — NOT inside odmr-vector-tracking, keeping
   cloud-infra churn out of the science repo whose git history is the pre-hoc discipline
   chain. The odmr worker consumes it via the increment-8 dispatch.
3. **What was built (v1, validated dry-run):** preflight (SSO/quota L-DB2E81BA/AMI/bucket
   go-no-go), scoped IAM instance profile (S3 single-bucket), sha256-manifested bundle
   staging, matrix launcher (dry-run by default, `--launch` to spend, per-invocation
   instance cap, double-launch refusal, IMDSv2 required, watchdog `shutdown +720` as FIRST
   user-data action with terminate-on-shutdown), result collection with per-run exit
   status, teardown by tag. Draft 12-run matrix for the B+C stack (5 teachers + trunk;
   6 students in wave 2) — clearly marked DRAFT; the real matrix + `increment8_train.py`
   + pre-hoc verdict belong to the dispatch. Worst-case cost ≈ $58/wave at g6.xlarge caps.
4. **Provenance discipline:** every cloud run writes `run_manifest.json` (torch/CUDA/GPU/
   platform, repo commit SHAs, dataset sha256, exact cmd). Cross-hardware caveat booked in
   the README: L4/x86 vs GB10/ARM is not bitwise-comparable — the increment-8 dispatch must
   state whether baselines are rerun in-environment or hardware is a recorded covariate.
5. **Blockers before first launch:** (i) Jason's SSO login (`aws sso login --profile
   spark-sso --use-device-code`) — CLI v2.35.21 installed on spark2, config restored from
   the spark1 preflight clone; (ii) preflight PASS, esp. G-instance quota (often 0 on
   fresh accounts; request early); (iii) the increment-8 dispatch itself (direction pick +
   pre-hoc verdict rules committed in odmr BEFORE any cloud run).

---

## Addendum K (2026-07-11) — CUDA-Q/GPU-sim assessment + ETL; fan-out harness VALIDATED end-to-end; quota state; dispatch-9 launch policy amended

1. **Fan-out harness validated on real AWS runs.** Smoke test PASSED end-to-end (g6.xlarge:
   boot → scoped-IAM S3 access → sha256-verified bundle → venv+torch cu130 → L4 GPU visible →
   2.9G dataset readable → both packages import → provenance run_manifest.json → results to
   S3 → self-terminate). One bug found+fixed on the way: embedded quotes in run commands broke
   the user-data bash parse — commands are now base64-transported (gpu-fanout b76bcb7+).
   IAM worker role created BY JASON (permission-gated, correctly held for his review).
2. **Quota state:** raise to 64 G-vCPUs = Support case 178377947900659 (OPEN; the three AWS
   emails Jason forwarded 2026-07-11 are its opening notifications, not a decision). History
   shows a prior 192-vCPU request CLOSED UNGRANTED 2026-06-05 → expect friction. Spot G quota
   = 0 (no shortcut). **Dispatch-9 gate amended per Jason: launch chunked at current quota
   (8 vCPUs = 2 concurrent), widen as the raise lands.**
3. **CUDA-Q question (Jason) answered — assessment filed:**
   `cudaq-gpu-sim-assessment-2026-07-11.md`. Headlines: CUDA-Q 0.15.0 EMPIRICALLY RUNS ON
   OUR GB10 (agent installed cu13 wheel + ran 1024 batched 3-level Lindblad evolutions in
   4.5 s; benchmark preserved as `cudaq-batched-dynamics-benchmark-2026-07-11.py`; cudaq now
   in spark2 base env). nv-sensor-sim already has a STUB CudaQAdapter (planned, never built) —
   activation is now de-risked. For the future fidelity generator the recommendation is
   dynamiqs (JAX; native batching + DIFFERENTIABLE → sim-to-real calibration) as primary with
   CUDA-Q Dynamics as verified throughput fallback; today's analytic generator needs only
   batched linear algebra if speed ever binds. Gotchas booked (cu13-only on Blackwell,
   collapse-ops list-of-lists, RK integrator not torch, chunked batches at 10^6).
   L4 validation run launched on AWS (r1 failed on a trivial matplotlib dep; r2 in flight).
4. **ETL booked:** new corpus `~/.corpus/gpu-quantum-sim` — 16 sources (NVIDIA primary docs,
   dynamiqs/qutip-jax/JAX, 5 arXiv sim-to-real/ODMR refs), 186 chunks, Qwen3-Embedding-4B.
   3 GitHub sources acquired via raw/API fallback (Jina 403 on github.com).
5. **NGC/NIM (Jason follow-up):** NGC = yes, relevant as the pinned-container distribution
   channel for CUDA-Q/cuQuantum (nvcr.io/nvidia/quantum images; DGX Spark porting guide lists
   cuQuantum "Yes since 25.06") — right route for reproducible envs when the adapter gets
   built. NIM = NOT relevant to simulation (inference microservices; NIMs keep their existing
   role as local audit critics only).
6. **Strategic ruling context (sim-to-real):** Jason flagged that everything rests on
   simulated data and asked how to improve the dataset before real-hardware access; TVW
   answered with the sequenced plan (do NOT pause increment-8; recipe first, fidelity data
   next, merge at a v4 re-validation increment) + the no-hardware levers: differentiable-sim
   calibration to published spectra, domain randomization widening, fidelity physics the sim
   already stubs (cross-relaxation/P1 bath), public/published real-ODMR anchor data, and
   NVRNet-style adapter-based transfer design. Full text in the session record; actionable
   items await Jason's lane assignments.

---

## Addendum L (2026-07-11) — increment-8 execution-infra escalation: RULING = fleet GB10s (Option C)

**Escalation received from the odmr worker (stop-and-report, correct behavior)** and verified:
pre-hoc science frozen at odmr 2207f87 ("committed BEFORE any training" — confirmed in git);
wave-1 chunk-1 teachers both exit 137 (SIGKILL, confirmed from S3 exit_code) = host-RAM OOM
(~17 GB peak v3-load+aug vs g6.xlarge's 16 GiB); second independent blocker = watchdog overrun
(bc ~99 s/ep, bc_sam ~140 s/ep ⇒ 15–25 h on L4 vs 720-min cap; ensemble×5+SAM is fundamentally
long). No live instances, no ongoing spend (~$0.15 total cost of discovery). Quota still 8
(case open), spot 0. The infra smoke test used a placeholder cmd, so real training memory/time
was never exercised on L4 — booked as a harness lesson: future smoke = 2-epoch real-recipe run.

**RULING: Option C — execute increment-8 entirely on the fleet GB10s (spark2 + spark3), 2
concurrent, house nohup+pidfile+heartbeat pattern.** Rationale: (i) at the current 8-vCPU quota
AWS offers ≤ the fleet's parallelism (g6.2xlarge would fix OOM but = 8 vCPU = 1 concurrent —
strictly worse); (ii) GB10 IS v6's original training environment — the environment-shift
confound collapses and kd1 connects directly to increment-7's actual numbers; (iii) $0,
unblocked today; (iv) 128 GB unified memory and no watchdog moot both blockers with zero code
change (worker confirmed the frozen code runs on GB10 as-is). Expected makespan ~3.5–5 days at
2×GB10 (~195 GPU-h).

**Amendments to dispatch-9 (execution only — science unchanged, pre-hoc verdict untouched):**
1. Compute target = spark2 + spark3 GB10s. spark3 reached over ConnectX (10.0.0.3); dataset/
   repo sync via 200GbE; verify spark3 GPU idle before scheduling onto it.
2. §0-ii now records: training environment = GB10 (same as v6/increment-7). Stop-condition 1
   (baseline-env vs v6 material shift) RETAINED as a consistency gate — it now guards
   torch-version/library drift instead of hardware shift. baseline-env arm RETAINED (its n=5
   seed-spread measurement of the incumbent recipe is unchanged in value).
3. NO mid-increment migration to AWS if the quota raise lands — one environment per increment.
   Schedule longest-first (bc_sam) to minimize makespan; keep both GPUs saturated.
4. AWS stays warm, nothing torn down (bucket, content-addressed dataset, validated harness incl.
   the worker's --chunk/--stage-dir extensions at gpu-fanout 8328f48). Credits re-earmarked:
   (a) a future wider matrix (increment-9+, more seeds/ablations) on g6.2xlarge×N once the
   64-vCPU raise lands; (b) v4 fidelity dataset generation — embarrassingly parallel,
   environment-insensitive, and now fully de-risked: **CUDA-Q L4 validation r2 PASSED**
   (1,024 batched Lindblad evolutions, 201 steps, 4.08 s on L4 — comparable to GB10's 4.51 s;
   corrects Addendum K item 3 "r2 in flight").

Dispatched back down to the odmr worker via Jason relay.

---

## Addendum M (2026-07-11) — Option C VETOED by Jason (sparks not lockable); superseding ruling: AWS g6e.xlarge

1. **Jason vetoed the Addendum L fleet ruling**: spark2/spark3 cannot be locked down for
   multi-day runs — that constraint was the original motivation for AWS. His stated fallback
   was holding for the spark4 RMA replacement.
2. **Hold is unnecessary — superseding ruling: AWS g6e.xlarge, us-east-1, 2 concurrent.**
   Verified specs: g6e.xlarge = 4 vCPU / 32 GiB host RAM / 1× L40S 48 GB. Under the existing
   8-vCPU quota this keeps 2-concurrent (equal to the fleet plan), the 32 GiB host RAM clears
   the measured ~17 GB OOM, and the L40S clears the watchdog problem (raised to 30 h for
   bc_sam headroom). Cost ≈ $360–450 of credits for the ~195 GPU-h matrix. Multi-region
   checked and rejected: G/VT quota = 0 in us-east-2/us-west-2/eu-west-1.
3. **Environment ruling:** all increment-8 runs on g6e.xlarge/L40S — one uniform environment.
   The §0-ii cross-hardware framing and stop-condition 1 (baseline-env vs GB10-v6 material
   shift) return to their ORIGINAL dispatch-9 roles (the baseline-env arm was designed for
   exactly this). If the 64-vCPU raise lands mid-increment, scaling CONCURRENCY on the same
   instance type is permitted (not an environment change); switching instance type mid-
   increment is not.
4. **NGC/NIM ruled NOT APPLICABLE to this problem** (Jason asked): NGC is a container
   registry (no compute); NIM free credits are hosted-inference API calls on NVIDIA-served
   models — they cannot execute arbitrary PyTorch training. The one NVIDIA-compute angle
   would be Brev (NVIDIA's GPU-VM cloud) IF Jason holds credits there — parked as optional,
   not needed given the g6e path.
5. Config landed: gpu-fanout `fanout.env` → FANOUT_INSTANCE_TYPE=g6e.xlarge,
   FANOUT_MAX_RUN_MINUTES=1800. Harness lesson from Addendum L stands: chunk-1 (2 teachers)
   doubles as the real-recipe smoke — verify RAM headroom + epoch pace from its logs before
   draining the waves.

---

## Addendum N (2026-07-11) — chunk-1 time/cost escalation RULED: proceed all arms, budget cap $800, 24h stop-line lifted

Worker escalation verified: teacher_e1 AND teacher_e2 both exit 0 on g6e.xlarge with valid
2.8 MB checkpoints in S3 (OOM cleared; infra pipeline proven on the real recipe; 2 of 5
teachers already banked). Measured pace: L40S 76.7 s/epoch vs GB10 38.9 (~1.97× slower —
latency-bound sequential BPTT; throughput GPUs don't help). Cost projection revised
$105–160 → ~$650–700 full increment. Month-to-date net spend ≈ $0 (credits absorbing).

**RULINGS (Jason directives 2026-07-11: "make sure it's running efficiently"; "if it needs to
go longer than 24 hours let it"):**
- **(A) Budget AUTHORIZED, hard cap $800** for the full increment (grounded in Jason's
  standing credits directives and his relay of this escalation). Worker reports projected +
  actual spend at each wave boundary; stop-and-report if the cap is threatened.
- **(B) = B[i], strengthened by Jason's override: the 24 h monitor stop-line is LIFTED.**
  Proceed with ALL arms including bc_sam. The watchdog is pure hang-protection, raised to
  48 h (fanout.env committed). An arm/seed is dropped only on watchdog kill or a guard trip —
  the data decides, not the clock. (Teacher early-stop @160 supports the optimistic case.)
- **(C) Instance type stays g6e.xlarge** — switching mid-increment is an environment change
  (barred), and nothing faster exists in quota anyway: the workload is kernel-launch-latency
  bound, so bigger cloud GPUs don't help. Concurrency scaling on quota raise remains allowed.
- **Efficiency question (Jason) answered honestly:** the ~2× vs GB10 is intrinsic to the
  frozen recipe's sequential BPTT on cloud GPUs (GB10 wins on launch latency via Grace-
  Blackwell integration, not raw compute). The known fixes — torch.compile, CUDA graphs,
  fused/batched BPTT — are training-environment/recipe changes BARRED mid-increment by the
  pre-hoc freeze. Booked as candidate increment-9 lane work: "cloud-efficient training path
  (compile/graphs), pre-declared, validated recipe-neutral vs a GB10 reference run."

---


