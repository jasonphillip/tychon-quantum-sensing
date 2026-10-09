# DISPATCH → odmr-vector-tracking session: 2c — v2 retrain with association levers

**From:** TVW orchestration session, 2026-07-02. **Approved by Jason.**
**Prereq:** `sequence_train_v2` delivered by the nv-sensor-sim lane
(`dispatch-nvsim-sequence-train-v2-2026-07-02.md`). Do not start training before it lands;
lever implementation (§2) can be built and unit-tested against v1 in the meantime.

> **BOUNDARY (standing TVW rule):** Do NOT touch the slide deck, email drafts, or any
> outreach surface — TVW-only; emails send only on Jason's explicit go. Do NOT push to
> GitHub without Jason's OK (nas push fine). Never quote the retracted Increment-1 numbers
> (16/16, 0.811, DR≈5 mT) except explicitly labeled as retracted.

## Context (why these levers)

B3's mechanism was exposure bias + self-referential gating: the motion gate keyed on the
model's own association softmax, so a wrong lock excluded the correct candidate and became
self-sustaining (1a3e787). CV-KF is immune because its gate anchors to calibrated detections.
Design rule going forward: **kinematics may enter only as a soft feature/bias, never a hard
gate; any hard gate must anchor to measurement-space evidence, not the model's own output.**
Lever details + citations: TVW `tvw/audits/research-ml-optimization-levers-2026-07-02.md`
(Tier 1 / association recipe).

## 1. Baseline first (cheap, mandatory)

Retrain the current deployable architecture (non-MP gated+aug) on v2 unchanged — this
isolates the data-scale effect before any lever confounds it. Full standing-eval matrix
(v1 test + shot-noise ladder). This is the new reference row.

## 2. Levers, applied cumulatively in this order (one matrix run each)

1. **Soft/merged CE targets for attribution-ambiguous in-collision frames** (your own
   queued lever). Inside the collision window, when candidates are within the ambiguity
   radius, replace one-hot targets with mass split across the ambiguous lines (or a merged
   target class). Rationale: hard targets teach confident wrong answers exactly where
   confidence is unearned — the confident wrong lock is what B3's gate then amplified.
2. **Sinkhorn one-to-one assignment loss** replacing independent per-slot CE: log-domain
   Sinkhorn (few iterations, e.g. 10–20) over the line×candidate score matrix with a
   dustbin row/col for missing/coasting lines; train against the (soft) permutation.
   Mutual exclusivity gets learned in the loss instead of bolted on as a hard gate at
   inference. Keep Hungarian at inference (unchanged).
3. **Scheduled sampling / rollout training**: ramp the probability of feeding the model's
   own previous-step association/track state instead of teacher-forced ground truth
   (e.g. 0 → 0.5 linearly over training). Directly targets the val/test dissonance B3
   exposed. Keep the supervised val metric logged separately so the ramp's effect on the
   *objective* vs the *tracker* stays visible.

If a lever regresses the matrix, drop it and continue the sequence without it — cumulative
means "keep what survives," not "keep everything."

## 3. Rules (unchanged, load-bearing)

- **Standing eval is immutable**: v1 test set, same seeds, full shot-noise ladder
  (SNR_faintest ∈ {3, 10, 30}), per-family Wilson CIs. v2 val is for training decisions only.
- **Field-regression rule**: lock-loss and post-crossing angular error rows must not regress
  vs the current floor (non-MP gated+aug reference) at any rung. A variant that wins identity
  but loses field is rejected, same as B3.
- Identity metrics reported against the CV-KF crown (sw/opp 0.016/0.053/0.217) — that's the
  bar for the 2c gap, not PID.
- Multi-seed: 3 seeds on the final surviving config (report spread, not just best).
- GPU verified before any run (`torch.cuda.is_available()` logged in the script's own output);
  long runs nohup + pidfile + progress lines.

## Report back (to Jason, for TVW)

Per-lever matrix deltas (identity + field, per family, with CIs), the surviving config, and
an explicit statement whether the 2c identity gap moved (misassoc + sw/opp vs both CV-KF and
the v1-scale reference). Numbers first, one screen. Commits on
`increment-2-learned-tracker` or a new clearly-named branch; nas push yes, GitHub held.
