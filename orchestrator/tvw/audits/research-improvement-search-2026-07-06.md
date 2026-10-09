# Improvement search — odmr-vector-tracking identity gap (2026-07-06)

**Type:** inventory + external/internal search. **No implementation authorized or performed.**
**Scope:** what went wrong across the tracker lineage, then a skills/API-driven sweep for
models, ML-parameter changes, papers, and adaptable code that could improve results — ranked by
how many of our open issues each item would plausibly close, most first.

**Method.** (1) Failure inventory from the repo (`odmr-vector-tracking` at origin
`increment-2-learned-tracker` HEAD 46db71b + spark1 archive) and the TVW audit trail. (2) Internal
corpus sweep (`odmr-pnt-nv-docs`, `tychon-physics`, `polarfire-control-corpus`; embedder pre-flight
green). (3) External sweep: the `deep-research` workflow (run `wf_737b6676-bb1` — 105 agents, 5
angles, 23 sources → 113 claims → **25 adversarially verified, 22 confirmed / 3 refuted**) plus my
own firecrawl paper-inspect / GitHub / docs verification. Each citation is **CONFIRMED** (a primary
source was quote-verified) or **PLAUSIBLE** (surfaced, not full-text verified). Refuted claims and
un-answered questions are reported for transparency — they change the recommendations.

---

## 1. What went wrong — the inventory

### The one thing that works (the constraint)
The **field / vector-lock claim survives and is deployable**: the learned tracker holds the vector
estimate through kinematically adversarial crossings where classical trackers lose lock — OU
family 0/30 lost locks vs CV-KF 19/30; pooled seeded lock-loss 56/270 (best seed 8/90) vs KF 70,
NLS 83, PID 90. **Non-negotiable constraint on every item below: do not damage this.** The field
estimate `b_est` comes from `state_to_proj(state)`→BLUE and never consumes the association
(`learned.py:543,585`), so an identity fix that is a *re-decode* of the score tensor cannot touch
it by construction. **That structural fact is the whole strategy** — and it turns out the radar/sonar
field independently arrived at the same design (decouple identity from the state estimate; see §3 Q1).

### The open problem (narrow and specific)
**Line identity during long merged dwells** — the `held` trajectory family at clean / high SNR:
learned in-collision misassoc **0.31 vs CV-KF 0.10**. Localized: by SNR10 the two converge and the
learned tracker wins identity on OU and reversal; KF's apparent SNR3 identity "win" is a lost-lock
artifact (28/37 held sequences lost). Residual = clean/SNR30 `held` only.

> **Reframing from the verified literature (load-bearing):** this exact failure is *track
> coalescence*, a 40-year-old, structural property of Bayesian-marginal trackers — **not** a defect
> unique to our learned model. Classical JPDA coalesces closely-spaced tracks for the same reason
> (Blom & Bloem 2000, CONFIRMED). And labeled-RFS "mixed-labelling" theory proves that after a
> *sufficiently long* merged dwell, label corruption can become **total and permanent** — "all
> possible label assignments become equally probable at all later times" (Garcia-Fernández 2016 /
> Boers 2010, CONFIRMED). **Implication: the honest target is graceful identity degradation +
> offline overlay re-decode, not guaranteed recovery.** We should stop trying to "solve" held-family
> identity inside the online tracker and instead (a) keep the field estimate clean and (b) recover
> what identity is recoverable as a separate, offline overlay.

### Dead levers — do NOT re-propose (all failed on the survival rule)
| Lever | Outcome | Source |
|---|---|---|
| soft/merged-CE targets | eliminated (2c) | `docs/increment2c_results.md` |
| Sinkhorn / OT matching | eliminated (2c) | ″ |
| scheduled sampling (any ramp) | eliminated, 42 cells; self-confirming lock | ″ |
| B3 hard motion-prior gate | rejected; regressed every closed-loop metric | 2b record / memory |
| greedy / smooth5 / smooth15 re-decode | help only at SNR3, regress the target regime | `increment2c_results.md` §re-decode |
| physics-snap (A1) / physics+smooth (A3) | **won OU+reversal, REGRESSED held** | ″ |
| **lever-B trained appearance-fingerprint branch** | **FAILED** — seed-unstable 0.18/0.55/0.41; halved IDSW but raised misassoc; **doubled SNR3 field lock-loss 56→105/270** (no SNR-graceful fallback) | `docs/increment3_results.md`, commits 36b3b97/46db71b |

**The fingerprint is the lever-B failure** — the "fingerprint didn't work" the user recalled.
Retained in code but **gated OFF by default** (`LearnedTrackerConfig.appearance_branch`); the shipped
tracker is byte-identical to the wave-2 `gated+linear+aug` reference. Note: its failure had **two
independent causes** — seed instability *and* no SNR-graceful fallback — and §3 only has a verified
fix for the second (see Q3b). The first (Q3a) is an open question.

### The model, for reference
`LearnedTracker` (custom; not off-the-shelf): **~177K params** deployable default (gated core +
linear association), 165K relu variant. obs_embed 123K, gated core 25K, state_to_tracks 17K,
extractor 9.5K, association 2.7K, BLUE decode 12 (frozen). **Only the 9.5K-param FrameFeatureExtractor
is V250-NPU-bound (INT8);** recurrence + association + BLUE run host-side float — so identity
mechanisms have the full float op-set. Tier-0 probe (polarfire, 2026-07-02): the
sigmoid/tanh/softmax op-ban is **falsified**; the real NPU blocker is **topology** (single graph
input) — the GRU cell crashes `vnnx_compile`. Flat loss weights today
(`w_assoc=w_pos=w_track=w_proj=1.0`, per the `appfp` run summary).

### Still-open caveats (honest gaps, not failures)
- v1/v2 largely **noiseless**; the shot-noise ladder is the hardening axis, and lever-B's SNR3
  damage proves identity work must be scored on the noise ladder, not just clean.
- **NLS warm-started forward-model** was the strongest classical attack (2b) — any new identity
  claim must clear it, not just CV-KF.
- Hyperfine ¹⁴N (L=24) deferred; **NV–NV cross-relaxation dips absent from the simulator** (a real
  1–4% contrast feature at inter-orientation degeneracy — exactly the crossing window).

---

## 2. Internal corpus — what we already hold
We own the adjacent-domain anchors but **not** the coalescence/data-association literature that turns
out to be central (§3 Q1):
- `odmr-pnt-nv-docs`: Yao/Zu **arXiv:2603.14728** (1D-CNN NV vector) indexed + in `references.md`.
- `tychon-physics`: **arXiv:2603.14144** (PINN Ramsey); Wang 2023 diamond-magnetometry-navigation
  (probabilistic multiple-hypothesis / PDA map-matching — a data-association analogue we own but
  never mined); `05_nv_ambiguous_resonances`.
- **Gap:** no track-coalescence, JPDA*/Set-JPDA, unresolved-measurement MHT, or labeled-RFS material
  in any corpus. If we pursue §4, ingest that source set into `odmr-pnt-nv-docs` (item H2).

---

## 3. External search — findings by question (verification-tagged)

### Q1 — Coalescence theory (the keystone, now sharpened)
Our failure is the classical **track-coalescence** problem, and the field has three mature fixes that
are all **architecturally isomorphic to our constraint** (they maintain identity through extended
merges while leaving the state estimate intact):

- **CONFIRMED — Set-JPDA (Svensson, Svensson, Guerriero, Crouse, Willett; SPIE 8050 805010, 2011).**
  Localizes targets **label-free** (coalescence-free *state*), then "identities are recalled as an
  **overlay**." The overlay by construction never feeds back into the state → **exact match to our
  non-negotiable constraint**, and it runs offline over the saved `(B,T,8,60)` tensor with zero
  retraining. *This is the top architectural template for the held fix.*
- **CONFIRMED — Koch & van Keuk, "MHT track maintenance with possibly unresolved measurements"
  (IEEE TAES 33(3):883–892, 1997).** The canonical mechanism for maintaining the identity of
  **exactly two** established tracks through an **extended** merged episode (formation flight) via an
  explicit sensor-resolution model — **structurally identical to the held family** (known count,
  long sub-resolution dwell, identity *maintenance* not initiation).
- **CONFIRMED (modern realization, my direct verify) — Saucan, Meyer, Willett, "Gaussian Belief
  Propagation for Tracking With Unresolved Measurements" (arXiv:2606.31716, 2026-06-30).** The 2026
  BP form of Koch/van Keuk's idea: any subset of objects may generate one unresolved measurement;
  GLBP complexity **O(m·n·2ⁿ)** → for n=8, 256·(m·n), trivial host-side. **Post-dates our 07-02
  sweep.** Reinforces Q1 as the state-of-the-art path.
- **CONFIRMED — JPDA\* (Blom & Bloem, IEEE TAC 45(2):247–259, 2000).** A **decode-side** change
  (prune permutation hypotheses before merging) that leaves the estimator's update equations intact —
  can run as an offline re-decode over the score tensor. **Caveat (REFUTED overreach):** the claim
  that JPDA\* escapes the trade-off (beats coalescence *and* clutter/missed-detections) was **refuted
  0-3**; hard pruning buys identity at the cost of low-SNR robustness — *our exact tension*, so this
  is a caution, not a free lunch.
- **CONFIRMED — mixed-labelling guardrail (García-Fernández, IEEE TAES 52(5), 2016; Boers 2010).**
  Extended proximity → possibly **permanent** label corruption; but label-switching machinery
  reorganizes labels **without altering the unlabelled state** — the invariance our constraint relies
  on. Design principle, not code: aim for graceful degradation, exploit label/state decoupling.

### Q2 — Spectral-line decoders that plug into the saved (B,T,8,60) tensor (zero-retrain)
- **CONFIRMED — Luo & Shen (Sensors 2019, 19(22):4866): HMM + Viterbi lofargram line tracking.** The
  exact offline re-decode shape we want (Viterbi over the score tensor, low effort to prototype) —
  **but** it extracts lines by greedy amplitude peel-off with **no joint cross-line assignment and no
  crossing/merge resolution**, so a joint-assignment step must be *added*. Good re-decode skeleton,
  not a held-family solution by itself.
- **CONFIRMED — Silbido profundo / DeepWhistle (Li et al., IJCNN 2020; Roch et al., JASA 2011).** The
  CNN is a **detector**, not a decoder; all identity/crossing logic lives in a separate classical
  **graph-search tonal tracker** whose **forward/backward polynomial-fit branch disambiguation at
  crossing nodes** is the reusable *algorithm reference* for our decode step.
- **CONFIRMED dead-ends (reported to save effort):** DeepLofargram (arXiv:1912.00605) is
  **single-line only**, multi-line explicitly deferred; GC-MS DP peak alignment (Robinson 2007) is a
  static cross-*experiment* matcher, poor fit without reframing the time axis.
- PLAUSIBLE Python route for the Viterbi skeleton: `pomegranate` (MIT); `bmwcarit/hmm-lib`
  (Apache-2.0, time-inhomogeneous transitions — matches per-frame-varying merge structure).

### Q3 — Fingerprint stabilization + SNR-graceful gating
- **Q3b (the fix for lever-B's low-SNR failure) — CONFIRMED, Deep OC-SORT (Maggiolino et al., ICIP
  2023, arXiv:2302.11813).** Two concrete, position-preserving, SNR-graceful formulas:
  1. **Dynamic Appearance (confidence-gated EMA):** `α_t = α_f + (1−α_f)·(1 − (s_det−σ)/(1−σ))`,
     `α_f=0.95`; at the threshold `s_det=σ` the new embedding is *totally ignored*, scaling to full
     incorporation at `s_det=1`; **no new hyperparameters**. *Transfer: substitute a per-line
     SNR/photon-count proxy for `s_det`.*
  2. **Adaptive Weighting (first-vs-second-best margin):** boost appearance only where the top-vs-
     runner-up cosine margin `z_diff` is large; **during a merged dwell all candidates look alike →
     the margin collapses → cost reverts to motion/position.** Exactly the graceful fallback lever-B
     lacked. Both keep the field estimate untouched. Maintained impl in `mikel-brostrom/boxmot`
     (confirm boxmot license before *code* reuse; the **formulas** are reusable regardless).
  - **CAVEAT:** gating repairs the low-SNR damage, **not** the seed instability.
- **Q3a (seed instability, 0.18/0.55/0.41) — OPEN.** SAM / SWA / EMA / ensemble-distillation with
  *tracking-specific* evidence produced **no claim that survived verification** this sweep. The
  07-02 research memo's EMA(0.999)+3–5-seed suggestion stands as *prior-motivated, not freshly
  verified*. Treat as an open question needing a dedicated follow-up (see §5).

### Q4 — Architecture delta 2025-26 (small-K, host-side)
- **CONFIRMED (mechanism only) — Samba / SambaMOTR (ICLR 2025, arXiv:2410.01806, code
  `mattiasegu/sambamotr`, MIT, PyTorch).** Instantiates the target pattern: **one shared-weight
  Mamba unit per tracklet, coupled only through a permutation-equivariant memory-sync layer**; linear
  in sequence length, quadratic in tracklet count (trivial at K=8). **BUT:** (a) its SOTA benchmark
  numbers were **REFUTED 0-3** — cite the *mechanism*, never the wins; (b) it reports **no parameter
  counts** — the sub-500K feasibility question is **UNANSWERED**; (c) adopting it *couples the
  per-target recurrences*, which **touches the shared recurrent core** → a field-lock risk that must
  be firewalled. Reference-only, higher-risk, retrain-required.
- Parameter-count evidence: none survived. (Prior memo noted MANTa <50K as a competent tiny
  associator; not re-verified here.) Practical read: our 177K is not the bottleneck — the association
  *mechanism* is.

### Q5 — NV/ODMR novelty delta since 2026-07-02
- **CONFIRMED (my direct verify) — arXiv:2606.02749 (Rieckmann, Afshar, Goldberg, Childress, Scheel,
  Heshami, 2026-06-01):** full **vector magnetometry** via **two broadband MW pulses** + **deep
  neural networks**, reading line splitting; 5–100 pT/√Hz, 25 µT floor, no bias beyond Earth's field.
  **It is a static single-shot NN vector solver — NOT a sequential stream tracker, NOT
  through-crossing/identity.** It does **not** break our "no ML through-crossing tracker / no
  sequential NN over ODMR streams" claim, but it **is** a new NN-vector-magnetometry competitor (a
  *different modality*: broadband transmission vs swept CW-ODMR) and **must be logged in
  `references.md` and cited to distinguish** in any outward-facing framing.
- **The workflow's Q5 sweep surfaced no *additional* verified new work** (no verified follow-up to
  Yao/Zu 2603.14728 or the PINN Ramsey 2603.14144; no other through-crossing/sequential-NN-over-ODMR
  claim). **Core novelty holds** — but the sweep is only as current as today, so re-run a dedicated
  novelty check before any external claim (§5, open).

### Q6 — Training recipe — OPEN
- No quantitative-evidence claim survived verification (curriculum, spectra augmentation, multi-seed
  selection, optimizer/schedule). One directly-surfaced anchor stands *outside* the verified set:
  **Kendall & Gal, arXiv:1705.07115** (homoscedastic-uncertainty task weighting) — the principled
  replacement for our flat loss weights, with a large MTL evidence base. Low-risk, independent of the
  identity mechanism, but treat as *un-adversarially-verified* here. Q6 overall = open.

### Q7 — Adaptable code inventory (verification-grounded)
| Repo / source | License | Lang / state | Reuse | Effort |
|---|---|---|---|---|
| **dstl/Stone-Soup** | MIT | Python, **active (v1.9.1, 2026-06-24)** | JPDA, **JPDAwithLBP (loopy-BP)**, JPDAwithEHM/EHM2 (exact marginals), GNN — importable substrate. **JPDA\*/Set-JPDA are NOT shipped** (grep-verified zero hits) → build on the JPDA/EHM base. Labeled-RFS/GLMB presence **UNRESOLVED** (negative claim refuted 0-3 — verify the updater module directly). | LOW (JPDA/EHM/GNN) / MED (JPDA\*, SJPDA subclass) |
| Deep OC-SORT | paper reusable; boxmot license TBV | Python/PyTorch, active | the **two gating formulas** (portable from the paper regardless of repo license) | LOW |
| Samba / SambaMOTR | MIT | PyTorch, research | architecture *reference* (per-target shared-weight recurrence + equivariant coupling); no param guidance | MED–HIGH |
| pomegranate / bmwcarit/hmm-lib | MIT / Apache-2.0 | Python / Java | Viterbi joint re-decode skeleton | LOW / reference |
| Silbido / DeepWhistle | (silbido MATLAB + ONNX) | active | graph-search crossing-branch disambiguation *idea* | MED (reference) |
| Luo & Shen lofargram HMM | no public repo | — | re-implement Viterbi over the tensor; ADD joint assignment | LOW + MED |
| nmrglue / multinmrfit | BSD / GPLv3 | Python | series peak-reassignment idea | reference |
| DeepLofargram / GC-MS DP align | — | — | **avoid** (single-line / static cross-experiment) | — |

**Already-surveyed (per the brief; treat as algorithm/eval references, confirm license before reuse):**
TrackEval, t-gospa-python, KalmanNet, Trackastra, MOTRv2, TFD-Net.

---

## 4. Ranked recommendations — most issues closed first

> Inventory + search only. **Nothing here is authorized for implementation;** phase-tagging and
> go/no-go are the user's call. Guiding rule (from the verified constraint): **prefer offline
> re-decode over the saved `(B,T,8,60)` tensor** — it structurally cannot perturb the field estimate;
> reserve anything that touches the shared recurrent core (item 7) for last and firewall it.

1. **Set-JPDA "identity-as-overlay" decode** (Svensson 2011). Closes: the held gap via the design
   that *is* our constraint — label-free state + identity recalled as a separate offline overlay;
   zero-retrain; **cannot touch the field estimate by construction.** Highest leverage, lowest risk.
   *(Not off-the-shelf in Stone Soup — custom build on its JPDA/EHM base, MED effort.)*
2. **Unresolved-measurement decode for the 2-line merge** — Koch & van Keuk (1997) as the canonical
   model, **GLBP-unresolved** (Saucan/Meyer 2606.31716, 2026) as the modern host-side realization
   (O(m·n·2ⁿ), trivial at n=8). Closes: identity through *extended* merges specifically — the exact
   held regime; offline, field-safe.
3. **Deep OC-SORT dual SNR-graceful gating** (Maggiolino 2023). Closes: the *specific* reason lever-B
   doubled SNR3 lock-loss; formula-level, LOW effort; makes any future appearance cue degrade
   gracefully and revert to position during merges. Position/field estimate untouched.
4. **Loopy-BP / EHM association re-decode using Stone Soup as substrate** (JPDAwithLBP). Closes: a
   large chunk of coalescence directly; importable MIT code as the scaffold for items 1–2; zero-retrain
   re-decode → field-safe. (BP provably reduces coalescence — Kropfreiter/Meyer/Willett.)
5. **Viterbi joint re-decode** (Luo/Shen skeleton + `pomegranate`), **with an added joint cross-line
   assignment step**, and the Silbido forward/backward crossing-disambiguation as the assignment
   heuristic. Closes: part of held; zero-retrain; natural baseline/companion to 1–2.
6. **JPDA\* decode-side coalescence-avoidance** (Blom & Bloem 2000). Closes: coalescence via
   hypothesis pruning, estimator untouched — **but** pruning trades low-SNR robustness (refuted that
   it escapes the trade-off), so gate it behind the item-3 SNR logic. Field-safe, use with care.
7. **Samba coupling pattern** — *only if a retrain is on the table.* Closes: long-merge memory
   structurally; **must be firewalled from the field estimate** (touches the shared recurrence),
   lacks param guidance, benchmark wins unverified. Higher risk, later.
8. **Seed-stability pass before any *retrained* identity lever** (EMA/SWA/SAM + 3–5-seed selection).
   Closes: the 5× seed variance that sank lever-B — a *prerequisite* for any appearance retrain.
   **NOTE:** open question (Q3a) — no tracking-specific evidence survived verification; validate the
   recipe on our data before relying on it.
9. **Learned uncertainty loss-weighting** (Kendall–Gal 1705.07115) replacing flat weights. Closes: a
   plausible slice of the train→closed-loop gap; low-risk, independent. **NOTE:** not in the
   adversarially-verified set.
10. **Cross-relaxation / hyperfine identity features in the simulator** (nv-sim lineage). Closes: a
    *physical*, non-seed-fragile identity cue that exists exactly in the crossing window (1–4%
    contrast) but is absent from our data. Larger lift (dataset + physics); the honest long game.

**Hygiene (cheap, protects the claims — not ranked with the above):**
- **H1.** Log arXiv:2606.02749 in `references.md` with the "static NN solver, not a tracker"
  distinction (novelty hygiene for outward material).
- **H2.** Ingest the coalescence / JPDA* / Set-JPDA / unresolved-measurement / labeled-RFS source set
  into `odmr-pnt-nv-docs` so retrieval can ground items 1–6 next session.
- **H3.** Adopt the **mixed-labelling guardrail** as the stated goal: graceful identity degradation +
  offline overlay, *not* guaranteed recovery — set expectations in the deck/claims accordingly.
- **H4.** Score any identity item on the **noise ladder against the NLS baseline**, not just CV-KF
  clean — the strongest classical attack and where lever-B's damage hid.

**Cross-cutting:** items 1–6 are zero-retrain, offline, and structurally field-safe — start there
*because* they cannot regress the one thing that works. 7–10 are the retrain-tier bets. The verified
message is singular: **treat identity as a decode-side overlay, keep the field estimate label-free,
and expect graceful degradation rather than a merge "solution."**

---

## 5. Open questions the search could NOT close (report, don't paper over)
- **Q3a — seed instability:** no tracking-specific SAM/SWA/EMA/ensemble evidence survived. The
  fingerprint's 5× seed variance has **no verified remedy** yet.
- **Q5 — novelty:** the sweep found no *new* through-crossing / sequential-NN-over-ODMR competitor,
  but a dedicated re-run is required before any external "nobody else does this" claim.
- **Q6 — training recipe:** no quantitative-evidence claim survived (curriculum, augmentation,
  seed-selection, optimizer). Kendall–Gal is a lead, not a verified result.
- **Q4 param count:** minimum model size for the per-target-recurrence + equivariant-coupling pattern
  at K=8 is unanswered.
- **Stone Soup labeled-RFS:** GLMB/LMB availability is genuinely unresolved (negative claim refuted) —
  check the updater module directly before build-vs-reuse.

*Full verified evidence, votes, and refutations: deep-research run `wf_737b6676-bb1`
(`…/tasks/wi4lxir5p.output`). This deliverable is inventory + search only — no code was changed.*

---

## Outcome addendum (2026-07-07) — Dispatch 4 executed: items 1/2/4/5 TESTED, NO SURVIVOR

Ranked items 1 (Set-JPDA overlay), 2 (unresolved-measurement decode), 4 (BP/EHM marginals) and
5 (joint Viterbi) were executed as `dispatch-4-identity-overlay-2026-07-06.md` in the tracking
repo (branch `increment-4-identity-overlay`, HEAD 9b82aa1; `docs/increment4_results.md`).
**Verdict: none survives the survival rule on held** (best: D-UM r=2 at 0.298 vs baseline 0.311 —
not CI-disjoint, one seed regresses, OU/reversal guards trip). Parity gate passed; field metrics
byte-identical throughout; deployable default unchanged.

**Root cause (measured, Step-0 dwell diagnostic):** held is a long-merge family (median merged
run ≈ 132 frames); once two lines sit within a linewidth, both the association scores and the
physics forward-map predictions are sub-linewidth-separated — the decode stage is
**information-starved**, and no re-weighting of starved information recovers identity. The
mixed-labelling caveat (§3 Q1, García-Fernández/Boers) is empirically confirmed on our data.
CV-KF's long-dwell 0.022 misassoc reflects **prior-matching** (its CV coast matches the
generator's crossing kinematics), not superior measurement use.

**Standing consequence: the zero-retrain / decode-side tier is EXHAUSTED.** Do not re-propose
read-out improvements of the existing signal (this now covers items 1, 2, 4, 5, 6 plus all 2c
re-decodes). Items still live: **3** (SNR-graceful gating — as a component of any future
appearance channel), **8** (seed-stability pass — still blocked on open Q3a), **9** (uncertainty
loss-weighting — retrain-tier), **10** (physics identity cues in the simulator — **promoted to
the active path**, together with the H3 boundary-claim measurement via a dwell-sweep dataset).
Successor dispatch: `dispatch-nvsim-identity-physics-2026-07-07.md`.

---

## Outcome addendum 2 (2026-07-07 evening) — item 10 executed; ranking superseded by a coverage finding

The nv-sim dispatch delivered (`sequence_dwell_v1` / `_cues`, seed-paired, branch
`feat/dwell-identity-lineage` cec6591; one accepted physics deviation — merges are quartets,
see `audit-dwell-program-2026-07-07.md` §1). The consumer side ran as **increment-5** in the
odmr session (ratified retroactively — no TVW dispatch existed; verdict rules were pre-hoc in
`experiments/increment5_verdict.py`; odmr main promoted to dde2a74 on NAS + private GitHub).

**Item 10 outcome: zero-retrain cue exploitation FAILED; cues are retrain-tier.** The CR dip
guard-trips the current checkpoints (field lock-loss 432/864 → 783/864, CI-disjoint every rung);
strain offsets are an exact null at ~MHz candidate resolution. The H3 boundary measurement
succeeded and is the primary result: in-coverage learned exit identity is graceful in dwell
(no observed cliff, D=8→192), and the topology-balanced eval measured CV-KF's identity crown as
CV-prior-matching (bounce 0.407 vs learned A3 0.045 switches/opportunity).

**Ranking superseded:** the eval discovered a **deterministic training-coverage gap** — cold
field acquisition fails 216/216 (all seeds) on merge geometries requiring 41–53° off-bias at
3.3–3.9 mT, jointly outside the ≤18° / ~4.7–5.8 mT training envelope. **Angular/magnitude field
coverage is now the top program lever, ranked above every identity item.** Successor dispatches:
`dispatch-nvsim-sequence-train-v3-2026-07-07.md` (v3 coverage lineage + fieldcone eval) and
`dispatch-6-coverage-retrain-2026-07-07.md` (conditional coverage retrain). Items 3/8/9 unchanged;
the cue-retrain lineage is the next candidate after increment-6, pending its own go-ahead.
