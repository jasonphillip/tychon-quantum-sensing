# Increment 4 — results (coalescence-aware identity overlay decoders, zero-retrain)

*Dated 2026-07-06. Standing eval: the v1 test set (3 families × 4 SNR rungs), scored by the shared
`sequence_metrics_row` path, fixed-seed shot noise. 3 wave-2 baseline seeds (20260701/11/21) on the
deployed `gated+linear+aug` checkpoints. Zero retrain, no dataset regeneration; every decoder
rewrites only the per-slot claimed identity (`tracked_hz`), `b_est` untouched. Artifacts:
`artifacts/noise_matrix/matrix_4_overlay.json`, `artifacts/increment4/{increment4_verdict.md,
dwell_analysis.md}` (reproduce with `experiments/increment4_overlay.py` →
`experiments/increment4_verdict.py`; Step 0 via `experiments/increment4_dwell.py`).*

## Question

Increments 2c/3 left one gap open: the **`held` clean/snr30 in-collision misassoc** (learned 0.31
vs CV-KF 0.10). Lever A (physics/smoothing re-decode) closed OU/reversal but not held; lever B
(appearance fingerprint) failed and regressed. The held gap is the classical **track-coalescence**
phenomenon — a structural property of marginal-style trackers — whose verified-literature fix is to
treat identity as a **decode-side overlay** that never feeds back into the state estimate (Set-JPDA,
Svensson 2011; unresolved-measurement MHT, Koch & van Keuk 1997; BP-reduces-coalescence,
Kropfreiter 2023). Our architecture already satisfies the precondition (`b_est` never consumes the
association), so a menu of four such decoders is **zero-retrain and field-safe by construction**:

- **D-BP** — marginal-association decode (Williams–Lau loopy sum-product over the gated score
  matrix), temporally accumulated; latencies 5/15.
- **D-OV** — Set-JPDA identity overlay: an 8×8 doubly-stochastic (Sinkhorn) slot-vs-line belief
  re-labelling the label-free positions; read-outs instantaneous/5/15/end-of-sequence.
- **D-UM** — unresolved-measurement merged hypotheses: lines within a resolution radius hold
  physics identity through the dwell; r ∈ {0.5, 1, 2} cells.
- **D-JV** — joint fixed-lag Viterbi over the gated assignment beam; latencies 5/15, plus the best
  composition (D-UM merged states inside D-JV).

Pre-flight parity gate passed: the spark2 re-decode reproduces the archived `matrix_2c_final`
learned baseline exactly (756 count comparisons, all seeds/rungs/families; field metrics
byte-identical) — the result below is attributable to the decoders, not environment drift.

## Verdict: NO DECODER SURVIVES (stop-and-report)

No decoder achieves a CI-disjoint, every-seed held improvement at both clean and snr30, and every
decoder trips the regression guard. Per the dispatch this is a stop-and-report outcome; no decoders
were improvised beyond the menu.

**Primary — held in-collision misassoc, pooled 3 seeds (baseline 0.311; CV-KF 0.099; NLS 0.052):**

| decoder | lat (f) | clean | snr30 | vs baseline | per-seed (clean) |
|---|--:|--:|--:|---|---|
| D-BP bp5 / bp15 | 5 / 15 | 0.499 / 0.515 | 0.502 / 0.516 | **regress** | [0.51, 0.50, 0.49] |
| D-OV inst / 5 / 15 | 0 / 5 / 15 | 0.403 / 0.410 / 0.453 | 0.402 / 0.411 / 0.454 | **regress** | — |
| D-OV eos | ≥seq | 0.311 | 0.309 | neutral (=baseline) | [0.374, 0.263, 0.295] |
| D-UM r0.5 / r1 | 0 | 0.383 / 0.345 | 0.382 / 0.345 | **regress** | — |
| D-UM r2 | 0 | **0.298** | **0.297** | neutral | [0.304, 0.325, 0.266] |
| D-JV jv5 / jv15 / jv15+um | 5 / 15 / 15 | 0.510 / 0.509 / 0.502 | 0.512 / 0.511 / 0.491 | **regress** | [0.49, 0.51, 0.51] |

Three mechanistically distinct failures, one wall:

- **D-BP and D-JV land at ~0.50–0.51 — the 2c pure-score `greedy` regime.** Marginal and joint
  decoding can only reweight the *association scores*; during a held merge the two lines sit within
  a linewidth for ~130 frames and the scores carry no information to separate them, so score-based
  decoders do strictly *worse* than the deployed position read-out.
- **D-OV** spreads its identity belief correctly during the merge but cannot re-concentrate it: the
  physics-predicted centers of the two held lines are themselves sub-linewidth apart during the
  dwell, so the belief re-sharpens on the wrong permutation (fixed-lag 0.40–0.45). The
  end-of-sequence read-out degenerates to the single global permutation = the baseline labelling
  (0.311), i.e. it recovers baseline but adds nothing.
- **D-UM r2** is the only decoder to nose *below* baseline (0.298) by holding physics identity
  through the merge — but the improvement is **not CI-disjoint and not seed-consistent** (seed
  20260711 = 0.325 > baseline 0.311), i.e. inside the seed spread, no claim.

**Guards — every decoder trips (CI-disjoint regression vs the default policy: A3 on OU/reversal,
baseline on held).** Even the two decoders that are neutral on held sacrifice OU/reversal, where the
A3 physics decode already won in 2c:

| clean | A3 (default) | D-UM r2 | D-OV eos | CV-KF |
|---|--:|--:|--:|--:|
| ou misassoc | 0.476 | 0.497 ✗ | 0.505 ✗ | 0.532 |
| reversal misassoc | 0.379 | 0.408 ✗ | 0.424 ✗ | 0.281 |

**Field claim intact (invariant by construction).** `b_est` is never an output: held snr3 field
lock-loss is **28 for every decode** (baseline, D-UM, D-JV, D-OV alike) and per-sequence angular
error is byte-identical — the matrix builder asserts this each rung/seed, and no assertion fired.
No decoder can inflate or damage the vector/lock claim.

**CV-KF SNR3 identity is conditioned-on-lock only:** CV-KF held snr3 misassoc reads 0.223, but KF
loses field lock on 28/37 held sequences at snr3 — the number covers only the frames where lock
survives and is not a clean identity win.

**IDSW/opportunity (report-only) shows no secondary gain either.** Held through-crossing switch
rate (clean, pooled): baseline 0.171, D-OV eos 0.171, D-UM r2 0.177, D-BP 0.239, D-JV+um 0.306,
versus CV-KF 0.016 — the overlay decoders are neutral-to-worse on switch stability too (unlike
lever B, which at least halved IDSW). **Latency (report-only):** all menu variants are ≤15 frames
except D-OV end-of-sequence, which is non-causal (a whole-sequence belief) and would not be
deployable on a real-time magnetometer irrespective of accuracy.

## Step 0 — merge-dwell diagnostic (why the wall is where it is)

De-pooling held in-collision misassoc by the per-slot `line_collision` run length (the survival
denominator) shows the gap is a **long-coalescence** phenomenon:

| family | in-coll entries | run p50 | run p90 | % entries ≥64 f |
|---|--:|--:|--:|--:|
| held | 5060 | 132 | 178 | 56% |
| ou | 8258 | 16 | 45 | 0% |
| reversal | 2998 | 11 | 23 | 0% |

held misassoc vs dwell (baseline / A3 / CV-KF): at short dwell (<16 f) 0.411 / 0.383 / 0.187; at
long dwell (≥64 f) 0.229 / 0.417 / **0.022**. The learned–vs–CV-KF gap is ~0.2 at *every* dwell (a
pervasive coalescence gap, not concentrated at long dwell), but the one sharply dwell-dependent
effect is that **CV-KF collapses to 0.022 misassoc in the longest, most stable merges** — a still,
near-coincident two-line hold initialised at t=0 is exactly its Hungarian-gate sweet spot — while
every per-frame overlay read-out stays ~0.23. A3 actively *worsens* held at long dwell (0.417),
confirming the 2c choice to keep baseline on held. This is the labeled-RFS mixed-labelling caveat
(García-Fernández 1604.00082) borne out: identity through long merges is information-limited, so a
guaranteed solve was not expected — and none was found.

## Decision

Per the dispatch's keep-what-survives rule, a no-survivor outcome means **stop and report the
per-family evidence; do not improvise decoders beyond the menu.** The deployable default is
unchanged: the wave-2 `gated+linear+aug` tracker with the A3 re-decode on OU/reversal and baseline
on held. Nothing in this increment ships.

The evidence is diagnostic, not a dead end. The overlay decoders are correct and field-safe; they
fail because **held identity through a long coalescence is information-limited at the decode stage,
not a matter of decode cleverness** — score-based decoders inherit starved scores, and physics-based
decoders inherit sub-linewidth-separated predictions. Closing the held gap therefore requires *new
information* during the merge, not a better read-out of the existing signal: an SNR-graceful
appearance/fingerprint channel (survey lever C, gated per Maggiolino 2302.11813, and only after the
lever-B stability fix) or an upstream dwell-sweep / cross-relaxation dataset that makes the held
lines separable — both out of scope here and each needing a fresh go-ahead. Step 0's dwell curves
scope (but do **not** request) the first such dataset.

## Disposition (2026-07-06)

The four overlay decoders and their harness are **retained in the code** (`tracking/redecode.py`;
`experiments/increment4_overlay.py`, `increment4_verdict.py`, `increment4_dwell.py`,
`increment4_parity_gate.py`) with 13 new unit tests (157 total green). They change **no default** —
`identity_redecode`'s A3-on-OU/reversal policy remains the deployed re-decode, and the shipped
tracker is exactly the wave-2 reference. The decoders are kept so the mechanism can be revisited
(alongside a new information channel) without re-deriving it; the matrix and verdict are fully
reproducible from the committed checkpoints and the immutable v1 test split. No new seeds, no
retrain, no dataset regeneration, and no GitHub push were performed. Per the standing IP flag, the
coalescence/overlay mechanisms stay out of outward-facing material (the TVW lane owns outward
material).
