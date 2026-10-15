# A 20-minute reviewer path

This path separates synthetic evaluation, recorded kit tests and work still pending.
Allow 20 minutes for reading. Installation and benchmark runtime are additional.
Keep the [glossary](glossary.md) open for unfamiliar terms.

## Minutes 0–2: establish the scope

Read the [README](../README.md), especially **Demonstrated state** and **Three workstreams, one coordinator**.
The controller used replayed synthetic spectra on a PolarFire SoC development kit.
No live diamond sensor was connected.
The scalar controller, vector tracker and CPU benchmark have different evidence and limits.

## Minutes 2–5: reproduce the CPU benchmark, or inspect its records

Read the [benchmark instructions](../bench/README.md).
From the repository root, run:

```sh
make bench
```

The [Makefile](../Makefile) requires `python3.11` and network access to PyPI and the PyTorch CPU wheel index.
The [benchmark workflow](../.github/workflows/bench.yml) runs this command on Ubuntu with Python 3.11.
Use that environment for the documented route; this guide does not establish macOS compatibility.

The command trains a model and writes `bench/results.json`.
That generated file is untracked and absent from a clean checkout.
Its errors concern synthetic spectra and FP32 CPU inference.
They do not measure the deployed INT8 model or a live sensor.

If you cannot run it:

1. Read the recorded reference in [bench/README.md](../bench/README.md).
2. Inspect reference values and acceptance thresholds in [bench/expected.json](../bench/expected.json).
3. Open [CPU synthetic benchmark workflow runs](https://github.com/jasonphillip/tychon-quantum-sensing/actions/workflows/bench.yml).
4. Select a run for the commit under review and open its `bench` job.
5. Inspect **Install in venv, run benchmark, enforce expected metrics**, including its output and conclusion.

The workflow does not upload `bench/results.json` as an artifact.
Reference values and thresholds are recorded evidence, not a new measurement.
A successful run for another commit does not establish the result for your checkout.

For a fixed archival reference, [CITATION.cff](../CITATION.cff) identifies version 1.0.0, released 2026-10-12.
Its [version DOI](https://doi.org/10.5281/zenodo.23323385) is an archive fallback.
Check its contents before using it for later evidence, including the kit report dated 2026-10-14.

## Minutes 5–8: read the project account

Read the [case study](case-study.md), especially [Results and limits](case-study.md#results-and-limits).
Use its workstream descriptions to locate the relevant implementation.
Keep each result beside its stated dataset, execution target and limitation.

## Minutes 8–12: follow one failure investigation

Read [engineering decision 2: watchdog fallback](engineering-decisions.md#2-test-actual-fallback-rather-than-count-watchdog-trips).
Follow its links to the test plan and before/after raw summaries.
Compare a counted watchdog trip with an observed PID-only controller update.
The decision record describes the software correction and remaining processor-freeze and recovery-step limitations.
This is a recorded kit investigation; it does not establish physical actuator or live-sensor behavior.

## Minutes 12–14: read the pre-registered comparison study

The vector comparison study was registered before scoring and scored once on each of two sealed synthetic test sets. Read the [protocol](../workers/odmr-vector-tracking/docs/comparison_study_protocol_2026-10.md) (rule, margins and the dated addenda (a) to (l)), then the [first decision](../workers/odmr-vector-tracking/docs/comparison_study_decision_2026-10.md) and the [second decision](../workers/odmr-vector-tracking/docs/comparison_study_decision_2026-10_v2.md). The [case study's reference-estimator section](case-study.md#reference-estimator-for-vector-tracking) has the summary table.

The registered verdict: under the study's realistic synthetic conditions the classical per-frame fit plus exact Hamiltonian inversion beats the learned tracker by the registered margins on both sets, and on eleven of the twelve stress cells of each set. The learned tracker as trained loses 96 to 100 % of sequences in every cell. Its limits stay part of the result: everything is synthetic; the classical estimator still loses 44 to 69 % of sequences; on clean spectra the two estimators split, and the classical estimator's clean-cell angular error changed from 31° to 71° between the two sets.

For an earlier comparison correction, read
[engineering decision 1: a broken tracking baseline](engineering-decisions.md#1-withdraw-a-comparison-after-discovering-a-broken-baseline).

## Minutes 14–17: inspect the deployed scalar model evidence

Read [the deployed model on the kit](../workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md).
The report dates its run 2026-10-14.
Follow its recipe, model contract, pass criteria and results in that order.

The report records float, INT8 CPU, VectorBlox simulator and kit outputs against synthetic test labels.
It reports bit equality between the INT8 CPU, simulator and kit outputs for the tested rows.
This supports the reported arithmetic checks on replayed synthetic inputs, not live-sensor performance.
The residual model adds a bounded correction to PID; it differs from the CPU benchmark model.

Use the report's artifact hashes and file list to trace the chain.
The [raw kit evidence](https://github.com/jasonphillip/polarfire-agent-skills/tree/53acad6/evidence/2026-10-14-deployed-fcnn) is in `polarfire-agent-skills`, a separate repository.
Do not treat that external evidence listing as raw files included in this checkout.
The saved label and prediction arrays of that run are in this checkout ([`docs/kit-run-2026-10-14/`](../workers/odmr-edge-ml/docs/kit-run-2026-10-14/)); the report's "Recompute from saved arrays" section recomputes its metrics offline against the pinned external records.

## Minutes 17–19: check the scalar repair stop decision

Read the [scalar repair decision record](../workers/odmr-edge-ml/docs/scalar_repair_cycle_2026-10.md). A bounded repair of the scalar estimators was frozen before a single read of a fresh sealed validation set. The registered rule required a repaired method to pass its prediction gate (lower error than both training constants by at least 0.5 µT at 95 % confidence, and a 90th-percentile error of at most 25 µT) under both primary synthetic conditions; none did, so the cycle stopped and the final set was never generated. This is a recorded negative result: the repair removes the realistic-condition failure of the unchanged direct models, but no repaired method beats the training constant there.
To check it yourself, run the record's offline checker on the published predictions; it recomputes the metrics, the intervals and the stop decision without inference or network access.

Optional follow-on: the [known-axis bias comparison](../workers/odmr-edge-ml/docs/scalar_bias_design_2026-10.md) is a separate, changed task (field along one known axis, classical fit only). Its record gives two NumPy-only commands that recompute the development and sealed-evaluation metrics from the saved arrays; set `CHECKOUT` to the `workers/odmr-edge-ml` folder of this checkout.

## Minutes 19–20: resolve terms and record open questions

Use the [glossary](glossary.md) for ODMR, FP32, INT8, PID, VectorBlox and V250.
Record the commit, workflow run and report date you inspected.
Keep missing evidence and pending work separate from measured failures.
