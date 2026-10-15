# Fast-estimation component screen

Prepared 2026-10-15. Execution requires root-approved custody and shared fleet reservations.
No population data, trained weights, or performance results exist in this preparation.
The base is `4bb3a035ed708652af471f70114ccb4e91677d9a`.
Only unchanged forward-model source is reused from the completed experiment.

This is a positive, known-axis task with a known +250 µT bias.
It does not repair the original arbitrary-direction task.
The network proposes a scalar field and five scalar nuisance parameters.
It is research code, not the production residual model or an FPGA export.

## Prospective component gate

The earlier unspecified-deadline prerequisite is superseded before any population run.
Acquisition, settling, transfer, recovery, and the instrument deadline remain unknown.
This study can establish processing efficiency only.
It cannot establish system bandwidth, energy savings, or instrument usefulness.

Profile all six classical controls on 128 fresh development frames.
A control qualifies with MAE ≤2 µT, p90 ≤5 µT, and failures ≤1%.
Choose the adequate control with the lowest p95 latency.
Break exact timing ties by method name.
Root freezes its name and the exact qualification report before training.

If no classical control qualifies, stop the acceleration study.
Otherwise train one fixed candidate after root approves that report.
The candidate needs ≥2× p95 speedup against the frozen reference.
Its paired added-MAE upper 95% limit must be <0.1 µT.
Both methods must still meet the absolute accuracy and failure limits.
A secondary nuisance comparison cannot replace a failed development result.
No architecture search, threshold change, or second candidate is allowed.

## Methods and fairness

All methods receive the same 100 bins, photon budget, calibration, and prior.
Every physical refinement uses the same weighted least squares and analytic Jacobian.

| Method | Initial refinements |
|---|---:|
| analytic_multistart | Six fixed starts |
| coarse_grid | Two starts from a 299-point grid |
| lookup | Interpolated grid start and best grid start |
| fixed_single | One B45 start with observed common center |
| grid_single | One best grid start |
| lookup_single | One interpolated grid start |
| hybrid | One learned start |

The grid solves linear contrast, baseline, and slope coefficients before refinement.
Its initialization is unweighted; all refinements use identical observed-intensity weights.
The six-start method completes its search once.
Every other method may use that same six-start search once as fallback.
A rejected result returns operational 45 µT and remains in all metrics.
Fallback, failures, boundary hits, false acceptance above 5 µT, and fit evaluations are reported.
Residual acceptance is not a calibrated confidence interval.

The generator varies temperature, MW scale, gradient, linewidth, contrast, baseline, and slope.
Every physical fit uses nominal MW1 and gradient0.196875.
Unknown row MW and gradient are not supplied to an estimator.
This is a disclosed likelihood approximation, shared by every refinement.
The network learns only under the registered training prior.
The nuisance split holds out the two outer temperature bands.
It is a development stress check, not sealed final evidence.

The MLP is fixed: 100→32→16→6, ReLU, 3,862 parameters.
Training uses CUDA, 20 epochs, Adam lr0.001, batch256, and the final checkpoint.
NumPy float inference includes all three network layers inside batch-one timing.
No quantization or FPGA compatibility is claimed.

## Timing and saved evidence

Timing includes preprocessing, initialization, refinement, residual checks, and fallback.
File I/O is excluded for every method.
Cold table or weight setup is reported separately.
No warmup frame is removed.

The initial development run times the six classical methods once.
The later hybrid run reads those saved predictions and timings unchanged.
It verifies identical data, host, Python, NumPy, SciPy, and thread settings.
The receipt explicitly identifies separate wall runs and records host load before and after.
Root reserves a quiet host for both runs.
This design cannot remove all time-varying host effects.
The nuisance run times all seven methods in randomized within-frame order.
It uses the reference selected on development without reselection.

Saved reports bind the data manifest, prediction receipt, and paired-bootstrap index array.
`verify_saved.py` independently recomputes metrics, limits, baseline choice, and comparison gates.
It uses only NumPy and the standard library.
It imports no estimator, renderer, training code, or scoring helper.
The verifier checks reused classical records exactly.
It does not establish fresh runtime measurements or real-sensor transfer.

## Approval and resource contract

Every numerical child command must run through root's shared accounting controller.
The controller entrypoint is `accounting.py run --spec ABSOLUTE_JOB_SPEC.json`.
Its immutable specification binds the approval file and every executed source hash.
The controller provides `TYCHON_NUMERICAL_APPROVAL_SHA256` and `TYCHON_NUMERICAL_RUN_ID`.
It sets numerical threads to one and limits the host and GPU memory.
These script guards do not replace resource accounting.

Approval needs `claim_scope: component_efficiency_only`, authorized phases, protocol and source hashes, and the renderer hash.
Initial approval covers development generation, profiling, and scoring only.
Training and comparisons need a later approved qualification hash and frozen classical name.
Hybrid comparison additionally requires the frozen weights hash.
Nuisance generation and comparison require explicit later phases.

The seed certificate covers prior integer seeds below 2^63.
Two older 256-bit entropies were checked separately against the new seed namespace.
Do not claim every historical entropy lies below 2^63.
Six distinct 128-bit seeds come from the custodian's certificate and immutable supplement.
The derived Torch seed must equal the supplement's audited value.
No old data, prediction, result, or seed supports selection.

The provisional lane share is 4,800 CPU seconds and 1,800 cumulative wall seconds.
Training allows ≤32 GiB; CPU workers allow ≤8 GiB.
These are shares of fleet limits, not fresh budgets.
Run one worker with one numerical thread.
No Beelink, FPGA, board power, .vnnx compilation, or hardware work is authorized.

## Staged child commands

These are child commands for approved accounting specifications, not execution permission.
All paths must be absolute.
On Spark3, use `PYTHON_BIN=~/miniconda3/bin/python3`.
Set `WORKER_ROOT` to the isolated source checkout.
Set `LANE="$WORKER_ROOT/experiments/nv_hybrid_screen"`.
Set `APPROVAL`, `OUT`, and each saved report hash from root's frozen records.

Initial development:

    "$PYTHON_BIN" "$LANE/data.py" --approval "$APPROVAL" --split development --out "$OUT/development"
    "$PYTHON_BIN" "$LANE/run.py" --approval "$APPROVAL" --data "$OUT/development" --out "$OUT/classical"
    "$PYTHON_BIN" "$LANE/score.py" --approval "$APPROVAL" --data "$OUT/development" --predictions "$OUT/classical" --out "$OUT/qualification.json"
    "$PYTHON_BIN" "$LANE/verify_saved.py" --data "$OUT/development" --predictions "$OUT/classical" --report "$OUT/qualification.json" --report-sha256 "$QUALIFICATION_SHA256" --out "$OUT/qualification-verification.json"

After classical qualification and root's exact report approval:

    "$PYTHON_BIN" "$LANE/data.py" --approval "$APPROVAL" --split train --out "$OUT/train"
    "$PYTHON_BIN" "$LANE/train.py" --approval "$APPROVAL" --data "$OUT/train" --qualification "$OUT/qualification.json" --out "$OUT/model"

After root freezes the trained weights:

    "$PYTHON_BIN" "$LANE/run.py" --approval "$APPROVAL" --data "$OUT/development" --out "$OUT/comparison" --weights "$OUT/model/initializer.npz" --qualification "$OUT/qualification.json" --reuse-classical "$OUT/classical" --methods hybrid
    "$PYTHON_BIN" "$LANE/score.py" --approval "$APPROVAL" --data "$OUT/development" --predictions "$OUT/comparison" --qualification "$OUT/qualification.json" --out "$OUT/comparison.json"
    "$PYTHON_BIN" "$LANE/verify_saved.py" --data "$OUT/development" --predictions "$OUT/comparison" --report "$OUT/comparison.json" --report-sha256 "$COMPARISON_SHA256" --qualification "$OUT/qualification.json" --out "$OUT/comparison-verification.json"

After a passing development screen and separate nuisance authorization:

    "$PYTHON_BIN" "$LANE/data.py" --approval "$APPROVAL" --split nuisance --out "$OUT/nuisance"
    "$PYTHON_BIN" "$LANE/run.py" --approval "$APPROVAL" --data "$OUT/nuisance" --out "$OUT/nuisance-comparison" --weights "$OUT/model/initializer.npz" --qualification "$OUT/qualification.json" --methods analytic_multistart coarse_grid lookup fixed_single grid_single lookup_single hybrid
    "$PYTHON_BIN" "$LANE/score.py" --approval "$APPROVAL" --data "$OUT/nuisance" --predictions "$OUT/nuisance-comparison" --qualification "$OUT/qualification.json" --out "$OUT/nuisance-report.json"
    "$PYTHON_BIN" "$LANE/verify_saved.py" --data "$OUT/nuisance" --predictions "$OUT/nuisance-comparison" --report "$OUT/nuisance-report.json" --report-sha256 "$NUISANCE_SHA256" --qualification "$OUT/qualification.json" --out "$OUT/nuisance-verification.json"

No final seed exists.
Any later sealed comparison needs a separate registration and fresh custody.

## Preparation checks

Root ran the two manufactured physics tests at d68171a once: PASS.
They used 0.198 CPU seconds, 0.218 wall seconds, and about81 MB.
The physics implementation remains unchanged.
The newer mocked fallback tests await a separate accounting reservation.
Run only those changed tests:

    "$PYTHON_BIN" "$WORKER_ROOT/tests/test_nv_hybrid_screen.py" FallbackFairnessTests

Source syntax has been parsed.
No population profile, training, saved-output verifier, or CUDA calculation has run yet.
No timing or memory estimate below is measured performance.
Planning estimates are 1–5 minutes for the profile and 1–10 minutes for tiny-model training.
Root must reserve each job inside the remaining fleet allowance.
The 8192×100 float32 input matrix is about3.3 MiB before framework overhead.
