# Hybrid initializer: verified development stop

This software screen completed on October 15, 2026.
The learned initializer did not meet the registered processing-speed requirement.
The qualified classical reference remains the preferred method for this tested synthetic component task.

One fresh development set contained 128 frames.
All six classical methods passed MAE ≤2 µT, p90 ≤5 µT, and failure fraction ≤0.01.
The fastest adequate reference was frozen as `grid_single` before training.
One 3,862-parameter MLP trained for exactly 20 CUDA epochs on 8,192 separate fresh frames.
The final checkpoint was used without architecture or checkpoint selection.

## Results

| Method | MAE (µT) | p90 error (µT) | Failure fraction | p95 processing latency (ms) |
|---|---:|---:|---:|---:|
| analytic_multistart | 1.148497 | 2.301980 | 0.0 | 7.976580 |
| coarse_grid | 1.148528 | 2.302008 | 0.0 | 1.831961 |
| lookup | 1.148530 | 2.302026 | 0.0 | 1.694852 |
| fixed_single | 1.148539 | 2.302014 | 0.0 | 1.419211 |
| grid_single | 1.148627 | 2.302026 | 0.0 | 0.910636 |
| lookup_single | 1.148416 | 2.301907 | 0.0 | 1.051447 |
| hybrid | 1.148448 | 2.302170 | 0.0 | 0.968335 |

The hybrid's observed p95 speedup was **0.940414×**, below the required **2×**.
Its paired added-MAE mean was −0.000178645 µT.
The paired 95% interval was [−0.000379587, −0.000039021] µT.
The accuracy gate passed; this tiny difference does not establish useful sensing improvement.
Both the classical qualification and comparison passed independent saved-output verification.

The registered speed gate failed.
The lane stopped without nuisance generation, a sealed final test, retuning, or another candidate.
This result applies to one fixed initializer and this tested configuration.
It does not show that every neural initializer must fail.

## Timing and task limits

Classical methods ran once in randomized within-frame order.
The later hybrid pass reused every original classical prediction and timing unchanged.
Both runs used the same Spark3 CPU host, runtime versions, and one-thread settings.
Their receipts preserve the separate wall runs and host-load measurements.
This design cannot eliminate time-varying host effects.

Batch-one timing includes preprocessing, initialization, physical refinement, residual checks, and fallback.
It excludes file I/O for every method.
Cold table and weight setup are reported separately.
No warmup rows were removed.

The task assumes a positive known-axis field and a known +250 µT bias.
It does not repair the earlier arbitrary-direction sensing task.
Every fit uses the same nominal physical mixture.
The generator varies unobserved MW scale and gradient, so that mixture remains an approximation.
No real instrument, measurement bandwidth, energy saving, or FPGA compatibility was established.

## Published evidence

- [Development inputs, truth, and manifest](development/manifest.json): all 128 frames and labels are present.
- [Original classical predictions](classical/predictions.json) and [receipt](classical/receipt.json): six methods, with flags and timings.
- [Classical qualification](qualification.json) and [independent verification](qualification-verification.json).
- [Combined comparison predictions](comparison/predictions.json) and [receipt](comparison/receipt.json).
- [Comparison metrics](comparison.json), [saved bootstrap indices](comparison.bootstrap.npy), and [independent verification](comparison-verification.json).
- [Frozen model](model/initializer.npz), [training receipt](model/training.json), and [training manifest](training/manifest.json).
- [Source and approval provenance](provenance.json) and [artifact hashes](artifact-sha256.json).
- [Resource receipt projections](resource-projections/): ten jobs, with exact charged resources and original receipt hashes.
- [Frozen protocol](../../../experiments/nv_hybrid_screen/protocol.json) and [independent verifier source](../../../experiments/nv_hybrid_screen/verify_saved.py).

Every copied scientific evidence file retains its original bytes.
Resource records are explicitly labeled field projections.
They omit commands, private paths, full environments, and approval contents.
They preserve source hashes, approval hashes, status, timestamps, resource charges, and original receipt hashes.
The package includes only consumed data seeds, the derived training seed, and saved bootstrap indices.
Original approval bodies and custody certificates are omitted because they contain unused seed material.
Their hashes remain in the provenance record.

The training manifest preserves hashes for training arrays that are not included here.
The trained weights and complete training receipt are included.
Training arrays are unnecessary for the saved-output metric checks below.
These checks neither retrain the model nor reproduce timing measurements.

## Recompute from a public checkout

Set `WORKER_ROOT` to an absolute standalone `odmr-edge-ml` checkout.
For the public monorepo, use its `workers/odmr-edge-ml` directory.
Do not use the monorepo root directly.
Set `PYTHON_BIN` to an absolute Python interpreter with NumPy installed.
The verifier requires NumPy and the standard library only.

    PACKAGE="$WORKER_ROOT/docs/nv_contribution_screen_2026-10/hybrid"
    CHECKER="$WORKER_ROOT/experiments/nv_hybrid_screen/verify_saved.py"
    OUTPUT_DIR="$(mktemp -d)"
    "$PYTHON_BIN" "$CHECKER" --data "$PACKAGE/development" --predictions "$PACKAGE/classical" --report "$PACKAGE/qualification.json" --report-sha256 f23bc33ac831a2462322aa9e83b21ae1083d6411c28d06da5de72bf7633482c4 --out "$OUTPUT_DIR/qualification-verification.json"
    "$PYTHON_BIN" "$CHECKER" --data "$PACKAGE/development" --predictions "$PACKAGE/comparison" --report "$PACKAGE/comparison.json" --report-sha256 d646ae6a413344836ebf9ffabb3caefd1a0a08a03fe2f0ca48cdffece42ddd28 --qualification "$PACKAGE/qualification.json" --out "$OUTPUT_DIR/comparison-verification.json"

Both commands must print `RESULT: PASS`.
A verifier PASS confirms the saved calculations, including the failed experimental gate.
It does not convert this negative development result into a successful adoption decision.

These exact checks already passed on the original study artifacts.
Package copying was verified by byte hashes.
The coordinator must run these paths from the final public checkout before declaring publication complete.
