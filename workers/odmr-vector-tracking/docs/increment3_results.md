# Increment 3 — results (lever B: appearance-fingerprint association branch)

*Dated 2026-07-03. Standing eval: the v1 test set (families × 4 SNR rungs), scored by the shared
`sequence_metrics_row` path. 3 paired seeds (20260701/11/21), recipe = the wave-2 reference
(gated+linear, aug SNR10, 800/32/100/5) on v2. Artifacts:
`artifacts/noise_matrix/matrix_3_redecode.json`, `artifacts/increment3/leverB_verdict.md`
(reproduce with `experiments/leverB_verdict.py`).*

## Question

2c's zero-retrain re-decode closed OU/reversal identity but could not reach the **`held`
clean/snr30** gap (A3 regressed held; pure-score decodes were information-starved). Lever B adds
a **rectified-difference appearance branch** to `LinearScoreAssociation` — folding a per-line
fingerprint (per-axis Zeeman depth/contrast) into the association score — to enrich the scores
where positions coincide, targeting `held`. Pre-flight was green (held regression CI-real; conv
RF 17.4 linewidths sees the fingerprint; contrast ladder 0.0012/0.0019/0.0027/0.0036 separates
the 4 axes).

## Verdict: FAILED (per the survival rule)

The primary target regressed, the fingerprint did not enrich the scores, and two guard classes
tripped — including the surviving field claim at SNR3.

**Primary — held in-collision misassoc (lever-B vs wave-2, pooled 3 seeds):**

| rung/decode | wave-2 | lever-B | verdict | KF | per-seed lever-B |
|---|---|---|---|---|---|
| clean/baseline | 0.311 | 0.379 | **B-WORSE** | 0.099 | [0.177, 0.554, 0.406] |
| clean/greedy (scores) | 0.510 | 0.537 | **B-WORSE** | 0.099 | [0.527, 0.553, 0.531] |
| clean/stack5 (A3) | 0.391 | 0.449 | **B-WORSE** | 0.099 | [0.389, 0.521, 0.438] |
| snr30/baseline | 0.309 | 0.375 | **B-WORSE** | 0.260 | [0.177, 0.541, 0.407] |

Held misassoc **regressed** under every decode, CI-disjoint, and stayed far from CV-KF (0.099).
The pure-score `greedy` decode is still ~0.54 — **the fingerprint did not enrich the scores**.
Critically, the per-seed spread is enormous — **0.177 / 0.554 / 0.406** (range 0.377, ~5× the
0.072 wave-2 seed spread): one seed found a large *improvement* (0.177 vs 0.311) while two
regressed badly. The branch is real but **wildly seed-unstable**, so no consistent claim survives.

**The one gain — held IDSW/opportunity (through-crossing switches):** the appearance branch
roughly **halves** identity switches under the deployed decode (clean 0.171 → 0.102, snr30
0.168 → 0.099, both CI-disjoint). But it is a secondary metric, it does **not** survive under
the A3 decode (~overlap), and it comes bundled with the worse misassoc above — the branch makes
the tracker *commit harder* to an identity (fewer swaps) but sit on the wrong axis more during
the overlap.

**Guards — tripped:**

| guard | wave-2 | lever-B | verdict |
|---|---|---|---|
| clean/ou misassoc (A3) | 0.476 | 0.494 | B-WORSE |
| clean/reversal misassoc (A3) | 0.379 | 0.414 | B-WORSE |
| snr30/ou, snr30/reversal (A3) | 0.476 / 0.381 | 0.496 / 0.413 | B-WORSE |
| **snr3 field lock-loss** | **56/270** | **105/270** | **B-WORSE** |

Lever B nicks the OU/reversal identity that A3 had won in 2c, and — most seriously — **nearly
doubles field lock-loss at SNR3** (21% → 39%, CI-disjoint), damaging the one surviving
deployable claim. This matches the survey's explicit caveat: *a weak fingerprint is worse than
none* — at SNR3 the faintest line is ~1 LSB, the fingerprint is uninformative, and the branch
degrades the field rather than falling back to position-only.

**Field claim in the target regime is intact:** at clean/snr30/snr10 lever B holds 0 lock-losses
(vs baseline's 1) and slightly *better* angular error (ae_post 0.32–0.34 vs 0.37–0.39). So the
branch does not hurt the field where the fingerprint is informative — only at SNR3.

## Decision

Per the dispatch rule, a failed outcome (primary regressed + guard regressions) means **stop and
report the per-family evidence; do not improvise new levers.** The deployable default remains the
wave-2 `gated+linear+aug` tracker; the lever-B model must **not** ship (SNR3 field regression).

The evidence is diagnostic, not a dead end: the mechanism *can* help (seed 20260701 reached held
misassoc 0.177, and switch-stability improved across all seeds), but as implemented it is
seed-unstable and lacks an SNR-graceful fallback. Two things would have to change before an
appearance signal is worth retrying: (1) **stability** (the 5× seed variance says the branch
over-fits an unstable identity commitment), and (2) an **SNR-graceful gate** so the fingerprint
switches off when a line vanishes into noise. The per-slot appearance-memory lever (survey lever
C) builds *on top of* this branch and additionally introduces output feedback (exposure-bias
risk) — it should not be attempted until the branch itself is stabilized, and needs a fresh,
explicit go-ahead.
