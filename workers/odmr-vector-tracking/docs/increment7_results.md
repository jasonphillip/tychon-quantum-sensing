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

*(Results, verdict, and keep-what-survives disposition are appended after the runs complete.)*
