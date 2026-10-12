# Research synthesis: ML optimization levers for odmr-vector-tracking

**Date:** 2026-07-02 · **Method:** three parallel web+corpus research agents (learned
MOT/association; deployable sequence models + training knobs; NV/ODMR domain 2024–26),
synthesized against the repo's actual configs (`train_increment2a.yaml`, `model.yaml`,
`docs/increment2a_results.md` at 60c4491). All items carry citations in the agent reports;
key ones repeated here. Evidence: Wang et al., doi:10.1063/5.0310526, supplementary material (held privately, not in this repository).
**Consumption:** Tier 0 is a polarfire-lane dispatch (safe during the soak — Beelink-only);
Tiers 1–2 feed the NEXT tracking dispatch (post-B3 report); Tier 3 feeds Increment 3;
Tier 5 feeds the next nv-sim lineage; Tier 4 items are doc/corpus chores TVW can drive.

## Headline verdicts

1. **Novelty claim survives, resolved wording.** Wang/Wrachtrup APL 128,114001 (2026)
   (doi:10.1063/5.0310526) is READ (abstract + full supplement + all 31 refs): classical
   lock+DDS-hop, 5th-order polynomial lock-in, fixed 3×4 pseudoinverse, spiral demo with
   ≲1 G excursions, **no ML, no crossing/identity handling** — line identity is assumed.
   It is the newest classical comparator, not a scoop. Across three lanes: **no ML
   through-crossing resonance tracker and no sequential NN over ODMR spectra streams
   exists as of 2026-07-02.** Wording constraints: scope to NV/ODMR (an NMR video-SR
   crossing tracker exists, bioRxiv 2026.03.19.712888); do NOT claim static-overlap
   identification novelty (Haim MLST 2025 already claims 8-from-6-visible single-frame;
   Stone 2405.18648; Dubey 2504.18478); acknowledge identity-from-degeneracy art
   (Espinós/Budker arXiv:2512.13835 — Bayesian, static, MW-free) and Rabi labeling
   (SBQuantum lineage).
2. **The NPU gate ban may be stale.** The SDK's own op list
   (`polarfire-control-corpus/raw/github.com/Microchip-Vectorblox/VectorBlox-SDK/docs/OPS.md`,
   Apr-2026 vintage) lists LOGISTIC/TANH/SOFTMAX/EXP/MUL/SUB as supported INT8 ops; the
   sigmoid/tanh/softmax ban traces to older launch-collateral. If gates compile on V250,
   the noise-winning gated cell (3/37 vs relu 8/37 at SNR 3) is itself deployable and the
   relu-vs-gated dilemma dissolves. **Decisive test = Tier 0.**
3. **The association literature convergently indicts our current design** (fully-learned
   per-slot scores, no motion prior): the 2023–26 winning pattern is CV-Kalman base +
   learned residual/gain (HybridTrack RA-L 2025: learning prediction helps, learning
   update alone fails; KalmanNet; PKF soft association; MANTa <50k params) + a
   mutual-exclusivity-aware training objective (Sinkhorn — BMVC 2025 neural-Kalman, or
   Hungarian/GOSPA-in-the-loss — MT3v2). Per-slot CE never penalizes double-claiming:
   the likely root of B4's "posterior on the wrong line."
4. **Closest published analogue to our exact geometry:** dolphin whistle-contour tracking
   through crossings (Roch JASA 2011 → DeepWhistle/silbido 2020–23): per-frame CNN
   candidates + graph linking with slope continuity, crossings resolved using evidence
   from BOTH sides. Short-lookahead/bidirectional scoring is legal for us and cheap.

## Tier 0 — decisive verification (polarfire lane; Beelink-only, soak-safe)

**Compile test on bee:** export (a) a one-step unrolled gated cell (sigmoid/tanh, state as
graph I/O), (b) an 8×60 softmax head, to INT8 TFLite; `vnnx_compile -c V250`; run the
VNNX simulator vs float over a fixed input set; report per-op acceptance + max abs error.
~30 min. Outcome A (compiles, small error): ops_guard rewritten from measured truth;
gated cell becomes NPU-eligible; attention heads reconsidered. Outcome B (rejects): the
ban gets a *measured* provenance line and we proceed gate-free with confidence. Either
way the guard stops resting on doc archaeology. (Note: ban may originally come from real
odmr-edge-ml compile failures — the test settles it.)

## Tier 1 — do-now cheap (training hygiene; next tracking dispatch)

| Lever | Why / evidence | Config today |
|---|---|---|
| Randomize + curriculum the photon budget (per-sequence uniform over the ladder, anneal toward harsh) | ACCAN EUSIPCO 2017: fixed-SNR training is the documented weak point; targets the 8/37-vs-3/37 gap | fixed SNR-10 aug |
| 3–5 seeds + report spread; EMA weights (decay 0.999) as the eval/export artifact | Deep ensembles NeurIPS 2017; EMA/SWA free generalization; per-family counts on 37/23/30 seqs need variance bars | single seed 20260701, raw endpoint |
| Measure-then-set grad clip (log norms, clip≈p90), 100–500-step warmup, ~10-frame hidden-state burn-in excluded from loss | blind clip 1.0 can silently clip every step; TBPTT bias analysis UAI 2019 | clip 1.0 flat, no warmup |
| Augmentation menu: frequency jitter (labels shifted), contrast scaling ±30%, line dropout (cutout of one dip), **spectra-mixup = synthetic collision generator** | Iwana&Uchida PLOS ONE 2021; arXiv:2201.11739 (+45% small-data); mix-based wins on physio signals | shot noise only |
| ReLU-cell stabilization: IndRNN-style per-neuron recurrent-gain clamp + zoneout p≈0.1 on the update branch | Li-GRU's unbounded-ReLU-state warning = the likely fragility mechanism; IndRNN CVPR 2018 clamp is whitelist-legal | small-gain init only |
| Scale data 512→~5k sequences (generator is ours; ~30 min gen) | at this scale augmentation+data dominate architecture swaps; matches the session's own train→val gap diagnosis | 512 train seqs |

## Tier 2 — identity gap / B3+ (architecture; sequenced)

1. **CV prior as the BASE, learn residual + gain on top** (HybridTrack ablation; KalmanNet)
   — sharpen the already-dispatched B3: don't learn free-form motion; learn corrections.
2. **Sinkhorn layer over the 8×60 score matrix + one-to-one-aware loss** (BMVC 2025;
   Gumbel-Sinkhorn; 1 iteration can suffice — host-trivial) replacing per-slot CE; or
   Hungarian-matching-in-the-loss (MT3v2 GOSPA framing).
3. **Short-lookahead / bidirectional crossing resolution** (whistle-tracker "both sides"
   rule; Kalman smoothing at eval) — a 5–10-frame delay is honest for a magnetometer if
   stated; keep a causal mode for the deployed path.
4. **Existence/coast head** with temporal-smoothness prior (Milan AAAI 2017) +
   **β-NLL (β=0.5) heteroscedastic covariance head** (Seitzer ICLR 2022) replacing the
   constant buffer — ~64 params, supplies real R for fusion/safety story.
5. **Pairwise-in-context scoring** (TWiX coordinates-only SOTA; Trackastra greedy-linked
   pairwise transformer, Cell Tracking Challenge 2024 winner) — score line-candidate
   pairs jointly on the host, not slots independently.
6. **minGRU ablation** (gates from x_t only → NPU-side gate computation, host keeps
   MUL/ADD): convert the gated cell's gate inputs to x_t-only, rerun the noise gauntlet.
   If it retains 3/37, a deployable gate exists even without Tier 0's answer.
7. **TCN variant** (dilated causal conv, ~63-frame receptive field): 100% whitelist-legal
   today, strong INT8 track record — the whole temporal stack becomes NPU-resident.
8. **KD: gated(+ensemble) teacher → relu/TCN student** — hidden-state MSE + soft assoc
   targets (Irie ICASSP 2018 is the exact analogue); weight 0.3–1.0, oversample
   heavy-noise sequences.
9. Appearance/ReID embeddings as PRIMARY cue: **skip** (DanceTrack lesson: uniform
   appearance breaks ReID; amplitude only as motion-bootstrapped auxiliary, BMVC KL(P‖U)).

## Tier 3 — Increment-3 deployment

- **QAT, not PTQ, for anything recurrent** (recurrent state accumulates quant error;
  arXiv:2210.07692; integer-LSTM per-gate scales): fake-quant fine-tune final ~20% epochs
  from float checkpoint with KD loss on.
- **Calibration data must span the photon ladder**; fold input gain via
  `tflite_quantize --mean/--scale` (VectorBloxPG §2.2.4–2.2.5); assert input scale uses
  ≥90% of INT8 range (the 0.4%-contrast hazard).
- LRU/S5-style diagonal linear recurrence = variant C if gates stay banned (recurrence =
  per-channel MUL+ADD; quantization-sensitive activations — Quamba); after TCN/minGRU.
- Skip: RWKV (DIV-by-activation NPU-illegal, wrong scale), TTA on the 1 kHz path.

## Tier 4 — metrics, claims, and doc/corpus chores

- **Report GOSPA/T-GOSPA (radar/DAF-credible; localization-vs-switching decomposition
  maps onto our field-vs-identity split) alongside HOTA/AssA/IDF1 (vision-credible)** +
  existing IDSW/opportunity. TrackEval + t-gospa-metric-python exist.
- references.md fixes: Wang APL 2026 flag → "non-ML, no crossing handling — VERIFIED
  2026-07-02 (abstract+supplement+refs; main-text figures unverified)"; Lönard now
  PRResearch 8, 013054 (2026) doi:10.1103/28t7-7gcn; Ziabari "PRR 7,043044" unverified —
  flag; add Dubey (doi:10.1007/s00723-025-01824-6), Haim published DOI
  10.1088/2632-2153/ade51c, Espinós 2512.13835, Meneses 2502.14683 (title-collision:
  object tracking, not line tracking — cite to distinguish), NMR video-SR tracker.
- landscape_ip.md: US10921394B2 assignee = SOCPRA/Roy-Guay (SBQuantum ecosystem — note:
  context, not just risk); **passive per-axis contrast as a learned feature reads on
  identity cue. Q.ANT "±500 µT" claim contradicted by Q.ANT's own 2024 brochure (2.7 µT
  demonstrator) — mark unverified.
- DR-comparison citation table for future claims: Wang RSI 2023 (4.3 mT, 0.723 T/s),
  Kumar RSI 2024, Micromachines 2024 (6.4 mT; Γ/2-per-cycle rule), Liu IEEE Sensors 2024,
  Fu Opt.Express 2025, Wang APL 2026 — "classical closed-loop ≤ few-mT single-line or
  hop-heuristic; crossing traversal unsolved."
- Corpus ingestion list (odmr-pnt-nv-docs): the CR set (1505.02253, 2301.09666,
  2207.13899, Lazda PRB 103,134104), Haim 2409.12820 + 2502.06070, Lönard 2504.20750,
  Espinós 2512.13835, Meneses 2502.14683, Stone 2405.18648, Yamauchi 2605.23455,
  Mongelos 2602.12090, US10921394B2, PRA 110,052417, Wang abstract+supplement (doi:10.1063/5.0310526; held
  privately, not in this repository).

## Tier 5 — simulator/physics features (next nv-sim lineage)

1. **Cross-relaxation dips as crossing markers** (density-conditional; Dhungel: 1.79%/0.78 mT
   at 3.8 ppm, visible ≳0.9 ppm; Espinós has the analytic resonance model to copy).
   Physics-anchored "a crossing is happening HERE" feature; also required realism for
   ≳1 ppm samples. Caveat: Lazda 2021 is NV↔P1 at 51.2 mT — different mechanism, don't
   conflate.
2. **¹⁴N hyperfine triplet** (A∥≈2.16 MHz vs Γ≈1.5 MHz: partially resolved; axis-AGNOSTIC
   so NOT an axis label, but the crossing composite's deviation from a clean 1:1:1
   triplet is an overlap/deblending feature — **no prior art exploits this passively;
   genuinely unclaimed idea**).
3. **Per-axis static strain/E-field offsets (M_z ladder)** — differential, persistent →
   a static identity fingerprint (real-device values exist to copy: Meneses fit
   (19.6,−4.2,−3.5,−11.9) kHz); plus an 8-line common-mode gate (dD/dT −74.2 kHz/K)
   separating T-drift from B-driven crossings.

## Future mode (sparse/adaptive acquisition) — citation frame ready

NIST `optbayesexpt` (PRApplied 14,054036: >10× speedup; embedded <50 µs Arshad
PRApplied 21,024026) = the benchmark for a learned probe-tone selector; Haim compressed
sensing 2502.06070 (~15% of points) = the sparse-sampling prior art; qsensoropt/Fiderer
PRX Quantum = learned-policy frame. Nobody has done multi-line vector ODMR probe steering
with identity constraints — open, and the natural Increment 4.

## Skip list (with reasons)

RWKV (NPU-illegal core op, wrong scale) · TTA on deployed path (K× latency, thin
evidence) · appearance-ReID primary cue (DanceTrack) · stochastic depth (wrong depth
regime) · label smoothing if distilling (calibration/distillation conflict — verify
Müller 2019 before relying) · global ILP/offline linking (host-paced online budget).
