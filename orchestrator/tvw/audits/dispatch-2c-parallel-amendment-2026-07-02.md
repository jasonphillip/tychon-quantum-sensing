# AMENDMENT → dispatch-2c-v2-retrain: parallel two-Spark execution plan

**From:** TVW, 2026-07-02 evening. **Supersedes the run-scope question** — do not run the
7-run sequence serially. Answer to your menu: none of the three options; execute this plan.
**Approved by Jason (asked for the speed-up; second Spark explicitly authorized).**

> **BOUNDARY (unchanged):** no deck/email/outreach surfaces; GitHub push only on Jason's
> OK (nas push fine, see NAS window below). Never quote retracted Increment-1 numbers.

## 0. Why the redesign

The cumulative lever sequence (A → +soft → +Sinkhorn → +SS) was designed for serial
compute. With two idle-enough Sparks it wastes wall-clock AND carries an invalidation risk
(if a mid-chain lever regresses, downstream configs are mis-specified). Switch to
**independent ablation + survivor combo**:

- **Wave 1 (4 runs, all parallel):** A = baseline (gated+linear+aug, v2, recipe frozen) ·
  B = A + soft/merged CE targets · C = A + Sinkhorn assignment loss · D = A + scheduled
  sampling. Each vs the standing eval (v1 test, full ladder, per-family CIs).
- **Wave 2 (3 runs, all parallel):** survivor combo × 3 seeds. **Survival rule
  (deterministic, no check-in needed):** a lever survives iff field rows (lock-loss +
  post-crossing error) do not regress beyond CI at any rung/family AND identity
  (misassoc / sw/opp) improves or is neutral. Combo = A + all survivors; if none survive,
  wave 2 = A × 3 seeds (the data-scale headline is still the deliverable).
- Interactions between levers land in the combo run — acceptable at this budget; note any
  combo-vs-ablation surprise in the report rather than adding runs.

Run wave 1 → wave 2 autonomously (rule-driven, no overnight idle); full per-lever matrix +
verdict table in the morning report.

## 1. Hardware placement

- **ws1:** 2 concurrent runs. **ws2:** 2 concurrent runs (verified 2026-07-02
  ~16:45 ET: GPU 0% util, only the Qwen3 embedding service resident — it MUST stay up;
  do not touch port 8000).
- **Contention test before committing (15 min):** launch runs A+B on ws1, measure
  s/epoch for ~10 epochs. If per-run s/epoch > 1.7× the solo 59 s, fall back to 1 run per
  Spark (wave 1 = 2×2 sub-waves; still ≈2× faster than serial).
- **ws2 setup:** clone from the nas mirror (`/mnt/nas/projects/git/odmr-vector-tracking.git`)
  or push ws1→ws2 directly; **copy the 2.9 GB dataset to ws2 LOCAL disk**
  (rsync from ws1's canonical path over the 10GbE LAN) and point `data/sequence_train_v2`
  at the LOCAL copy. Env: verify `python -c "import torch; print(torch.cuda.is_available(),
  torch.cuda.get_device_name(0))"` prints True on BOTH Sparks and log device placement in
  each run's own stdout (global rule; silent CPU fallback = bug).
- **NAS window (hard constraint):** the NAS powers off ~21:30 ET nightly. NOTHING in the
  overnight runs may read/write NAS paths — dataset local, logs local, no nas pushes from
  inside the runs. Any nas mirror pushes happen tomorrow morning or before 21:25 ET.

## 2. Make the epoch cheaper first (30–45 min, before wave 1)

59 s/epoch at batch 32 ≈ 64 steps/epoch ≈ 0.9 s/step for a ~1.7 MFLOP/frame model — that
is data-pipeline-bound, not GPU-bound. In order:

1. **Profile one epoch** (where does the 59 s go: h5 reads / noise aug / host↔device / step).
2. **Numerics-identical fixes, apply freely:** load the full 2.9 GB h5 into RAM once
   (pinned tensors), prefetch/persistent workers, avoid per-batch h5 slicing.
3. **Distribution-equivalent fix, apply only if profiling shows aug dominates:** train-time
   shot-noise generated on-GPU (fresh-per-epoch noise needs no seed compatibility).
   Guard: overlay 20-epoch train-loss curves (CPU-noise vs GPU-noise, same seed init) —
   visually indistinguishable ⇒ proceed. **The fixed-seed EVAL noise path stays untouched
   (CPU, byte-identical) — comparability with every published matrix depends on it.**
4. **Do NOT change:** batch size (32), precision, optimizer, LR — they confound the
   v1-vs-v2 data-scale comparison that run A exists to isolate.
5. Selection-run budget may trim: patience 150→100, max epochs 800 (document in the runs
   table). Wave-2 final runs keep the original dispatch budget.

## 3. Run hygiene

nohup + pidfile per run; heartbeat line (epoch / best-val / s/epoch / ETA) to a local log
every val cycle; `nvidia-smi` snapshot at launch logged per run. Standing eval immutable;
field-regression rule unchanged; commits on the existing branch, clean messages, no AI
references; GitHub held at Jason's gate.

## 4. Report back (morning)

One table: run × {best val, epochs, wall h, s/epoch} + the per-lever matrix deltas
(field + identity, per family, CIs) + survivor verdicts + wave-2 3-seed spread + an
explicit statement whether the 2c identity gap moved vs CV-KF (0.016/0.053/0.217) and vs
the v1-scale reference. Include the profiling result (what the 59 s actually was).

**Expected wall-clock: ~9–14 h total (setup+profile ≤1 h, wave 1 ≈4–6.5 h, wave 2
≈4–6.5 h) vs 25–45 h serial — and if the pipeline fix lands, plausibly 5–8 h.**
