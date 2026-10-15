# NV contribution screen, 2026-10-15: two software routes, both stopped

Status: **both routes STOP.**
The hybrid route ran its development comparison and failed the registered speed gate.
The sparse route stopped earlier: its pre-development numerical qualification failed, so no development cases were run.
No final seed, evaluation data, population run, retuning, or new candidate followed either decision.
Every gate below was fixed before the results it judges.

This screen followed the [known-axis bias comparison](scalar_bias_design_2026-10.md).
It asked two questions about the same simulated known-axis task:

1. Can a small learned component make field estimation faster at matched accuracy?
2. Can adaptive frequency selection save acquisition time?

The FPGA board was not used. No measured sensor data was used.

## Route 1: fast estimation (stopped, negative)

All methods received the same 100 frequency bins, photon budget, calibration, and prior.
Every physical refinement used the same weighted least squares.

**Classical reference.** Six classical controls were profiled once on 128 fresh development frames.
A control qualified with MAE ≤2 µT, 90th-percentile error ≤5 µT, and failures ≤1%.
All six qualified. The fastest qualified control by p95 latency was `grid_single`:
MAE 1.14862695 µT, 90th-percentile error 2.302026 µT, p95 latency 0.910636 ms, and no failures.
Its qualification report is frozen with SHA256 f23bc33ac831a2462322aa9e83b21ae1083d6411c28d06da5de72bf7633482c4.

**Candidate.** One fixed candidate was trained: a 3,862-parameter MLP, exactly 20 CUDA epochs on 8,192 separate fresh frames.
It proposes the field and five nuisance parameters as the starting point for the same physical refinement.
The final checkpoint was used. There was no architecture search, checkpoint selection, or second candidate.

**Gate.** The candidate needed at least 2× lower p95 latency than the frozen reference.
Its paired added-MAE upper 95% limit also had to stay below 0.1 µT.

**Result.** The accuracy gate passed, but the hybrid was not faster:
p95 latency 0.968335 ms against 0.910636 ms, a speedup of 0.940414.
The required speedup was 2, so the route stopped.
The paired added-MAE mean was −0.000178645 µT, with 95% interval [−0.000379587, −0.000039021] µT.
That tiny difference does not establish a useful sensing improvement.
The comparison report has SHA256 d646ae6a413344836ebf9ffabb3caefd1a0a08a03fe2f0ca48cdffece42ddd28.
Independent saved-output verification passed for the qualification and the comparison.
The lane stopped without nuisance generation, a sealed final test, retuning, or another candidate.
The [hybrid evidence package](nv_contribution_screen_2026-10/hybrid/README.md) has the full method table, predictions, model, and receipts.

**Timing conditions.** All methods were timed batch-one on the same CPU host, runtime versions, and one-thread settings.
Timing includes preprocessing, initialization, physical refinement, residual checks, and fallback; it excludes file I/O.
The classical methods ran once in randomized within-frame order; the hybrid pass reused those classical timings unchanged.
This design cannot remove time-varying host effects.

**Limits.** These are component processing times on one machine.
They are not system bandwidth, end-to-end rate, energy, or hardware results.
The result covers one fixed initializer in this configuration. It does not show that every neural initializer must fail.

## Route 2: sparse acquisition (stopped at pre-development qualification)

Four classical policies were prepared: a fixed schedule, coarse-to-fine sampling, a nuisance-aware Fisher policy, and an approximate Bayesian policy.
All use the same discrete Poisson posterior and median estimator. No learned policy was proposed.

**Qualification.** Before any development or population case, the posterior approximation had to pass seven manufactured belief checks.
It failed all seven. Refining the grid moved the posterior mean by up to 4.45 µT and an interval end by up to 8.5 µT.
The approximation is therefore unqualified, and no population cases were run.

**What this means.** This is not evidence that adaptive classical acquisition is worse.
The approximation needed for a fair comparison did not qualify, so the comparison was not made.

**Verifier note.** The original saved-output verifier had a bug, which is preserved as recorded.
A separate `verify_saved_v2.py` uses the correct saved posterior for the utility identity.
No scientific gate changed. Version 2 reproduces the qualification failure for all seven beliefs.
Its saved report has SHA256 6727c79fd2eb558893b1f404b12b0a4bd43d3c55d96dc7396067ac674161c46a.
The [sparse evidence package](nv_contribution_screen_2026-10/sparse/README.md) publishes the qualification only.
It contains no population cases, case data, or unused noise seeds.

## What the screen shows

- No processing-speed advantage for the learned component at matched accuracy on this task and machine.
- No conclusion about adaptive acquisition, in either direction.
- No novelty, hardware, bandwidth, energy, or measured-sensor claim.

## Reproduce from saved outputs

Use a public checkout. Set `WORKER_ROOT` to its `workers/odmr-edge-ml` folder, not the monorepo root,
and `PYTHON_BIN` to an absolute Python path. The checks read saved outputs only; they do not retrain, run inference, or remeasure timing.

**Hybrid.** Run the two commands in the [hybrid package README](nv_contribution_screen_2026-10/hybrid/README.md#recompute-from-a-public-checkout).
They need NumPy and pin the qualification and comparison report hashes. Each must print `RESULT: PASS`.
A PASS confirms the saved calculations, including the failed speed gate.

**Sparse.** The publication filter changed one documentation file, so use the public checker with the sanitization manifest:

```bash
WORKER_ROOT=/absolute/path/to/public-checkout/workers/odmr-edge-ml
PYTHON_BIN=/absolute/path/to/python3
"$PYTHON_BIN" "$WORKER_ROOT/experiments/sparse_acquisition_screen/verify_public.py" \
  --kind qualification \
  --input "$WORKER_ROOT/docs/nv_contribution_screen_2026-10/sparse/qualification" \
  --sanitization "$WORKER_ROOT/docs/nv_contribution_screen_2026-10/SANITIZATION.sparse.json" \
  --out "$(mktemp -d)/sparse-qualification-verdict.json"
```

Expected: status `qualification_fail`, exit code 2, and empty stderr.
A traceback or a missing verdict file is a checker failure, not the expected result.
The checker accepts declared hash bindings only for two named Markdown files.
Scientific code, data, protocols, gates, and tolerances must match exactly.

## Publication notes

The publication filter replaces machine home-directory prefixes with `~` in all exported history.
Two lane documents change bytes because of that rule:

| File | Source SHA256 | Public SHA256 |
|---|---|---|
| experiments/nv_hybrid_screen/README.md | b2bcdac4ca054bdc78da7512d0039612f2606b4c66592ff6bf132ecda8d5c987 | 3a34be33841f488788eadf656ca793b963a547ca4429949b8d7eaf5f19bf5840 |
| experiments/sparse_acquisition_screen/QUALIFICATION.md | c39f34fbd319f2adf0343b493db184cdd5795d7c48f9df880e23fb874588ad21 | 934660433b59deff47798497c3055abf745025fe599feac39dd3f97af6c7a597 |

The sparse binding is the checker input [`SANITIZATION.sparse.json`](nv_contribution_screen_2026-10/SANITIZATION.sparse.json).
The hybrid README change is recorded separately in [`hybrid-doc-exception.json`](nv_contribution_screen_2026-10/hybrid-doc-exception.json); no checker reads that file.
The original documents stay unchanged in the source history.
All other new lane source and evidence files keep their exact bytes; each was compared with the reviewed lane commits.
Host names recorded in those files are fleet role labels, not credentials. They stay as recorded:
the publication's tree-wide host-name replacement does not apply to the lane source and evidence folders.
Unused seeds and private custody, approval, and accounting paths are not published.
