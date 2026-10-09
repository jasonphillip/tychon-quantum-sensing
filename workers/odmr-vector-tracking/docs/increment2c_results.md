# Increment 2c — results (v2 lever ablation + seeded baseline finals)

*Dated 2026-07-03. Standing eval: the v1 test set (4 trajectory families × 4 SNR rungs),
scored by the shared `sequence_metrics_row` path. Verdict artifacts:
`artifacts/noise_matrix/matrix_2c_final.json` and the generated table
`artifacts/increment2c/wave2_report.md` (gitignored — this doc is its tracked narrative).*

## Question

2c asked whether any **loss-shaping association lever** closes the per-track *identity* gap
that 2a exposed — the learned tracker wins the vector estimate through adversarial crossings
but loses to CV-KF + Hungarian on *which line is which*. Three levers were trialled on the v2
dataset (4× sequence count) at the frozen v1-scale recipe (gated+linear, shot-noise aug SNR10,
epochs 800 / batch 32 / patience 100 / val 5): **soft/merged-CE targets**, **Sinkhorn/OT
matching**, **scheduled sampling** (plus a gentler `ss_ramp125` ramp variant).

## Verdict: no lever survived

The deterministic survival rule (CI-disjoint regression vs the plain gated baseline at any
rung × family, on FIELD lock-loss + paired post-crossing angular error, and IDENTITY misassoc
+ IDSW/opportunity) eliminated all three:

| Lever | Verdict | Representative failure |
|---|---|---|
| soft-targets | ELIMINATED (2 cells) | SNR3/ou misassoc 5985/8258 vs 5581/8258 (CI-disjoint) |
| Sinkhorn (OT) | ELIMINATED (4 cells) | held ae_post +0.13–0.17° CI-disjoint (clean/snr30/snr10) + SNR3/ou misassoc |
| scheduled-sampling | ELIMINATED (42 cells) | clean/held lock-loss 24/37 vs 1/37; ae_post +5.48° [+4.96,+6.42] |

The gentler scheduled-sampling ramp (`ss_ramp125`, 12.5% teacher→model) did **not** rescue it
(clean/held lock-loss 19/37, misassoc 0.892 vs baseline 0.374) — same self-confirming-lock
failure as the B3 motion-prior negative. **Loss-shaping as a lever family is exhausted.** The
deployable default stays the plain gated+linear+aug tracker.

## Baseline seed-variance (3 seeds, val physical assoc median/seq)

| seed | best_epoch | best_val | in-coll (physical) | out-coll | in-coll (anchor) |
|---|---|---|---|---|---|
| 20260701 | 230 | 0.0678 | 0.550 | 0.985 | 0.958 |
| 20260711 | 310 | 0.0613 | 0.622 | 0.996 | 0.958 |
| 20260721 | 235 | 0.0652 | 0.592 | 0.991 | 0.961 |

The in-collision identity proxy carries real seed spread — **0.550 / 0.592 / 0.622 (range
0.072)** — while out-of-collision sits at ~0.99 for every seed. Consequence: single-seed lever
deltas at the ~0.02 misassoc level were inside seed noise; the CI-disjoint rule correctly
rejected them, and any future identity claim must clear this spread.

## The identity crown is rung-dependent (not a flat "KF wins")

Scoring the 3 baseline seeds against CV-KF across the full matrix sharpens the 2a picture:

- **FIELD / lock — learned wins everywhere, decisively on OU.** Learned loses vector lock on
  0/30 OU sequences clean→snr10 where CV-KF loses 19/30; the learned lock advantage holds at
  every rung × family. This is the surviving, deployable claim, now confirmed across 3 seeds.
- **IDENTITY — KF's crown is confined to its home regime.** KF wins identity only at
  clean/snr30 on held+reversal (misassoc 0.10–0.28 vs learned 0.26–0.46). By snr10 the two
  converge and learned wins identity on OU and reversal as KF degrades faster under noise. KF's
  *apparent* SNR3 identity win (misassoc 0.22 on held vs learned 0.69) is a lost-lock artifact —
  KF has lost lock on 28/37 sequences there, so its "consistent" association tracks noise, not
  identity. **Report KF SNR3 identity conditioned on lock, never unconditioned.**

## Takeaway → next increment

The residual identity gap is now localized to **clean/SNR30 on held+reversal** and is not
closable by loss tricks. Per the cross-domain survey (`docs/design/04_identity_gap_solution_survey.md`),
closing it needs either an **architecture change** (a fingerprint/relational appearance branch,
or an attention assignment head) or a **hybrid** (learned field estimate gates the association).
The honest paper claim is **field-estimate / vector-lock robustness + cold acquisition**, not
identity superiority.

A **zero-retrain identity re-decode** (survey lever A) is the immediate next probe: the field
estimate `b_est` never consumes the assignment (`learned.py:543`, `585`), and the model emits
the full `(B,T,L,K)` score tensor, so identity can be re-decoded post-hoc against the existing
v2 checkpoints without touching the field claim. Results in the dated section below.

---

## Zero-retrain identity re-decode (2026-07-03)

*Eval-side only — no training, no model edits. Six per-slot identity decoders applied to the
three baseline-seed v2 checkpoints through the same noise-matrix harness (4 families × 4 SNR
rungs, 3 seeds), scored by the shared `sequence_metrics_row`. Code: `tracking/redecode.py`
(+ `tests/unit/test_redecode.py`), `experiments/identity_redecode.py`,
`experiments/redecode_verdict.py`. Artifacts: `artifacts/noise_matrix/matrix_2c_redecode.json`,
`redecode_verdict.json`, and `artifacts/increment2c/redecode_report.md`.*

**Field claim is untouched — verified, not asserted.** The decoders rewrite only the per-slot
claimed line center `tracked_hz`; `b_est` is never modified. The matrix builder ASSERTS that
lock-loss and per-sequence angular error are byte-identical across all six decodes, and the
`decode:baseline` column reproduces `matrix_2c_final.json`'s learned-baseline misassoc exactly
(parity-checked, all seeds/rungs/families). So any identity change here is a pure re-decode, and
the vector/lock claim carries over unchanged.

**Decoders.** `greedy` (instantaneous exclusive assignment on raw scores); `smooth5`/`smooth15`
(A2 — fixed-lag smoothed exclusive decode, latency 5 / 15 frames); `physics` (A1 — assign
candidates to the 8 Zeeman-forward-map positions predicted from `b_est`, physics fallback when
no candidate is in the capture radius); `stack5` (A3 — smoothed scores biased by the physics
prior + physics fallback, latency 5). Baseline = the deployed `track_pos` readout.

**Headline: the physics-anchored + smoothed decode (A3) is a real but partial, family-specific
win.** In-collision misassoc, pooled over 3 seeds (✅ = CI-disjoint improvement *and* every seed
improves — clears the 0.072 seed spread; ✗ = CI-disjoint regression):

| rung | family | baseline | stack5 (A3) | CV-KF | verdict |
|---|---|---|---|---|---|
| clean | held | 0.311 | 0.391 | 0.099 | ✗ regress |
| clean | ou | 0.505 | **0.476** | 0.532 | ✅ (beats KF) |
| clean | reversal | 0.424 | **0.379** | 0.281 | ✅ |
| snr30 | ou | 0.505 | **0.476** | 0.544 | ✅ (beats KF) |
| snr30 | reversal | 0.424 | **0.381** | 0.302 | ✅ |
| snr10 | ou | 0.503 | **0.478** | 0.564 | ✅ (beats KF) |
| snr10 | reversal | 0.425 | **0.385** | 0.487 | ✅ (beats KF) |
| snr10 | held | 0.309 | 0.390 | 0.375 | ✗ regress |

A3 improves in-collision misassociation on **OU and reversal at every SNR rung**, CI-disjoint and
consistent across all three seeds — and on **OU it overtakes CV-KF at every rung** (0.476–0.478
vs 0.532–0.564). On reversal it closes ~40–50 % of the baseline→KF gap and beats KF at snr10.
This is the first identity gain in this lineage that costs **zero retraining**.

**But it does not fix `held`** — the family where KF's crown is strongest (misassoc 0.099 clean).
Every decode variant *regresses* held at clean/snr30/snr10. The gap is narrowed on two families,
untouched on the hardest.

**Informative negatives (they point at the next lever):**
- **Pure score decodes regress in the target regime.** `greedy` and `smooth5/15` are worse than
  baseline at clean/snr30/snr10 (held 0.50 vs 0.31) and only help at SNR3. The raw association
  scores carry *worse* identity than the recurrent position readout — the identity signal is not
  in the association head.
- **Physics-alone (A1) also regresses** (over-snaps candidates); it only wins *combined* with the
  smoothed scores (A3), where the physics prior breaks ties the scores leave ambiguous.
- **Temporal smoothing (A2) helps only at SNR3**, where per-frame scores are noisy — latency
  5–15 frames. Not the target regime.
- KF's SNR3 misassoc (0.223 held) is a **lost-lock artifact** (KF lost lock on 28/37 held at
  SNR3) and is not a fair identity comparison there; the learned decodes' SNR3 gains
  (`smooth15` held 0.697→0.550) are over a tracker that still holds lock.

**Implication.** The win mechanism is *folding the physics prediction from the good, non-circular
field estimate into the association* — exactly survey lever #1 (a fingerprint/physics term
multiplied into the position score). The zero-retrain form already banks OU + reversal for free
and should be adopted as the default identity decode on those families. It also sharpens the
next retrain: **lever B (a trained physics-fingerprint relational branch), targeted specifically
at `held`**, where a learned appearance descriptor (Zeeman slope sign, contrast, ¹⁴N hyperfine)
has the most to add and a zero-retrain prior cannot reach.
