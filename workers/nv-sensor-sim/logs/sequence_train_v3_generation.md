# sequence_train_v3 / sequence_eval_fieldcone_v1 — generation run log

**Dispatch:** `tychon-verification-workbench/tvw/audits/dispatch-nvsim-sequence-train-v3-2026-07-07.md`
(approved with four amendments; Amendment 1 committed to **Option A — angle-stratified widening**).
**Session:** nv-sensor-sim on ws2, 2026-07-07.
**Branch:** `feat/sequence-train-v3-coverage` (created from `cec6591` = `feat/dwell-identity-lineage` HEAD).

## Motivation (measured)

`odmr-vector-tracking` increment-5 (`docs/increment5_results.md`, commit dde2a74) found a
deterministic field-acquisition failure: the learned tracker loses field lock **216/216** on
dwell merge pairs **(0,2)/(4,6)**, which force **B to 41.5°/53.2° off the deployment bias at
3.9/3.3 mT** — outside the v1/v2 training cone (≤ ~18° off-bias). v3 widens the trained off-bias
cone to **≥ 60°** (so 53.2° sits in the interior) and lowers the **|B| floor to 3.0 mT**, on the
same v1 contract; `sequence_eval_fieldcone_v1` is the held-out boundary eval (Deliverable 2).

## Environment

ws2 conda base: numpy 2.4.2, simos 0.2.3, qutip 5.2.3 (match the archived v1 lineage). All
local compute. Test suite green throughout: **215 passed, 4 skipped** (188 dwell baseline + 27 new).

## Design — angle-stratified widening (Amendment 1, Option A)

**Stop-and-report that drove Option A.** The approved isotropic ±4.0 mT widening geometrically
cannot reach ≥60°: the reachable off-bias angle is bounded by `arcsin(|ext|/|bias|)`, so ±4.0 mT
caps at 53.1° (the failure on the *rim*), and reaching 60° at the |B|≥3.0 mT floor needs
`|ext| = 4.36 mT` at a near-tangent direction — a sliver uniform sampling never draws (measured
isotropic ±4.5 mT: median 21°, p99 44°, **0/1500 ≥ 53°**). TVW ruled Option A; nv-sim proceeded.

**Two sub-populations** (both under three per-frame reject guards — |B| floor, window containment,
min per-axis |B·n|):
- **angle-stratified (~70%)** — off-bias angle drawn `U[0, 62°]`, magnitude `U[3.0, 6.0] mT`,
  constructed at that stratum with random azimuth; v1-style held/reversal/ou families set the ramp
  shape. The target angle is drawn in an outer loop so guard rejection does not bias the recorded
  density. (The ou base is drawn with ~3.5σ of OU headroom so the perturbation stays in-grid.)
- **directed (~30%)** — v1-style pass-through crossings aimed exactly at the enumerated cross-axis
  merge degeneracies (reusing the dwell `merge_direction`/`a_merge` machinery). The bias admits
  **4 merge templates: (2,4), (0,6), (4,6), (0,2)** — the two hard failure pairs (0,2)/(4,6) among
  them.

**Cold-start diversity (Amendment 1 condition 2).** The failure is off-cone *acquisition*, not
lock-carrying. `cold_start_fraction = 0.5` of the angle-stratified sequences **start frame-0 at
their drawn (possibly wide) stratum** (acquisition); the rest carry a lock outward from the
near-bias cone. Recorded per sequence in `start_mode` (0=acquire, 1=carry, −1=directed).

**Stratification law (Amendment 1 condition 1).** The full draw distribution (angle law U[0,62°],
|B| law U[3,6] mT, cold-start fraction, carry parameters, directed fraction) is recorded in the
manifest `stratification_law` — this is a training **density** change vs v1/v2 isotropic sampling,
needed for increment-6 coverage attribution.

## Results — `sequence_train_v3` (cues OFF)

2048 / 512 / 512 sequences, T=256, 951-pt pinned grid, master_seed 20260703. Rendered ~20 min.
`config_hash 4e7ffabc9f9d`; content **`data_md5 be28fab5a129ff3b757ce77a92e60b47`**; raw
`dataset.h5` md5 `f32bcd72b7bf6f5eaf0125853b03fcb4`.

Achieved coverage (train split, N=2048):
- **off-bias angle**: min 0.8°, mean 30.7°, **max 65.5°**; frac ≥41.5° = 0.285, **frac ≥53.2° =
  0.076** (53.2° in the interior), **frac ≥60° = 0.023**. (Isotropic gave 0/1500 ≥ 53°.)
- **|B|**: min **3.01 mT** (floor honored), mean 4.18 mT, max 5.81 mT.
- sub-populations: directed 569 / angle-stratified 1479 (realized 0.278); start modes acquire 785
  / carry 694 (realized cold-start 0.531).
- directed template counts (idx→pair): 0=(2,4):139, 1=(0,6):148, 2=(4,6):135, 3=(0,2):147 — the
  two hard failure pairs (0,2)/(4,6) each get ~140 pass-through crossings at the exact degeneracy.

## Results — `sequence_eval_fieldcone_v1` (cues OFF)

Held-out (off-bias angle × |B|) ladder, eval-only (all `test`), T=256, 951-pt pinned grid,
master_seed 20260713. 10 buckets × 12 = **120 sequences** (failure 24 / control 48 / beyond 48).
Rendered 47 s. `config_hash` in manifest; content **`data_md5 92dc06692d1975f6fcd101e70cc02d99`**;
raw `dataset.h5` md5 `b152cb6bd1b5090b54389f6404856c23`.

- failure buckets ramp through the exact (0,2) and (4,6) merges.
- realized off-bias 10.0°–**70.0°** and |B| **1.98**–5.00 mT — the `beyond` buckets genuinely
  exceed the widened cone (>62°) and the training floor (<3.0 mT). All 10 buckets feasible inside
  the pinned window (no stop-and-report).

## Determinism & non-regression

- **Determinism**: `sequence_eval_fieldcone_v1` regenerated to a temp dir reproduces `data_md5`
  **identically** (92dc06…); the v3 widened pipeline's same-seed→same-`data_md5` property is
  covered by `tests/smoke/test_sequence_v3_pipeline.py` and the fully-seeded draw structure (new
  spawn keys: sub-population = 6, fieldcone geometry = 7).
- **Seeds disjoint**: v3 (n=3072) and fieldcone (n=120) per-sequence seed sets verified pairwise
  disjoint from v1 (20260701) and v2 (20260702).
- **Protected lineages untouched**: v1/v2/dwell/archive generators were not run. dwell_v1 raw md5
  `41509ee65d68e652d3d1b10418188908` and dwell_v1_cues `29aa923526273d1e7e485fac0658ea1b` verified
  unchanged. Cues-OFF byte-identity of the legacy isotropic/fixed paths is covered by the existing
  sequence tests (215 green).

## Cues-ON config (not generated)

`configs/sequence_train_v3_cues.yaml` is a seed-paired twin (same master_seed 20260703, identical
widened envelope) with the two default-OFF physics cues turned ON (Meneses strain ladder + 3.8 ppm
CR). **Not generated** — it is a deliverable for a later cue-retrain experiment. The sequence
pipeline now supports the cue knobs (default OFF = byte-identical); generating it later is a single
CLI call.
