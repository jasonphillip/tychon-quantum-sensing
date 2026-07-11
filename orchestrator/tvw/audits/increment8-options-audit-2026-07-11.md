# Increment-8 options audit — is "(a) capacity vs (b) distillation refinement" exhaustive?

**Date:** 2026-07-11. **Trigger:** increment-7 keep-nothing escalation (Addendum H,
`audit-dwell-program-2026-07-07.md`). **Method:** three parallel TVW research agents
(2026-07-11): (1) KD-reliability literature, (2) training-stability literature, (3) adversarial
option-space completeness check. All load-bearing arXiv IDs fetch-verified this session; full
texts ETL'd into `~/.corpus/odmr-pnt-nv-docs` (Qwen3-Embedding-4B, Spark2). **Status:** decision
support only — the direction pick is Jason's; no dispatch is drafted from this document.

---

## 1. The measured failure this must solve

At fixed capacity (175,790 params, frozen v6 architecture, frozen v3 data), single-teacher KD
(α=0.5, T=2.0) recovered in-cone identity in 2 of 3 student seeds — one fully into v2 territory,
both skills held — but seed 20260721 landed **worse than v6**. No guard ever tripped: the two
skills are not in opposition at eval time. The binding failure is **reliability-at-fixed-capacity**
— the model can fit both skills; the training trajectory doesn't find that solution reproducibly.
Held misassoc per-seed: 0.262 / 0.340 / 0.604 (v6: 0.508 / 0.530 / 0.581).

## 2. Verdict on the (a)/(b) dichotomy

**NOT exhaustive.** The escalation framed two paths — (a) capacity bump, (b) distillation-recipe
refinement. The sweep found **four additional constraint-surviving option families**, two of which
target the measured failure mode *more directly* than either (a) or (b):

| | Family | One-line mechanism | Constraint verdict |
|---|---|---|---|
| **A** | Capacity bump (original a) | More params | Survives, but costs NPU re-check + `.vnnx` recompile (Beelink handoff) |
| **B** | Target-signal refinement (original b, widened) | Better teacher signal: ensemble/multi-response teacher, logit standardization, consistent-view + patience, α retuning, churn-constrained co-distillation | Survives; training-time only |
| **C** | Trajectory-stability levers — **NEW** | SAM/ASAM flat-minima optimization; SWA/EMA weight averaging; shared-early-checkpoint seed branching | Survives; the only family whose literature *directly targets* seed variance |
| **D** | Cross-seed weight aggregation — **NEW** | Average the 3 seeds' weights into ONE same-shape model (soup) | Gray-zone: valid only if runs share a basin (needs C's branching); re-basin merging unreliable at 176k-param width |
| **E** | Explicit sequential retention — **NEW** | Two-stage training + EWC Fisher penalty (or selective freezing) at fixed shape | Survives; deterministic retention vs KD's stochastic rescue |
| **F** | Collapse-exact over-parameterized training — **NEW** | ExpandNets/RepVGG-style: train each conv/dense expanded into consecutive linear layers, contract *algebraically exactly* to the 175,790-param deployed net | Survives as constraints are written — **this is option (a)'s optimization benefit with zero deployment cost** (no NPU re-check, no recompile) |

Family F is the sharpest structural miss: the program's constraints bind the *deployed artifact*,
not the training-time computation graph, and linear over-parameterization contracts exactly (same
ops, same param count, byte-identical shape). Family C is the cheapest and composes with everything.

## 3. What the literature says about our exact failure (key findings, ETL'd)

**Where seed variance comes from — and why "fix the RNG" can't work.**
- Summers & Dinneen 2021 (arXiv:2103.04514): every individual nondeterminism source (init, data
  order, augmentation, cuDNN) produces statistically indistinguishable variance; a single-bit
  weight perturbation yields the full run-to-run spread. Variance is an **instability property of
  the optimization trajectory**, not of any one noise source. Deterministic ordering merely
  freezes one lottery draw (epistemically adjacent to cherry-picking an RNG stream).
- Bouthillier et al. 2021 (arXiv:2103.03098): data-order variance ≥ init variance as contributor.
- Picard 2021 (arXiv:2109.08203): seed spread is first-class even in standardized trainings;
  3 seeds is far too few to estimate the tail — relevant to how increment-8's verdict counts seeds.

**Why 7b half-worked — KD variance theory.**
- Safaryan et al. 2023 (arXiv:2305.17581): KD acts as *partial* stochastic variance reduction whose
  strength depends on the distillation weight — consistent with α=0.5 single-teacher stabilizing
  only 2/3 seeds.
- Cui & Pei 2026 (arXiv:2601.18909): formalizes **inter-student variance** (our exact metric) vs
  intra-student; single-response KD suppresses the latter, not the former; averaging k teacher
  responses shrinks the noise **O(1/k)** — the theoretical backbone for the ensemble-teacher fix.
- Stanton et al. 2021 (arXiv:2106.05945): student-teacher fidelity is limited by optimization
  difficulty, not capacity — independently matches the Addendum H diagnosis.
- Cho & Hariharan 2019 (arXiv:1910.01348): bigger/more accurate teachers often distill WORSE
  (capacity mismatch); early-stopped teachers distill better. Caution: don't fix the seed problem
  by scaling the 4× teacher.

**Family B levers with direct churn/jitter evidence.**
- Jiang et al. 2021 (arXiv:2106.02654): distillation from the prior model is provably a churn
  constraint — the principled recipe for making a retrain land near a prior artifact.
- Bhojanapalli et al. 2021 (arXiv:2102.03349): co-distillation + min-entropy regularizer reduce
  cross-seed prediction disagreement at fixed architecture.
- Hidey et al. 2022 (arXiv:2204.04735): production study; ensembling and co-distillation reduce
  seed-to-seed "model jitter," co-distillation best cost/benefit.
- Beyer et al. 2021 (arXiv:2106.05237): consistent teacher/student views + long patient schedules
  make KD markedly more consistent ("function matching").
- Sun et al. 2024 (arXiv:2403.01427): logit standardization removes teacher/student logit-magnitude
  mismatch under shared T — plug-and-play repair for high teacher-student capacity gaps (ours: 4×).
- Wu et al. 2021 (arXiv:2106.14448, R-Drop): consistency regularization; churn-flavored, cheap.

**Family C/D anchors.**
- Foret et al. 2020 (arXiv:2010.01412, SAM); Kaddour et al. 2022 (arXiv:2202.00661): the only
  systematic SWA-vs-SAM comparison reporting across-seed std devs; proposes WASAM (both in one run).
- Izmailov et al. 2018 (arXiv:1803.05407, SWA); Morales-Brotons et al. 2024 (arXiv:2411.18704):
  weight-EMA improves prediction consistency / reduces churn across runs — strongest recent
  free-lever evidence.
- Frankle et al. 2019 (arXiv:1912.05671): networks become stable to SGD noise **early in
  training** — branch the 3 "seeds" from one partially-trained trunk so all land in one basin.
  This both shrinks the lottery AND makes family D souping cleanly valid.
- Wortsman et al. 2022 (arXiv:2203.05482, soups): cross-run weight averaging works only within a
  shared basin (same init / early branch). Ainsworth et al. 2022 (arXiv:2209.04836, Git Re-Basin) +
  Jordan et al. 2023 (arXiv:2211.08403, REPAIR): cross-init merging needs permutation alignment and
  activation-statistic repair, and small/narrow nets are the worst case — honest prior at 176k
  params: **don't bet on cross-init merging; branch-then-soup instead.**

**Family E/F anchors.**
- Kirkpatrick et al. 2016 (arXiv:1612.00796, EWC): explicit Fisher-penalized retention at fixed
  shape — deterministic mechanism, and consistent with the 7c finding (no gradient conflict;
  retention failure is drift, not opposition).
- Guo et al. 2018 (arXiv:1811.10495, ExpandNets): linear over-parameterization during training,
  exact algebraic contraction to the compact net — demonstrated on small conv nets.

**Multi-task side (context, not a lever):** Kendall et al. 2018 (arXiv:1705.07115, uncertainty
task weighting — 2 learned params, removes a brittle hand-set hyperparameter) and Kurin et al.
2022 (arXiv:2201.04122): plain scalarization + standard regularization matches specialized
multi-task optimizers — the productive MTL knob is regularization, not gradient manipulation.
Corroborates dropping the PCGrad family (7c) permanently.

## 4. Families considered and down-weighted (recorded so they stay considered-and-rejected)

- **Curriculum / data ordering on frozen data:** mechanistically adjacent to 7a (static geometric
  re-weighting), which measured no effect. Low prior; at most a free tweak inside another family.
- **Deterministic / pinned-nondeterminism training:** ruled out on the arXiv:2103.04514 evidence —
  it freezes a draw rather than improving the odds; also epistemically close to seed cherry-picking.
- **Inference-time ensembles of the 3 seeds:** VIOLATES deployment constraint (one 175,790-param
  model). Not eligible.
- **"Train N seeds, ship the best":** post-hoc selection as an *adoption rule* violates house
  discipline. But see §5 — there is a legitimate pre-registered version of this question that
  belongs to Jason.
- **Aux self-supervised heads on frozen data:** survives constraints, moderate prior, no strong
  anchor for our regime; revisit only if the composite stacks fail.

## 5. A governance question the sweep surfaced (flagged, not answered — Jason's call)

The deployed artifact is ultimately **one seed's checkpoint**. The every-seed rule exists to prove
the *recipe* is reliable, not because all three seeds deploy. A **pre-registered** per-run
acceptance gate ("train k seeds; adopt iff ≥m pass a pre-declared dual-skill bar, deploy a
pre-declared selection, e.g. median-on-held") is materially different from post-hoc cherry-picking
— under 7b, 2 of 3 runs already pass such a bar. Whether the program's reliability standard is
"the recipe succeeds every time" or "the recipe yields a passing artifact with high, measured
probability" is a **policy decision**, and it changes what increment-8 has to achieve. TVW's note:
the current every-seed standard is the stronger claim and the better outward story; relaxing it
should be explicit and pre-registered if done at all. HOLD for Jason.

## 6. TVW recommendation (decision remains Jason's)

The evidence-ranked, cost-ranked menu:

1. **Deployment-neutral composite first — "B+C stack":** ensemble teacher (3–5 teachers, averaged
   soft targets; O(1/k) inter-student variance per arXiv:2601.18909) + logit standardization +
   EMA/SWA of student weights, seeds branched from a shared early checkpoint (arXiv:1912.05671).
   Optionally SAM on the student (2× train FLOPs). Every element is training-time only, frozen
   data, frozen architecture, and directly targets the measured failure. A **branch-then-soup**
   candidate (family D) falls out for free as a report-only extra arm.
2. **Family F (collapse-exact expansion)** as the second shot if the stack fails: capacity-like
   optimization benefit, zero deployment delta. Verify the contraction is byte-exact against the
   ops-guard as a pre-registered assertion.
3. **Family A (true capacity bump)** only after 1–2 fail — at that point the evidence for "fixed
   capacity is genuinely binding" would be clean, which is exactly what the hardware-cost decision
   deserves. Family E (EWC two-stage) is a viable alternative second shot if the failure signature
   after the stack looks like drift-during-joint-training rather than trajectory noise.

Design constraint for whichever is picked: the arm count must stay small enough that the verdict
keeps its every-seed teeth (or the §5 policy question is settled first).

## 7. Corpus/ETL record

26 papers (25 batch + 1 pre-test) ingested as full text via ar5iv→Jina into
`~/.corpus/odmr-pnt-nv-docs/raw/arxiv.org/` with provenance headers, manifest updated, corpus
reprocessed with Qwen3-Embedding-4B (Spark2, 2560-d). See manifest and
`meta/acquisition.log` for the file-level record. Search entry point:
`python ~/projects/skills/skills/search-corpus/...` or the `search-corpus` skill against topic
`odmr-pnt-nv-docs`.

**Agent-flagged residual gaps (not ETL'd, verify before formal citation):** arXiv:2407.04600
(variance question for repeated self-distillation), arXiv:2206.15047 / 2512.13905 (ensemble-KD
for edge students, index-verified only), ASAM (2102.11600) / GSAM (2203.08065) / Switch-EMA
(2402.09240) as optimizer variants if SAM/EMA are adopted. The literature has **no** direct
"seed-stable KD for tiny fixed-architecture embedded students" paper — the composite in §6 is
assembled evidence, and a positive result would itself be a defensible novelty point (relevant to
the Q5 novelty ledger, O7).
