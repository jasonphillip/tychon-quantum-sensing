# Increment 7 — in-cone identity recovery at coverage (candidate measurement)

*TVW dispatch-8 (`dispatch-8-increment7-identity-recovery-2026-07-08.md`), executed on branch
`increment-7-identity-recovery` off odmr main `2f52d69`. Goal: buy back the in-cone line identity
that v6 lost (v1-standing-eval held misassoc 0.311 → 0.540) **without** losing v6's acquisition
win and **without** changing the deployed model's shape (frozen v3 data, frozen v6 architecture —
same ops, 175,790 params, V250 whitelist; cues OFF; only the training signal changes).
Keep-what-survives; NO default flip inside increment-7 (this measures candidates; adoption is a
separate TVW ruling). Baseline-to-beat: **v6 @ 2f52d69 with the dispatch-7 re-decode policy**
(held→baseline, ou/reversal→A3), inherited — no new decoders.*

## §0 — Quantization status on the record (stated FIRST, before any training)

The v2 and v6 tracker checkpoints are **FP32 PyTorch** models. **No INT8/TFLite export of the
tracker exists yet** — verified: `find . -iname '*.tflite' -o -iname '*.onnx' -o -iname '*int8*'`
returns nothing under the repo. **All metrics reported to date (v0–v6, and everything in this
increment) are float.** INT8 export + on-target parity — QAT per Jacob et al. 2018
(arXiv:1712.05877) is the recommended route — is a **separate tracked work item (TVW open item
O11), NOT part of increment-7.** The architecture is *designed* V250-INT8-compatible and passes
the PyTorch-graph ops-guard (`validation/ops_guard.py`) and the flatbuffer stage
(`validation/tflite_ops.py`), but that is a **design property, not an executed export** — no
downstream statement in this increment may claim "INT8" or "on-silicon" numbers the artifacts do
not yet support.

## Arms (parallel candidates; keep-what-survives)

All arms: frozen `sequence_train_v3`, frozen v6 architecture (gated core + linear assoc, 175,790
params, same ops/whitelist), cues OFF, seeds 20260701/11/21, wave-2 backbone, snr10 shot-noise
augmentation — **only the training signal changes** vs increment-6. Verdict rules committed
PRE-HOC in `experiments/increment7_verdict.py` before any training result exists.

- **7a — geometry-weighted ("foveated") identity loss.** The association (identity) loss term is
  multiplied by a per-sequence factor keyed on `max_offbias_angle_deg`: high inside the historic
  in-cone region (≤~30°), relaxed at wide angles. Field-lock/projection loss untouched. Exact
  angle-bin schedule pre-declared in the verdict script.
- **7b — knowledge distillation.** An unconstrained FP32 teacher (wider, off-target, throwaway,
  never deployed) is trained on v3; its soft association targets are distilled into a student
  **byte-identical in shape to v6**. Teacher spec + KD (α, temperature) pre-declared.
- **7c — PCGrad gradient surgery (OPTIONAL, only if bandwidth).** Project conflicting field-head
  vs identity-head gradients. Training-time only, deployment-neutral.

## Runs (2026-07-09 → 07-11, single GB10, frozen recipe)

| run | arm | params | early stop | best val |
|---|---|--:|--:|--:|
| `fov_gated_linear_snr10` (×3 seeds) | 7a | 175,790 | 300/180/270 | 0.6853/0.6829/0.6238 |
| `teacher_v3` (throwaway, never deployed) | 7b teacher | 699,982 | 210 | 0.5786 |
| `kd_gated_linear_snr10` (×3 seeds) | 7b | 175,790 | 370/455/415 | 0.5544/0.5170/0.5703 |

7c (PCGrad) was **deferred by Jason mid-run** (optional arm; scaffolding committed, not trained).
Deployment-neutrality asserted on all 6 candidates: params == 175,790, state-dict key/shape
identical to v6, extractor passes the V250 ops-guard. Teacher premise confirmed: the 4× student
val (0.579 vs v6's 0.658) means real dark knowledge existed to distill.

## Verdict (per the pre-hoc rules): KEEP NOTHING — but the evidence is sharp

`experiments/increment7_verdict.py` (rules committed a7b3061, before any training):
**no arm survives PRIMARY; no arm trips a guard.** Decision = `keep-nothing-escalate`.

### 7a foveated — no effect on the target

Held clean misassoc 0.548 vs v6 0.540 (neutral, −3% recovery); ou +5%, reversal +18%, all
CI-neutral. Re-weighting *where* the identity gradient lands, at fixed capacity and hard labels,
does not buy back in-cone identity. GUARD-A/B clean (directed 0/72 every seed; off-cone 6–8/216
CI-neutral vs v6's 1–2; lock neutral).

### 7b distillation — material pooled recovery, seed-unstable on held

Identity at the dispatch-7 policy decode, pooled 3 seeds (clean; snr30/snr10 near-identical):

| family | kd | v6 | v2 ref | recovery | CI + every-seed |
|---|--:|--:|--:|--:|---|
| held misassoc | **0.402** | 0.540 | 0.311 | 60% (material ≤0.425 ✓) | CI-improve, **every-seed FAILS** |
| ou misassoc | **0.477** | 0.569 | 0.476 | ~100% | CI-improve + every-seed ✓ |
| reversal misassoc | **0.434** | 0.536 | 0.379 | 65% | CI-improve + every-seed ✓ |

The held per-seed spread is the whole story: **0.262 / 0.340 / 0.604** (v6 counterparts
0.508/0.530/0.581). Two seeds recover *into v2 territory*; seed 20260721 lands **worse than v6**.
Under the pre-hoc every-seed rule on the headline cell, PRIMARY does not clear — the same
seed-instability signature that killed increment-3's lever B, and exactly what the rule exists to
catch. (At snr3 the recovery vanishes — held 0.722 vs 0.717, neutral — consistent with every
prior increment's snr3 behavior.) GUARD-A/B clean: directed 0/72 every seed, off-cone 4–6/216
CI-neutral, lock neutral at all 12 cells.

### What this refines about the capacity-tension diagnosis

The dispatch framed a stop here as "evidence that in-cone identity and wide-cone acquisition are
in genuine capacity tension at 175,790 params." The 7b evidence **sharpens** that: no arm traded
acquisition for identity (GUARD-A never tripped — the two objectives are not in hard opposition
at eval time), and two of three distilled seeds held BOTH. The binding failure is
**reliability-at-fixed-capacity**: with a stronger training signal the student can fit both, but
not reproducibly across seeds. Escalated UP to TVW as the increment-8 trigger with that nuance —
the options space includes a capacity bump (hardware-cost path) *and* a distillation-recipe
refinement (e.g. teacher ensemble / stronger KD schedule — still deployment-neutral, but a new
recipe = fresh dispatch). Per the dispatch, no capacity work was started here.

## Disposition (2026-07-11)

Branch `increment-7-identity-recovery`; verdict artifacts in `artifacts/increment7/`
(gitignored, preserved on disk + NAS backup `ws2-odmr-increment7`); no default change
(deployed default remains v6 @ `docs/deployable_default.md` with the dispatch-7 policy); no new
decoders, no dataset work, no cue data; 7c deferred mid-increment and **declined by Jason 2026-07-11**
(not trained — the verdict evidence weakened its premise: no field/identity guard conflict was
ever observed); fieldcone boundary NOT re-charted (no survivor, per dispatch). 175 tests green (training-signal hooks are gated
opt-ins; default path byte-identical). Outward material untouched.
