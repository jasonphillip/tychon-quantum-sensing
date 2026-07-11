# Dispatch 9 (DRAFT) — odmr-vector-tracking: increment-8 B+C reliability stack, cloud fan-out

> **GATE STATUS (drafted 2026-07-11):**
> 1. **Jason's explicit go — REQUIRED.** Jason directed the B+C-stack setup on 2026-07-11
>    (direction pick from the options audit); per house convention, pasting this dispatch's
>    prompt into the worker session constitutes the go to EXECUTE.
> 2. **Infrastructure gates (all must be green before any `--launch`):**
>    (a) ~~IAM worker role~~ **DONE 2026-07-11** (Jason ran setup_iam.sh; role scoped to the
>    fanout bucket); (b) G-vCPU quota: raise to 64 requested (case 178377947900659, OPEN;
>    prior request for 192 closed 2026-06-05 ungranted — expect delay). **AMENDED per Jason
>    2026-07-11: do NOT block on the raise — launch chunked at current quota (8 vCPUs = 2
>    concurrent g6.xlarge), widening waves as quota lands.** Spot quota is 0 (checked) — no
>    spot shortcut. (c) ~~smoke test~~ **PASSED 2026-07-11** end-to-end (exit 0, L4 GPU,
>    dataset sha-verified + readable, both packages import, provenance manifest, results
>    shipped, self-terminated).
> 3. **Governance default:** verdict uses the EVERY-SEED standard at n=5 seeds (options audit
>    §5). If Jason prefers a pre-registered k-of-n acceptance gate instead, he must say so
>    BEFORE issuance — it changes the verdict script.
>
> Naming: **dispatch-9 executes increment-8.** Increment-8 is the reliability-at-fixed-capacity
> increment (B+C stack), NOT the capacity bump (that idea moves to increment-9+ if ever needed).

**Target session:** `~/projects/odmr-vector-tracking/` on **spark2** (training executes on AWS
via `~/projects/gpu-fanout`; evals + verdict run locally — cloud trains, spark2 judges).
**Grounding:** TVW options audit `increment8-options-audit-2026-07-11.md`; all method papers
ETL'd in `~/.corpus/odmr-pnt-nv-docs` (search-corpus topic `odmr-pnt-nv-docs`).
**Mode (when issued):** end-to-end; keep-what-survives; stop-and-report.

## Why

Increment-7 (Addendum H): single-teacher KD recovered in-cone identity in 2/3 seeds (one fully)
with zero acquisition loss, but failed every-seed — diagnosis **reliability-at-fixed-capacity**.
The literature (options audit §3) says: inter-student variance shrinks O(1/k) with k averaged
teacher responses (arXiv:2601.18909); trajectory-stability levers (EMA/SWA, SAM, shared-early-
branch) reduce run-to-run churn independently (2411.18704, 2010.01412, 1912.05671); logit
standardization repairs the 4× teacher-scale mismatch (2403.01427). Increment-8 stacks these
deployment-neutral levers: **frozen v3 data, frozen v6 architecture (175,790 params, V250
whitelist), cues OFF — only the training signal and trajectory control change.**

## §0 — provenance on the record (FIRST, before any training)

State in `docs/increment8_results.md`: (i) FP32/no-INT8 status unchanged (same paragraph as
increment-7 §0); (ii) **training executes on AWS g6.xlarge (L4/x86)** — not bitwise-comparable
to GB10/ARM, therefore **all verdict comparisons use the in-environment baseline arm** (below),
and every run's `run_manifest.json` (torch/CUDA/GPU, commit SHAs, dataset sha256) is preserved
under `artifacts/increment8/` + NAS; (iii) eval sets and verdict never leave spark2.

## Arms (train on AWS; 5 seeds each: 20260701/11/21/31/41 — n widened from 3 per
Picard/Bouthillier; every-seed at n=5 is a materially stronger reliability claim)

- **baseline-env** — the UNCHANGED increment-6 v6 recipe, rerun in-environment ×5 seeds. This
  is the baseline every guard/PRIMARY compares against, AND (report-only) the first n=5
  measurement of the incumbent recipe's own seed spread. Cross-check pooled baseline-env vs
  the GB10 v6 numbers: material shift → STOP (environment problem, not a science result).
- **kd1** — increment-7 7b recipe verbatim (single teacher, α=0.5, T=2.0) ×5 seeds. Dual duty:
  k=1 ablation point for the O(1/k) prediction + connects increment-7's result to the new
  environment/n. Report-only (not an adoption candidate).
- **bc** — the B+C stack: ensemble-KD (5 fresh teachers, same 4× teacher arch/recipe as
  increment-7; soft targets AVERAGED), + logit standardization (2403.01427), + weight-EMA of
  the student (decay pre-declared), all seeds branched from a **shared early trunk** (branch
  epoch pre-declared per the LMC stability point, 1912.05671). ×5 seeds.
- **bc_sam** — bc + SAM on the student (ρ pre-declared; ~2× step cost). ×5 seeds.
- **soup (report-only, local, no training):** uniform weight-average of the 5 bc branch
  students (same trunk ⇒ same basin ⇒ souping is valid per 2203.05482); evaluate as a single
  candidate. If it beats every individual student, that is increment-9 material — report, do
  not adopt inside increment-8.

Teacher notes: teachers are throwaway, never deployed, never shipped outward; heed Cho &
Hariharan (1910.01348) — keep the increment-7 teacher size/patience, do NOT grow the teacher.

**NOT in scope:** capacity/param changes; cue lineage; dataset changes; new decoders (inherit
dispatch-7 policy); non-whitelisted ops; PCGrad (dropped permanently, Addendum H); any
deterministic/pinned-RNG "fix" (options audit §4).

## Verdict (pre-hoc `experiments/increment8_verdict.py`, committed BEFORE any training;
include ALL pre-declarations: EMA decay, SAM ρ, trunk branch epoch, foveation-free loss
weights unchanged, ensemble averaging method, logit-standardization form)

- **PRIMARY — in-cone identity recovery vs baseline-env:** held/reversal/ou in-collision
  misassoc + exit IDSW/opp CI-disjoint better, **every seed (n=5)**, clean+snr30. Material =
  recovers ≥ half the v6 regression (held misassoc ≤ ~0.425 equivalent in-environment).
  Report recovered fraction per metric + per-seed pass counts for every arm (the reliability
  measurement itself).
- **GUARD-A (HARD) — acquisition:** directed 0/72 every seed; off-cone dwell CI-neutral-or-
  better vs baseline-env, every seed, clean+snr30. Any regression drops that arm.
- **GUARD-B — lock:** v1-eval lock CI-neutral vs baseline-env, per family × rung.
- **Report-only:** kd1 vs bc inter-student variance (the O(1/k) check); classical parity
  exact; snr3 leans; fieldcone boundary re-chart if an arm survives; soup vs individuals;
  baseline-env vs GB10-v6 environment shift; ops-guard + param count == 175,790 on every
  candidate (deployment-neutrality assertion).
- **Keep-what-survives:** survivors must clear PRIMARY with no guard trip. Multiple → strongest
  material recovery; tie → simpler arm (**bc < bc_sam**). None → keep nothing, escalate UP to
  TVW (next rung on the options-audit ladder: family F collapse-exact expansion, then true
  capacity).

## Stop-and-report

1. baseline-env shifts materially from GB10 v6 on any guard surface → STOP (environment).
2. An arm trips GUARD-A → drop that arm, continue others.
3. All arms trip GUARD-A or none clears PRIMARY → STOP, escalate (options-audit ladder).
4. Any candidate changes param count / fails ops-guard → stop that candidate.
5. Any surprise needing a new decoder, data change, or cue.
6. Cloud-side: any run INCOMPLETE after watchdog → rerun once; twice → stop and report infra.

## Execution mechanics

- Branch `increment-8-bc-stack`. Pre-hoc verdict + `experiments/increment8_train.py` committed
  BEFORE staging the bundle (`gpu-fanout/scripts/stage_bundle.sh <tag>` pins the commit).
- Waves: (1) teachers ×5 + trunk ×1; (2) baseline-env ×5 + kd1 ×5 (need nothing from wave 1 —
  can run in wave 1 if quota allows); (3) bc ×5 + bc_sam ×5 (need teachers + trunk staged
  back into the bundle). Matrix file: `gpu-fanout/configs/increment8-matrix.yaml` (update the
  draft to match this dispatch). ~26 GPU runs ≈ **$105–160 in credits** at g6.xlarge caps.
- Checkpoints/logs sync back via `collect_results.sh`; evals + verdict + soup on spark2;
  artifacts to `artifacts/increment8/` + NAS backup `spark2-odmr-increment8`.
- Outward material untouched; banned numbers stay banned (16/16, 0.811, DR ~5 mT); IP hold
  stands. Strategic next-steps route UP to TVW.

## References (all full-text local; cite by arXiv id in the results doc)

2601.18909 (ensemble-response variance O(1/k)) · 2305.17581 (KD = partial variance reduction)
· 2403.01427 (logit standardization) · 2106.05237 (patient/consistent) · 1912.05671 (early
stability / trunk branching) · 2203.05482 (soups, same-basin) · 2411.18704 (weight-EMA churn)
· 2010.01412 + 2202.00661 (SAM/WASAM) · 1910.01348 (teacher-size caution) · 2103.04514 (seed
variance = instability) · 2109.08203 + 2103.03098 (n=3 too few).
