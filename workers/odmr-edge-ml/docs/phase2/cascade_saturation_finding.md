# Phase II Open Issue — Hierarchical INT8 Cascade Saturation

**Fix-list row:** P3-11B (Hierarchical INT8 — Path B)
**Status:** Architecture implemented, deployed artifacts produced, empirical
result inconsistent with Phase I framing. Documented for FTR; proposed
Phase IIa work below.
**Date:** 2026-05-02
**Branch / commit:** `feature/op-set-check-and-fcnnv2-docstring` @ `889bb21`
(orchestrator), `386c4ef` (validation script)
**Evidence files (gitignored, on ws1):**
- `exports/cascade_v1/cascade_manifest.json`
- `exports/cascade_v1/cascade_eval_report.json`
- `exports/cascade_v1/deployed_cascade_validation.json`
- `exports/cascade_v1/training.log`

---

## Summary

The Path B hierarchical INT8 cascade trains and exports cleanly, the
`tychon_shared_data.cascade.CascadeManifest` contract is satisfied, and
`verify_bit_exact` returns `n_mismatch=0` on a 32-spectrum fixture.
However, two independent measurements show the cascade is **not behaving
as the additive-authority-widening mechanism Phase I assumed**:

1. **FINE training labels saturate at the ±2.25 µT clamp 93.9% of the
   time.** COARSE and FINE both effectively learn a constant ≈ ±clamp
   prediction conditioned on lock_bin; the two stages do not decouple.
2. **70.08% of cascade outputs on the AIC val split saturate at the
   composition output's int8 representable boundary
   (±composition.output_quant range = [-1.20, +3.22] µT).** The
   unsaturated float-twin sum spans [-3.42, +6.82] µT — the cascade
   *wants* to predict over a 10.2 µT range but the int8 envelope
   represents only 4.4 µT.

Net: deployed cascade val MAE = **21.68 µT vs PID baseline 23.75 µT
= +8.71% reduction.** For comparison, the 2-epoch dry-run gave +10.33%
reduction; the 100-epoch run is 1.6 percentage points *worse*. This is
consistent with the saturation finding — at convergence both stages
collapse to clamp-magnitude constants, so adding them gives ~2× clamp in
the wrong direction half the time.

This compares against the existing v2 monolithic baseline (≈ 5% val MAE
reduction at the same clamp on the same dataset). The cascade does not
materially improve on the monolithic model.

## Root cause

The Phase I framing implicitly assumed the ±2.25 µT clamp was a
*deployment-side* constraint that two cascaded models could escape via
composition. The empirical run shows the constraint is actually **baked
into the training labels at clip time, before the loss is computed**
(`scalar_residual_v2.py:97`, mirrored in
`experiments/cascade_v1_train.py:170-180`). With clipped labels, neither
stage can learn signal at |residual| > 2.25 µT because the gradient
beyond that magnitude is identically zero. The cascade composition is
therefore widening the *output* range but the *learned signal* in each
stage is bounded at ±clamp magnitude.

A secondary problem: the orchestrator's choice
`composition.output_quant = min(coarse_scale, fine_scale)` was a
conservative wiring decision (preserve resolution of the finer stage)
that becomes the binding authority constraint once both stages train to
non-trivial output range. Even if the label-clipping issue were fixed,
this would still cap the deployed cascade at the smaller stage's range.

## Proposed Phase IIa work

Two fixes are required, in order:

### IIa-1. Decouple training-label clipping from the deployment sector clamp

Train both stages on **unclipped (or wide-clipped, e.g. ±10 µT) residual
labels**, and rely on a post-prediction sector clamp at deployment time
to enforce the Lur'e/Circle Criterion bound. This restores gradient
signal in the regime where the cascade is supposed to add value.

Impact: training-side change in `experiments/cascade_v1_train.py` and
`src/odmr_edge_ml/cascade/fine_labels.py`; the deployment-side clamp
already exists in the production host pipeline (`scalar_residual_v2.py`
post-prediction clip). Effectively decouples the two semantics that
`CLAMP_UT = 2.25` currently conflates.

### IIa-2. Replace `min(stage_scales)` with a calibrated cascade scale

Track the running min/max of `coarse(x) + fine(x)` during a calibration
pass (e.g. last training epoch) and set `composition.output_quant.scale`
to span the observed range with a centered zero_point. This eliminates
the int8 saturation cliff at the composed output.

Impact: ~30 lines in `src/odmr_edge_ml/cascade/manifest_emit.py` and
`experiments/cascade_v1_train.py`. Should land *after* IIa-1 — fixing
this first would just absorb the bimodal-saturated label distribution
and produce the same MAE.

### Sequencing

IIa work is deferred — the original plan (P3-12 bias-aware samplers,
P3-RPO-5 ReLU sector verification) is unblocked and proceeds first.
The deployed cascade artifacts ship as-is with this open-issue note
attached. P3-11B's stop-gates as written
(`cascade_manifest.json` validates after rounding resolution,
`verify_bit_exact` ok, `compose_quantized_then_dequant` MAE improves
over monolithic) are partially met: the manifest and bit-exact gates
pass; the MAE-improvement gate is *not* met until IIa-1 + IIa-2 land.

## Reproducibility

```bash
# Train
python experiments/cascade_v1_train.py \
  --dataset production_50k_v2_aic --output exports/cascade_v1/ \
  --epochs 100 --seed 0

# Validate (writes deployed_cascade_validation.json)
python scripts/validate_deployed_cascade.py \
  --cascade exports/cascade_v1/ --dataset production_50k_v2_aic
```

Wall time on GB10 (ws1, bf16 + torch.compile): 8 m 28 s end-to-end.
