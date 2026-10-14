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

## Minutes 12–14: check comparison status

**Comparison status (2026-10-14): PENDING.** The planned study files are absent from the source snapshot, commit `a9640736dc6e`.
There is no result from that study to inspect here.
The CPU benchmark's baseline comparisons and earlier case-study results are separate experiments.

For an existing comparison correction, read
[engineering decision 1: a broken tracking baseline](engineering-decisions.md#1-withdraw-a-comparison-after-discovering-a-broken-baseline).
Its corrected synthetic comparison does not complete the pending study.

## Minutes 14–19: inspect the deployed scalar model evidence

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

## Minutes 19–20: resolve terms and record open questions

Use the [glossary](glossary.md) for ODMR, FP32, INT8, PID, VectorBlox and V250.
Record the commit, workflow run and report date you inspected.
Keep missing evidence and pending work separate from measured failures.
