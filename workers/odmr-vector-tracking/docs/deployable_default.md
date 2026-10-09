# Deployable default — canonical registry

*Authoritative record of the default tracker checkpoints + re-decode policy. Updated on a
default flip only. Current: **v6 (angular-coverage retrain)**, flipped 2026-07-09 per TVW
dispatch-7 (`dispatch-7-v6-default-2026-07-08.md`), from the increment-6 SUCCESS verdict
(`docs/increment6_results.md`, main b102cf3) and the TVW deploy ruling
(`audit-dwell-program-2026-07-07.md` Addendum D). Zero-retrain: this flip is a checkpoint swap +
a pre-hoc re-selection of the decode policy on the new weights — no training, no new decoders.*

**Status of v6: FP32 research default.** "v6" names the model. The status means v6 is the default
model for research evaluation in FP32 simulation. It is not a deployed model. The word "deployable"
in the title and in some headings below is a historical label for "default checkpoint"; it does
not mean the model runs on target hardware.

## Readiness states of the v6 default

Each state is separate. A later state does not follow from an earlier one.

| state | v6 default | evidence in this repo |
|---|---|---|
| trained (FP32) | **yes** — 3 seeds, FP32 PyTorch, trained on simulated data (`sequence_train_v3`) | `docs/increment6_results.md`; md5s below |
| evaluated | **yes, on synthetic sets only** — the v1 standing eval (families `held`, `ou`, `reversal`; noise rungs clean, snr30, snr10, snr3), the dwell sets (in-cone and off-cone; `cross` and `bounce` topologies), and the field-cone set `sequence_eval_fieldcone_v1` (120 sequences) | `docs/increment6_results.md` |
| exported (INT8 or other format) | **no** — no INT8, TFLite or ONNX export of the tracker exists. The `find` check in `docs/increment8_results.md` §0(i) returns nothing | `docs/increment7_results.md`, `docs/increment8_results.md` §0(i) |
| compiled for a target | **no** — no `.vnnx` or other target build exists for the tracker. The architecture passes the PyTorch-graph ops-guard and the flatbuffer op check, but that is a design property, not a compile | `docs/increment8_results.md` §0(i) |
| executed on target hardware | **no** — no on-target run and no INT8 parity run exists; the tracker is not in the FPGA loop. INT8 export and on-target parity are a separate open work item | `docs/increment8_results.md` §0(i) |

**Measurement conditions for every number in this file.** All figures are FP32 simulation
results. Each figure comes from the dataset named beside it (v1 standing eval, dwell sets, or
field-cone set), at the noise rung named beside it, on synthetic data from the simulator. The
angular envelope of the v6 training data is a cone of at least 60° off the bias axis. The
measured reliable band is narrower: about 30–40° off the bias axis (see "Boundary language").
Nothing here is a hardware result.

## Deployable default — v6 checkpoints + re-decode policy

**Checkpoints** (FP32 PyTorch; `gated+linear+aug`, wave-2 recipe, trained on simulated
`sequence_train_v3` angular coverage; run record in `docs/increment6_results.md`; artifacts gitignored, preserved on disk at
`artifacts/increment6/runs/`):

| seed | run dir | early stop | best val | md5(`best.pt`) |
|---|---|--:|--:|---|
| 20260701 | `v3_gated_linear_snr10` | 210 | 0.6581 | `bf5bfa775c5adcc1f527ef3750c9dfbe` |
| 20260711 | `v3_gated_linear_snr10_s20260711` | 270 | 0.6995 | `0d531c2e6a2a42913f18a2e78688756b` |
| 20260721 | `v3_gated_linear_snr10_s20260721` | 250 | 0.6456 | `842e867cec1e00cc4e51f00aa400de84` |

The md5s match the increment-6 run record (each checkpoint's `summary.json` seed / `epochs_run` /
`best_val_total` verified identical to the values above; `n_trainable_params` = 175 790,
`dataset_config_hash` = `4e7ffabc9f9d`).

**Re-decode policy** (re-selected on v6, pre-hoc rule in `experiments/v6_redecode_policy.py`;
result `artifacts/increment6/v6_redecode_policy.{json,md}`). The standing menu is
`baseline / A1(physics) / A3(stack5)` (A3 ≡ `stack5`); the selection metric is in-collision
misassoc, pooled 3 seeds, Wilson 95%, CI-disjoint + every-seed to switch a family, ties keep the
v2-era choice:

| surface | family / population | v2-era decode | **v6 selected** |
|---|---|---|---|
| v1 standing eval | held | baseline | **baseline** |
| v1 standing eval | ou | A3(stack5) | **A3(stack5)** |
| v1 standing eval | reversal | A3(stack5) | **A3(stack5)** |
| dwell through-merge (finding b) | cross / bounce, in-cone + off-cone | A3(stack5) | **A3(stack5)** |

**No family switched** — the v2-era per-family policy transfers unchanged to the v6 weights. This
is expected: the decode menu operates on the same architecture's score/field outputs, so *which*
decode wins is a structural property of the family dynamics, not of the training distribution;
the v6 identity regression (below) is a weights property that shifts every decode together and so
cannot change the ranking. On `held` (v1 standing eval, clean rung, simulated, FP32, pooled 3
seeds), A3 shows a lower `idsw_opp` than baseline (0.324 vs 0.398) but only **neutral** misassoc — under the pre-hoc selection metric this is a tie, so the
continuity rule keeps `baseline`.

**Flip guard (pre-hoc stop-conditions, all cleared):** (1) field lock is decode-invariant
(`b_est` untouched, asserted at build) and v6 checkpoint lock is CI-neutral-or-better than v2 at
every family × rung → the flip does not damage the field/vector claim anywhere; (2) the re-decode
`baseline` reproduces the `matrix_6_coverage.json` learned column exactly (no eval-path surprise);
(3) v6 md5s match the run record.

## In-cone identity reference — v2 checkpoints (PINNED, not the default)

v2 keeps sharper in-distribution identity and stays pinned as the identity reference. **Any
quotation of the numbers below must say "v2 checkpoints"** — they do not describe the v6
default. The v2 checkpoints are also FP32 simulation models: they have no export, no target
build and no on-target run.

| seed | run dir | early stop | best val | md5(`best.pt`) |
|---|---|--:|--:|---|
| 20260701 | `artifacts/increment2c/v2_gated_linear_snr10` | 330 | 0.0678 | `9ecc3b6616ecaf94f0b43839dd5e11a9` |
| 20260711 | `artifacts/increment2c/v2_gated_linear_snr10_s20260711` | 410 | 0.0613 | `074896dde57785922086f134f8056ee0` |
| 20260721 | `artifacts/increment2c/v2_gated_linear_snr10_s20260721` | 335 | 0.0652 | `45c7a7fc53d94e4551142153be03c3ce` |

**Claims that remain v2-checkpoint-scoped** (must be attributed to "v2 checkpoints", never quoted
of the v6 default). Every figure is a simulation result in FP32:

- **clean held misassoc = 0.311** (v2 checkpoints, v1 standing eval, `held` family, clean rung,
  pooled 3 seeds). The v6 default is 0.540 on the same cell.
- **dwell in-cone bounce exit-idsw = 0.045** (v2 checkpoints, dwell set, in-cone `bounce`
  topology, A3 decode, clean rung). The v6 default is 0.077 on the same population.
- **v2 v1-eval field lock** (v2 checkpoints, v1 standing eval, pooled 3 seeds; counts are lock
  losses over sequences): clean/snr30/snr10 held 1/111, ou 0/90, reversal 0/69; snr3 held
  28/111, ou 16/90, reversal 12/69.

## v6 trade-off caveat (carried by any claim built on the v6 default)

All figures in this section are FP32 simulation results on synthetic data. The dataset and
noise rung are named beside each figure.

- **In-cone identity regression:** on the v1 standing eval the v6 default's identity is worse than
  v2's, **CI-disjoint at clean → snr10** (e.g. `held` family, clean rung: misassoc 0.311 [v2] →
  0.540 [v6], exit IDSW/opp 0.171 → 0.398; reversal/ou likewise), softening to mixed at snr3. This is the price of
  spreading a fixed 175 790-param capacity over the ~3.4× wider v3 angle cone under a frozen
  recipe. The dwell through-merge identity claim (finding b) still holds on v6 vs KF-conditioned
  (dwell set, in-cone `bounce` topology, clean rung: 0.077 vs 0.508, every seed), weaker than
  v2's in absolute terms.
- **snr3 lock lean:** at snr3 (the noisiest rung, v1 standing eval) the v6 field-lock point
  estimates run slightly worse than v2 (reversal/ou), but the difference is **CI-neutral** (not a guard trip) — reported, not a claim.

## Boundary language (measured; geometry-specific — never a blanket angle claim)

Chart: `artifacts/increment6/fieldcone_boundary.png`. Measured on the simulated field-cone set
`sequence_eval_fieldcone_v1` (120 sequences; clean rung, snr30 near-identical; FP32; pooled 3
seeds). The v6 default is **reliable to ~30–40° off-bias for generic geometries, and holds the
directed (0,2)/(4,6) degeneracy geometries exactly** (the ~28% directed training component cleared
them 0/72 lost; 36 sequences each). The 30° generic control still loses 8/36 sequences, and the
45° and 52° controls lose 30/36 and 27/36, so "reliable" describes a band edge, not zero loss.
**Past the training envelope it is a hard cliff, not graceful decay** (never-acquires in 135–144/144
beyond the cone), and the **|B| = 3.0 mT floor binds** (below it, acquisition fails regardless of
angle). The training data covers a cone of at least 60° off-bias; the measured reliable band is
narrower than that. All of this is simulation; no hardware run exists. Coverage
is geometry-specific — directed oversampling taught its aim points, angle-stratified density
taught the band to ~30–40°; there is no generic capability past that. Do not state a single
"works to N°" number.

## Follow-ups (route UP to TVW — not actioned here)

The identity-recovery retrain (capacity bump or v2+v3 curriculum to buy back in-cone identity at
coverage) is **dispatch-8 / increment-7**, a separate retrain dispatch pending Jason's go — not
part of this flip.