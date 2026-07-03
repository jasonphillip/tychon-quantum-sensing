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
v2 checkpoints without touching the field claim. Results in the dated section below when run.
