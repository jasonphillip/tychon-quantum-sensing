# Dispatch 8 (DRAFT) — odmr-vector-tracking: increment-7 in-cone identity recovery at coverage

> **GATE STATUS (updated 2026-07-09, Addendum G):**
> 1. **Jason's explicit go — STILL REQUIRED (the only remaining gate).** This is the program's
>    **first recipe change** (increment-6 froze the v2 recipe; increment-7 deliberately changes
>    the training signal). Per the README "decisions that are yours," increment-7 needs an
>    explicit go. Jason pasting this dispatch's prompt into the worker session constitutes the go.
> 2. ~~dispatch-7 completed~~ **CLEARED 2026-07-09** — v6 is the deployable default at odmr main
>    `2f52d69`, per-family re-decode policy re-selected (no family switched: held→baseline,
>    ou/reversal→A3, dwell→A3). TVW-verified (Addendum G). The baseline-to-beat is now concrete:
>    **v6 @ 2f52d69 with that policy.** GUARD-B and PRIMARY comparisons inherit these decodes.
>
> Naming note: **dispatch-8 executes increment-7.** Dispatch and increment numbers diverged at
> dispatch-7 (a zero-retrain policy flip, no increment). Verdict script is `increment7_verdict.py`.

**Target session:** `~/projects/odmr-vector-tracking/` on **spark2**.
**Drafted:** 2026-07-08, from the increment-6 SUCCESS verdict (`audit-dwell-program-2026-07-07.md`
Addendum D / DLOG-060) and the external red-team review intake (Addendum E).
**Mode (when issued):** run end-to-end without user assistance; keep-what-survives; stop-and-report.

## Why

Increment-6 cleared the acquisition gap (216/216 → 1–2/216; directed 0/72) but the same fixed
capacity (175,790 params) spread over a ~3.4× wider cone regressed **in-cone line identity**:
v1-standing-eval held misassoc 0.311 → 0.540, exit IDSW/opp 0.171 → 0.398 (CI-disjoint, clean→snr10,
every seed). Addendum D booked the next binding constraint as **capacity/recipe, not data breadth**.
Increment-7 tries to **buy the in-cone identity back without losing the v6 acquisition win, and
without changing the deployed model's shape** (no NPU-budget or vnnx-recompile impact).

The diagnosis (capacity allocation under joint field+identity training, not catastrophic forgetting —
v6 was trained from scratch, not fine-tuned) points at **training-signal** levers, which are
deployment-neutral. Two are committed arms; a third is optional. All keep the architecture and the
data frozen so the single isolated variable vs increment-6 is the training signal.

## §0 — quantization status on the record (do FIRST, one paragraph, no work)

Before any training, state explicitly in `docs/increment7_results.md` (and confirm it is true):
the v2 and v6 checkpoints are **FP32 PyTorch** models; **no INT8/TFLite export of the tracker
exists yet**; all reported metrics to date are **float**. INT8 export + on-target parity (QAT per
Jacob 2018 is the recommended route) is a **separate tracked work item** (see TVW open item O11),
NOT part of increment-7. This one paragraph exists so no downstream doc repeats an "INT8 / on-silicon"
claim the artifacts don't yet support. (The architecture is designed V250-INT8-compatible and passes
the ops-guard — that is a design property, not an executed export.)

## The arms (parallel candidates; keep-what-survives)

All three: **frozen v3 data**, **frozen v6 architecture** (same ops, same 175,790 params, same V250
op-whitelist), **cues-OFF**, seeds 20260701/11/21, wave-2 backbone. Only the training signal changes.

- **7a — geometry-weighted ("foveated") identity loss.** Multiply the identity/association loss term
  by a factor that is **high inside the historic in-cone region (≤~30° off-bias)** and **relaxed at
  wide angles** (where v6's acquisition win lives and where identity was never the priority). The
  field-lock loss is untouched. Rationale: spend identity-relevant gradient where it was lost, stop
  spending it where it was never the goal. Pre-declare the weighting schedule (angle bins, factors)
  in the verdict script before results.
- **7b — knowledge distillation.** Train an **unconstrained FP32 teacher** (wider/deeper, off-target,
  never deployed) on v3, then distill its **soft targets** into a **student architecturally identical
  to v6** (same ops/params/whitelist). Rationale: soft "dark-knowledge" targets are a stronger, more
  regularized training signal that lets a small student learn boundaries it can't find from hard labels
  — the standard route to pack more skill into fixed capacity. The teacher is a throwaway offline
  artifact; **only the student is a candidate** and it must be byte-identical in shape to v6.
- **7c — PCGrad gradient surgery (OPTIONAL, same rules, run only if bandwidth).** Project conflicting
  gradients between the field head and the identity/association head so wide-angle-lock updates and
  in-cone-identity updates stop overwriting each other. Training-time only, deployment-neutral. This is
  the method that directly targets the diagnosed mechanism (field↔identity gradient conflict).

**NOT in scope (explicitly):** capacity bump / any param-count change (→ increment-8, separate — it
forces an NPU-budget re-check and a `.vnnx` recompile via the Beelink handoff, a cross-repo change);
cue lineage / CR-dip training (separate later dispatch, never combined); any dataset change; any new
decoder (inherit the dispatch-7 re-decode policy); any non-whitelisted op (attention, dynamic gating,
exotic activations — VectorBlox silently offloads unknown ops to the soft CPU and blows the latency
budget).

## Verdict structure (pre-hoc in `experiments/increment7_verdict.py`; roles INVERTED vs increment-6)

- **PRIMARY — in-cone identity recovery.** On the immutable v1 standing eval, held/reversal/ou
  in-collision misassoc and exit IDSW/opp must improve **CI-disjoint over v6, every seed**, toward the
  v2 reference. Survival gate = CI-disjoint-better-than-v6 with no guard trip. Call it a *material* win
  (vs marginal) only if it recovers **≥ half** the v6 regression (e.g. held misassoc ≤ ~0.425 vs the
  0.311→0.540 slide). Report the recovered fraction per metric.
- **GUARD-A — acquisition (HARD; the win we cannot lose).** Fieldcone directed geometries stay **0/72**
  and off-cone dwell stays at v6's cleared level (1–2/216), **CI-neutral-or-better vs v6, every seed,
  clean+snr30**. A candidate that regresses acquisition is dropped regardless of its identity gain.
- **GUARD-B — in-cone field lock.** v1-standing-eval lock CI-neutral vs v6 (per-family × rung).
- **Report-only:** classical parity (must stay exact); snr3 leans; re-chart the fieldcone boundary if
  any arm survives (confirm the ~30–40° generic edge / 3.0 mT floor / hard cliff are unchanged).
- **Deployment-neutrality assertion (every surviving candidate):** passes the existing ops-guard
  (`validation/tflite_ops.py` / V250 whitelist) with **param count == 175,790 and no new ops**.

**Keep-what-survives:** if exactly one arm clears PRIMARY without tripping GUARD-A/B, keep it. If more
than one, keep the strongest material identity recovery with no guard trip (tie → simpler arm: 7a < 7c
< 7b by training complexity). If none clears PRIMARY, keep nothing and escalate (below).

## Stop-and-report

1. **An arm trips GUARD-A** (loses any acquisition ground vs v6) → drop that arm, keep going with the
   others.
2. **All arms trip GUARD-A, OR no arm clears PRIMARY** → stop. This is the evidence that in-cone
   identity and wide-cone acquisition are in genuine **capacity tension** at 175,790 params → escalate
   UP to TVW as the trigger for the **increment-8 capacity-bump** decision (which carries a hardware
   cost the training-signal arms don't). Do not start a capacity bump inside increment-7.
3. **Any candidate fails the ops-guard or changes the param count** → stop that candidate (it is an
   increment-8 change, not increment-7).
4. Any surprise that would need a new decoder, a data change, or a cue.

## Constraints

- Frozen v3 data; frozen v6 architecture; cues-OFF; verdict rules pre-hoc; keep-what-survives.
- No default flip inside increment-7 — this measures a *candidate*. Any adopt-as-default is a separate
  TVW ruling after the verdict (same as increment-6 → dispatch-7).
- Branch `increment-7-identity-recovery`; NAS + private GitHub; NAS push on power-on; report final HEAD.
- Outward material untouched (TVW owns it); banned numbers stay banned (16/16, 0.811, DR ~5 mT); IP hold
  stands (cue/overlay/coalescence mechanisms out of outward material).
- Strategic next-steps (increment-8 go, cue sequencing, hardware-validation) route **UP** to TVW.

## References (methodology grounding; ETL'd into `odmr-pnt-nv-docs` 2026-07-08, local embedder)

- Distillation (7b): Hinton, Vinyals, Dean 2015, "Distilling the Knowledge in a Neural Network"
  (arXiv:1503.02531).
- PCGrad (7c): Yu et al. 2020, "Gradient Surgery for Multi-Task Learning" (arXiv:2001.06782).
- QAT (for the separate §0/O11 export item, NOT increment-7): Jacob et al. 2018, "Quantization and
  Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference" (arXiv:1712.05877).
