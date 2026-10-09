# Increment 8 — reliability-at-fixed-capacity: the B+C stack (cloud fan-out)

*TVW dispatch-9 (`dispatch-9-increment8-bc-stack-2026-07-11.md`) executes increment-8 on branch
`increment-8-bc-stack` off odmr `d8773f3`. Goal: recover the in-cone line identity v6 lost
(v1-standing-eval held misassoc 0.311 → 0.540) **reliably across seeds** — increment-7 showed
single-teacher KD recovers it in 2/3 seeds but not every-seed (diagnosis:
reliability-at-fixed-capacity, not identity-vs-acquisition opposition). Increment-8 stacks
deployment-neutral levers that shrink run-to-run variance without touching the deployed shape:
frozen `sequence_train_v3`, frozen v6 architecture (gated core + linear assoc, 175,790 params,
V250 whitelist), cues OFF — **only the training signal and trajectory control change.** Verdict
is pre-registered (`experiments/increment8_verdict.py`) and every number is re-derived LOCALLY on
spark2; AWS only ever executes training. Keep-what-survives; NO default flip inside increment-8
(adoption is a separate TVW ruling). Baseline-to-beat: the **`baseline-env` arm** — the unchanged
increment-6 v6 recipe rerun in the same AWS environment ×5 seeds (see §0-ii).*

## §0 — provenance on the record (stated FIRST, before any training)

**(i) Quantization status (unchanged from increment-7 §0).** The v2/v6 tracker checkpoints and
every increment-8 checkpoint are **FP32 PyTorch** models. **No INT8/TFLite export of the tracker
exists** — `find . -iname '*.tflite' -o -iname '*.onnx' -o -iname '*int8*'` returns nothing under
the repo. **All metrics reported here are float.** INT8 export + on-target parity (QAT per Jacob
et al. 2018, arXiv:1712.05877) is a **separate tracked work item (TVW open item O11), NOT part of
increment-8.** The architecture is *designed* V250-INT8-compatible and passes the PyTorch-graph
ops-guard (`validation/ops_guard.py`) and the flatbuffer stage (`validation/tflite_ops.py`), but
that is a **design property, not an executed export** — no statement here may claim "INT8" or
"on-silicon" numbers the artifacts do not support.

**(ii) Training environment: AWS g6e.xlarge (NVIDIA L40S 48 GB, 32 GiB host, x86-64).**
Increment-8 training runs on `~/projects/gpu-fanout` cloud instances (L40S/x86), **not** the
GB10/ARM primary. (Instance fixed by TVW Addendum M after `g6.xlarge` proved too small — see the
execution note below; one environment per increment.) L40S (x86) and GB10 (ARM) are **not
bitwise-reproducible** (different BLAS/cuDNN kernels, accumulation order). Therefore **all verdict
comparisons use the in-environment `baseline-env` arm** — the unchanged increment-6 v6 recipe
rerun ×5 seeds on the same L40S/x86 stack — as the baseline every guard and the PRIMARY test
compares against. Hardware is a **recorded covariate**: every run preserves its
`run_manifest.json` (torch/CUDA version, GPU, commit SHAs, dataset sha256) under
`artifacts/increment8/` + NAS backup `spark2-odmr-increment8`. A report-only cross-check compares
pooled `baseline-env` against the GB10 v6 numbers; a **material shift there is a STOP** (an
environment problem, not a science result — stop-and-report #1).

**(iii) Eval sets and verdict never leave spark2.** AWS receives only synthetic simulator output
(`sequence_train_v3/dataset.h5`, sha256-verified) + git-archived tracked source of the two private
repos (no artifacts, no eval sets, no history). The immutable v1 standing eval, dwell, and
field-cone sets stay on spark2; checkpoints come back and `experiments/increment8_verdict.py`
re-derives every reported number locally. A corrupted/wrong cloud run can only produce a checkpoint
that fails the local evals — it cannot contaminate the audit chain.

## Arms (train on AWS L40S; students byte-identical to v6, 175,790 params; 5 seeds each unless noted)

Frozen for every arm: `sequence_train_v3`, gated core + linear assoc (175,790 params, same
ops/whitelist), snr10 shot-noise augmentation, epochs 800 / batch 32 / patience 100 / val_every 5,
cues OFF, input_gain from the data's nominal contrast. Foveation-free association/field loss
weights are unchanged from increment-6. **Only the training signal + trajectory control change.**
Student seeds `20260701/11/21/31/41` (n widened from 3 per Picard/Bouthillier — every-seed at n=5
is a materially stronger reliability claim).

- **`baseline-env`** — the UNCHANGED increment-6 v6 recipe, rerun in-environment ×5 seeds. The
  baseline every guard/PRIMARY compares against, AND (report-only) the first n=5 measurement of the
  incumbent recipe's own seed spread.
- **`kd1`** — increment-7 7b recipe verbatim (single teacher `teacher_e1`, α=0.5, T=2.0) ×5 seeds.
  Dual duty: the k=1 ablation point for the O(1/k) ensemble-variance prediction, and it connects
  increment-7's result to the new environment/n. **Report-only** (not an adoption candidate).
- **`bc`** — the B+C stack ×5 seeds: **ensemble-KD** (5 fresh teachers, soft targets averaged as
  temperature-scaled, logit-standardized softmax probabilities) + **logit standardization**
  (2403.01427) + **weight-EMA** of the student, all seeds branched from a **shared early trunk**.
- **`bc_sam`** — `bc` + **SAM** on the student (~2× step cost) ×5 seeds.
- **`soup`** (report-only, LOCAL, no training) — uniform weight-average of the 5 `bc` branch
  students (same trunk ⇒ same basin ⇒ souping valid per 2203.05482); evaluated as a single
  candidate. If it beats every individual student, that is **increment-9 material** — report, do
  not adopt inside increment-8.

Infrastructure (trained but not adoption candidates): **teachers** `teacher_e1..e5` (seeds
`30260701..05`) — the wider FP32 teacher of increment-7 (feat_dim 64 / assoc_dim 32 / state_dim
128 / conv_channels 16), throwaway, never deployed, never shipped outward (heed Cho & Hariharan
1910.01348 — teacher size/patience held at the increment-7 value, NOT grown); **student_trunk**
(seed `20260700`) — the shared early-branch checkpoint.

**NOT in scope:** capacity/param changes; cue lineage; dataset changes; new decoders (inherit the
dispatch-7 policy held→baseline, ou/reversal→A3); non-whitelisted ops; PCGrad (dropped
permanently, Addendum H); any deterministic/pinned-RNG "fix".

## Pre-declarations (committed in `experiments/increment8_verdict.py` BEFORE any training)

| knob | value | rationale / source |
|---|---|---|
| KD blend α / temperature T | 0.5 / 2.0 | increment-7 7b verbatim (Hinton 2015) |
| Teacher arch overrides | feat 64 / assoc 32 / state 128 / conv 16 | increment-7 teacher; **not grown** (1910.01348) |
| Ensemble averaging | mean of per-teacher **response** probs `softmax(z_i/T)` | O(1/k) variance reduction (2601.18909) — average responses, not logits |
| Logit standardization | per-sample z-score over K-anchor dim (eps 1e-7), **KD/KL term only** (teacher + student); hard-CE on raw logits, unchanged | repairs ~4× teacher/student logit-scale mismatch (2403.01427) without altering the hard-label objective |
| Weight-EMA decay | 0.999 per optimizer step; EMA weights are the deployed candidate + the val/early-stop model | churn reduction (2411.18704) |
| SAM ρ | 0.05 (`bc_sam` only; ~2× step cost) | 2010.01412 default; flat-minima trajectory control |
| Trunk branch epoch | 40 (of the frozen 800) | shared early-stability phase; branches resume epochs 41→800 on the same cosine, total epochs unchanged (LMC, 1912.05671) |
| Student param count | 175,790 (asserted every candidate) | deployment-neutrality; V250 ops-guard passes |
| Seeds | teachers 30260701–05 · trunk 20260700 · students 20260701/11/21/31/41 | n=5 every-seed reliability standard |

## Verdict — PENDING (training blocked on an infra decision; escalated UP to TVW 2026-07-11)

Pre-registered in `experiments/increment8_verdict.py` (committed before any training result
exists). PRIMARY = in-cone identity recovery vs `baseline-env`, every seed (n=5), clean+snr30;
GUARD-A (HARD) = acquisition (directed 0/72 every seed; off-cone dwell CI-neutral-or-better);
GUARD-B = lock CI-neutral. Keep-what-survives; tie → simpler arm (`bc` < `bc_sam`); none →
keep nothing, escalate UP to TVW on the options-audit ladder. Filled in after the local
eval+verdict pass.

### Execution status — 2026-07-11 (stop-and-report #6: cloud infra)

All pre-hoc science is committed (`2207f87`) and locally validated (every arm trains end-to-end
on real v3; every student is exactly 175,790 params + ops-guard clean; 190 tests green; the
verdict reader was exercised against synthetic 5-seed artifacts). **Wave-1 chunk-1 (`teacher_e1`,
`teacher_e2`) FAILED on AWS `g6.xlarge`** — the mandated instance cannot run the frozen v6 recipe:

1. **Host-RAM OOM (exit 137 / SIGKILL by the Linux OOM killer, both runs).** Measured peak host
   footprint ≈ **17 GB** loading full v3 (2048 seqs) + the augmentation pipeline; `g6.xlarge` has
   **16 GiB host RAM**. (A CUDA-VRAM OOM would be a `RuntimeError`/exit 1, not 137.) The dispatch's
   pre-flight smoke used a placeholder script, so real data loading was never exercised on L4 —
   chunk-1 caught it for ~$0.15.
2. **Watchdog overrun for the ensemble/SAM arms (no memory fix helps).** Measured on GB10:
   baseline/teacher ≈ 36 s/epoch, **`bc` ≈ 99 s/epoch** (5 teacher forwards + EMA), `bc_sam`
   ≈ 140 s/epoch. At increment-7's early-stop horizon (~400 epochs) and L4 being slower per
   epoch, `bc`/`bc_sam` project to **~15–25 h**, exceeding the 720-min (12 h) watchdog.

No instances remain (self-terminated; teardown clean). Resolution requires a compute-target /
cost decision (bigger-RAM instance + longer watchdog, a faster GPU, or the fleet GB10s) —
escalated UP to TVW as the increment-8 execution blocker. Training and the verdict are unchanged
and ready to run the moment a compute target is chosen.

**RESOLVED — TVW Addendum M (2026-07-11, gpu-fanout `e613ec3`): execute on AWS `g6e.xlarge`**
(NVIDIA L40S 48 GB / 32 GiB host / 4 vCPU → OOM cleared, still 2-concurrent under the 8-vCPU
quota; watchdog raised to 1800 min / 30 h). Fleet vetoed (sparks can't be locked down); one
environment per increment (no instance-type change mid-increment — only concurrency may scale if
the 64-vCPU raise lands). Chunk-1 is re-run as the real-recipe smoke: verify host-RAM headroom +
s/epoch pace, STOP-AND-REPORT if the worst arm projects past ~24 h (6 h watchdog margin). §0-ii
above records the L40S environment; the `baseline-env` arm carries the comparison as designed.

**Chunk-1 smoke result — 2026-07-11 (STOP-AND-REPORT #2: worst-arm time + cost, escalated to
TVW).** `teacher_e1` **succeeded (exit 0)** on g6e.xlarge — the 32 GiB host cleared the OOM and it
produced a valid 2.8 MB checkpoint (best_val 0.490, on par with the increment-7 teacher). But the
measured L40S pace fails the stop-line: **teacher = 76.7 s/epoch (best@60, stop@160, wall 12,280 s)
vs GB10's 38.9 s/epoch → L40S is ~1.97x SLOWER.** The workload is latency-bound sequential BPTT
(256 steps, batch 32, small model), so L40S's throughput advantage doesn't apply. Projections at
increment-7's ~400-epoch early-stop horizon (GB10 pace x 1.97):

| arm | GB10 s/ep | L40S s/ep | ~per-run (400 ep) |
|---|--:|--:|--:|
| baseline / teacher | ~37 | ~76 | ~8 h |
| kd1 | ~43 | ~85 | ~9 h |
| **bc** | 99 | ~195 | **~21.7 h** |
| **bc_sam** | ~135 | ~266 | **~29.6 h (over)** |

**Two blockers:** (1) **bc_sam projects ~28-34 h** (400-455 epochs) — over the ~24 h stop-line AND
the 30 h watchdog (would be watchdog-killed). (2) **Cost overrun**: L40S at ~$1.9/hr x ~2x runtime
~= 4.7x the g6.xlarge cost-per-run the dispatch estimate assumed -> full increment projects to
**~$650-700 (bc-only ~$400)** vs the $105-160 estimate. Per the dispatch stop-line, escalated UP to
TVW; wave-1 launches held after chunk-1 (teacher_e2 allowed to finish, a needed ensemble member),
nothing else launched pending the ruling. Infra itself is proven working; this is purely a
time/cost fit problem with the L40S choice.
