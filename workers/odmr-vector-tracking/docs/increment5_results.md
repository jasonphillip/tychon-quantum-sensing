# Increment 5 — results (dwell-sweep boundary + physics-cue exploitation, zero-retrain)

*Dated 2026-07-07. Eval: the seed-paired dwell lineage from nv-sim (`sequence_dwell_v1` cues-OFF /
`sequence_dwell_v1_cues` strain+CR-ON; 288 sequences each, 24 per (D, exit-topology) bucket,
D ∈ {8..192} frames, cross/bounce balanced 50/50), scored by the shared `sequence_metrics_row`
path, fixed-seed shot noise sized on the v1 ladder. 3 wave-2 seeds (20260701/11/21) on the
deployed `gated+linear+aug` checkpoints; zero retrain; `b_est` untouched by every decode
(asserted). No TVW dispatch existed for this consumer side — the verdict rules were declared in
`experiments/increment5_verdict.py` before results were read. Artifacts:
`artifacts/noise_matrix/matrix_5_dwell.json`, `artifacts/increment5/{increment5_verdict.md,
coverage_split.json}` (reproduce with `experiments/increment5_dwell_eval.py` →
`increment5_verdict.py`; coverage split via `increment5_coverage_split.py`).*

## Question

Increment 4 measured the held identity gap as **information-limited at the decode stage** and
named two paths: quantify the recoverability boundary on a dwell-parameterized eval, and inject
new measurement-space information (physics cues). nv-sim delivered both datasets (2026-07-07).
This increment asks: (1) where is the identity-recoverability boundary vs merge-dwell length and
exit topology; (2) do the physics cues — per-axis static strain offsets (~20 kHz, split-invisible)
and the 3.8 ppm NV–NV cross-relaxation PL dip (~1.8%, a measurement-side merge marker) — let a
zero-retrain cue-aware decode (strain-aware forward map; CR-marker-gated hold) recover identity
that cues-OFF data cannot?

## Verdict

**Cues: FAILED for the current checkpoints (guard-tripped + no exploitation survivor).
Boundary: the primary result — and it must be read conditioned on a newly discovered
training-coverage gap.**

### Scoring note (read first)

On these engineered quartet merges (target pair + its physics-forced NV mirror pair), the two
merged lines are *coincident* during the dwell, so frame-wise in-collision misassoc has a **0.5
attribution floor** for any tracker that keeps both slots on the merged blob — it measures "are
you on the blob", not identity. The discriminative identity statistic on this eval is
**IDSW/opportunity** (exit identity: did each lock come out on the line it went in on).

### Discovery — a deterministic training-coverage gap (field claim)

The learned field lock fails on **exactly half** the cues-OFF sequences — identically across all
3 seeds, every dwell length, both topologies. The split is by merge template: pairs (0,6)/(2,4)
keep |B| ≈ 4.9–5.0 mT within 6–15° of the deployment bias (inside the v1/v2 training envelope,
max ≈ 18° off-bias) and the tracker **never** loses the field (0/216); pairs (0,2)/(4,6) require
**41°/53° off-bias at 3.9/3.3 mT** to force their cross-axis degeneracy — outside anything in
training — and the tracker **always** loses the field (216/216). This is a field-**coverage**
gap in the training data, not a tracker defect: cold acquisition simply never engages outside
the trained field cone. (Reproduce: `experiments/increment5_coverage_split.py`.)

### Boundary, in-coverage (templates 0/1; cues OFF, clean; the fair comparison)

| metric | learned baseline | learned A3 (stack5) | CV-KF |
|---|--:|--:|--:|
| field lock-loss | **0/216** | **0/216** | 107/144 |
| exit identity (IDSW/opp), cross | 0.154 | 0.111 | 0.233 |
| exit identity (IDSW/opp), bounce | 0.100 | **0.045** | 0.407 |
| in-coll misassoc (floor 0.5) | 0.500 | 0.500 | 0.56–0.60 |

Two claim-shaped findings:

- **KF's identity crown is prior-matching, now measured.** The exit-topology balance was designed
  to de-confound the constant-velocity prior (all-cross evals reward it trivially). On **bounce**
  exits KF switches identity **0.407** per opportunity (~coin-flip on the pair) vs **0.045** for
  the learned A3 decode — a ~9× gap in the learned tracker's favor — while on cross KF's 0.233
  still trails A3's 0.111. Pooled over the balanced eval the learned tracker wins exit identity
  outright, *and* holds the field where KF loses it on ~74% of in-coverage dwell sequences.
- **Graceful dwell degradation — effectively no cliff.** In-coverage learned exit identity is
  flat in dwell length: A3 per-D (topologies pooled, 3 seeds) = 0.073 / 0.059 / 0.090 / 0.059 /
  0.089 / 0.099 for D = 8→192 — a 24× longer merge costs ~0.03 in exit-switch rate. NLS sits at
  the 0.500 misassoc floor with 0.247 exit switches (its static per-frame fit coin-flips at
  merge exit, as in 2b).

Noise: the in-coverage picture is flat clean→snr10 and degrades gracefully at snr3; KF snr3
identity is conditioned-on-lock (KF loses lock on 231/288 dwell sequences at snr3).

### Cue robustness (guard) — the CR dip breaks the current checkpoints

Same tracker, seed-paired cues-ON vs cues-OFF: the learned tracker's field lock-loss goes
**432/864 → 783/864** (50% → 91%, CI-disjoint at every rung) — the ~1.8% CR dip is 5–16× deeper
than every ODMR line and is catastrophically off-distribution for the conv front-end. **Guard
tripped for the learned tracker at every rung; the cues as rendered are not deployable with the
current checkpoints.** (CV-KF, whose detector just sees another dip, is robust — its field lock
actually *improves* on cues, 228→137/288 at clean: the dip pins the merge location. The cue is
physically informative; the learned front-end is what breaks.)

### Cue exploitation — nothing survives

On the cues dataset, the best non-cue decode is pure physics (A1, 0.930 pooled misassoc); the
cue-aware decodes sit at 0.935–0.937 (strain) and 0.936–0.937 (CR gate) — no CI-disjoint
improvement, no seed-consistency, and net-vs-the-no-cue-world regress at every rung.
Mechanistic reads: the ~20 kHz strain offsets are invisible at the model's ~MHz candidate
resolution (`stack5_strain` ≡ `stack5` to 3 decimals — an exact null); the CR gate works as
designed (control: identical to A1 when no marker fires; changes the decode when it does) but on
a field estimate already broken by the same dip it gates on, it cannot help. Exploiting either
cue requires the cue inside the training distribution — a retrain, out of scope here.

## Decision

Per keep-what-survives: **no cue decode ships; no defaults change.** The deployable default
remains wave-2 `gated+linear+aug` with A3 on OU/reversal, baseline on held.

What this increment *does* establish, for the record and for the next dispatch:

1. **The balanced-topology identity claim** (new, positive): on in-coverage dwell merges the
   learned tracker beats CV-KF on *both* axes of the standing comparison — field lock (0/216 vs
   107/144) *and* exit identity (0.045–0.111 vs 0.233–0.407) — because the balanced eval removes
   the CV-prior confound that manufactured KF's v1 crown. This is the strongest identity
   evidence the learned tracker has ever had; it is dwell-eval-scoped and does not overturn the
   v1-held numbers.
2. **The top training lever is now angular field coverage, not identity mechanisms** (new,
   actionable): a deterministic, all-seed field-acquisition failure at 41–53° off-bias is a
   measured training-data gap. A v3 training request widening the off-bias cone (and |B| floor)
   is the highest-value next dataset — it attacks the field claim's boundary directly and is a
   precondition for any off-cone identity work.
3. **Cue path requires retrain**: strain needs sub-linewidth positional resolution (or a
   raw-spectrum integrator); the CR marker needs the dip in the training distribution. Both are
   retrain-lineage items (fresh go-ahead required), and the CR dip's KF benefit suggests the
   feature itself is real and useful once in-distribution.

## Disposition (2026-07-07)

Strain-aware forward map (`axis_offsets_hz` through `predicted_line_positions` / A1 / A3) and the
CR marker + gated decode (`cr_dwell_marker`, `cr_gated_decode`) are **retained** in
`tracking/redecode.py` (6 new unit tests; 163 unit / 169 total green) — correct, field-safe, and
ready for a post-retrain re-test; they change no default. Datasets verified against the nv-sim
handoff (md5, seed-pairing, bucket structure, cue presence) before any scoring. Branch
`increment-5-dwell-cues`; NAS only; no GitHub push; the spark1 archive untouched; no retrain, no
dataset regeneration. Per the standing IP flag, cue mechanisms stay out of outward-facing
material (TVW lane owns outward material).
