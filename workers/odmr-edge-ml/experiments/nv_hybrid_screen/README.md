# Fast-estimation development preparation

Prepared 2026-10-15. **No numerical runs are authorized by these files.**
No data, weights, performance results, or old evaluation inputs are included in this lane.
The source base is 4bb3a035ed708652af471f70114ccb4e91677d9a.
Only the unchanged single-axis forward-model source is imported from the completed study.

This is an identifiable, positive known-axis laboratory task with a +250 µT bias.
It does not repair the original arbitrary-direction task.
The initializer predicts one field value plus five scalar nuisance parameters, never a 3D field vector.
It is research code, not the production residual model or an FPGA export.

## Opportunity gate

Root must freeze the draft protocol and shared fleet accounting before any numerical command.
The acquisition, settling, transfer, recovery, and useful processing deadline remain unspecified.
They must come from a stated instrument requirement or an explicitly modeled use case.
There is no claim that processing currently limits measurement rate.

Profile all three fixed classical methods on one fresh development split.
Select the fastest adequate classical method: MAE ≤2 µT, p90 ≤5 µT, failures ≤1%.
Only train if its p95 exceeds the declared deadline AND processing contributes at least20% of the modeled cycle.
If a simpler method already meets the deadline, adopt it and stop training.
If no classical method meets accuracy, stop this acceleration claim and review measurement adequacy.
Do not pick a deadline after seeing which one makes the neural method look useful.

## Methods and fairness

All methods use exactly the same100 bins, photon budget, priors, calibration, and physical likelihood approximation.
The generator has unknown per-row temperature, MW scale, gradient, width, contrast, baseline, and slope.
Training and development share the registered prior.
The nuisance split withholds both outer temperature bands; it changes only common center and associated forward physics.
The conditional software claim does not establish measured instrument transfer.

Classical methods:
- Analytic six-start physical fit.
- A299-point coarse grid with precomputed linear least-squares initialization, then two physical refinements.
- The same lookup table with inverse-score interpolation of its four best entries, then two refinements.

The grid's linear initialization is unweighted. Every refinement uses the same observed-intensity weighting and analytic Jacobian.
The network is one100→32→16→6 ReLU MLP,3862 parameters.
Training is CUDA-only,20 fixed epochs, Adam lr.001, batch256, final checkpoint only.
CPU deployment uses the saved float weights through NumPy; Torch overhead is not shifted outside one method's timing.
There is no architecture sweep, early stopping, quantization, or board claim.

Every method uses the same bounded physical refinement, residual check, and full-domain six-start fallback.
A residual-rejected result returns45 µT and remains in operational metrics.
Fallback work and all rejected rows count.
Residual acceptance is not a calibrated confidence interval; false acceptance above5 µT is reported separately.
The residual threshold is a proposed screening rule and must be frozen before data.

Batch-one timing includes preprocessing, initialization, physical correction, residual checks, and fallback.
Cold setup and table/weight loading are reported separately.
No warmup rows are removed. Each frame is timed once per method in randomized within-frame order.
All compared methods must run on the same quiet CPU host, with the same single-thread settings.
Spark3 GPU training does not justify comparing GPU neural inference against CPU fitting.
Compute speed is not sensor bandwidth, energy, or physical acquisition time.

## Root approval contract

Every command needs --approval with an explicit approved phase, protocol SHA256, complete source hashes, and renderer SHA256.
The root accounting wrapper must provide TYCHON_NUMERICAL_APPROVAL_SHA256 and TYCHON_NUMERICAL_RUN_ID.
It must also set OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1.
These environment checks bind execution to root approval; they are not a replacement for resource accounting.
No wrapper exists in this lane. Integrate with root's shared fleet controller before execution.

Approval also supplies distinct128-bit seeds for train, development, nuisance, timing_order, bootstrap, and training_rng.
Every supplied seed must lie in[2^96,2^128); a metadata-only certificate must establish prior data seeds below2^96.
Torch uses a separately recorded derived seed in[2^63,2^64); training requires the stronger prior-seed upper bound2^63.
No old dataset, result, or seed is used for selection.
Training additionally needs the approved exact bottleneck-report hash.
Hybrid comparison needs the exact frozen initializer hash.
Nuisance commands require separate compare_nuisance and score_nuisance approval.

## Exact command forms after approval

Set WORKER_ROOT to the absolute standalone worker checkout.
Set LANE="$WORKER_ROOT/experiments/nv_hybrid_screen".
Set PYTHON_BIN, APPROVAL and OUT to absolute paths.
Every line below must be the child command of root's accounting wrapper.
They are command templates, not permission to run this preparation.

    "$PYTHON_BIN" "$LANE/data.py" --approval "$APPROVAL" --split development --out "$OUT/development"
    "$PYTHON_BIN" "$LANE/run.py" --approval "$APPROVAL" --data "$OUT/development" --out "$OUT/classical"
    "$PYTHON_BIN" "$LANE/score.py" --approval "$APPROVAL" --data "$OUT/development" --predictions "$OUT/classical" --out "$OUT/bottleneck.json"

Stop if the useful bottleneck gate fails. After root approves its exact report:

    "$PYTHON_BIN" "$LANE/data.py" --approval "$APPROVAL" --split train --out "$OUT/train"
    "$PYTHON_BIN" "$LANE/train.py" --approval "$APPROVAL" --data "$OUT/train" --bottleneck "$OUT/bottleneck.json" --out "$OUT/model"
    "$PYTHON_BIN" "$LANE/run.py" --approval "$APPROVAL" --data "$OUT/development" --out "$OUT/comparison" --weights "$OUT/model/initializer.npz" --methods analytic_multistart coarse_grid lookup hybrid
    "$PYTHON_BIN" "$LANE/score.py" --approval "$APPROVAL" --data "$OUT/development" --predictions "$OUT/comparison" --out "$OUT/comparison.json"

After source/weights freeze and separate nuisance authorization:

    "$PYTHON_BIN" "$LANE/data.py" --approval "$APPROVAL" --split nuisance --out "$OUT/nuisance"
    "$PYTHON_BIN" "$LANE/run.py" --approval "$APPROVAL" --data "$OUT/nuisance" --out "$OUT/nuisance-comparison" --weights "$OUT/model/initializer.npz" --methods analytic_multistart coarse_grid lookup hybrid
    "$PYTHON_BIN" "$LANE/score.py" --approval "$APPROVAL" --data "$OUT/nuisance" --predictions "$OUT/nuisance-comparison" --out "$OUT/nuisance-report.json"

The development screen proposes≥2× p95 processing improvement, added-MAE upper paired95% limit<.1 µT, and unchanged absolute gates.
No development screen is a sealed final evaluation or adoption decision.
Root must register any later evaluation separately with one fresh custody-controlled test.

## Resources, verification, and hardware

CPU baseline is portable NumPy/SciPy; CUDA training is optional and isolated.
Estimated preparation allocations: CPU workers≤8GiB; training≤32GiB; model weights<20KiB.
The8192×100 training matrix is about3.3MiB float32 before framework overhead.
Runtime estimates are planning values only: initial CPU profile1–5minutes; tiny training1–10minutes including startup.
No throughput, numerical correctness, import, or CUDA tensor smoke test has run in this preparation.
Root must fit all lanes within one shared allowance; these estimates do not reserve or reset any budget.

Prepared tests check analytic derivatives and nominal renderer parity. They await root's numerical test gate.
Before training, use the repository's operation guard under that same approval.
Float Linear/ReLU structure is not proof of INT8 or VectorBlox compatibility.
A promising result can later go to the polarfire-hybrid-control owner for matched V250 latency, energy, and recovery validation.
Compare strong classical CPU/FPGA alternatives and actual acquisition costs fairly.
Do not power the smart plug, access Beelink/FPGA, compile .vnnx, buy hardware, or connect an NV diamond from this lane.
