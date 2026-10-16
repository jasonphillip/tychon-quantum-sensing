# Contributing

Start with a small, reviewable change. A reproducible negative result is a useful contribution.

This repository contains software, synthetic studies, public measured-data replays, and development-kit evidence.
It does not contain a validated live NV-diamond sensing system.
Keep those evidence types separate.

## Start here

| Task | Read first |
| --- | --- |
| Reproduce saved results without training | [Evidence reproduction](docs/reproduce-evidence.md) |
| Understand the next proposed sensing study | [Next sensing study](docs/next-sensing-study.md) |
| Change the simulator | [Simulator contribution guide](workers/nv-sensor-sim/CONTRIBUTING.md) |
| Change scalar evaluation or model export | [ML contribution guide](workers/odmr-edge-ml/CONTRIBUTING.md) |
| Change vector estimation | [Vector worker](workers/odmr-vector-tracking/README.md) |
| Change FPGA software or design | [FPGA contribution guide](workers/polarfire-hybrid-control/CONTRIBUTING.md) |
| Change the dashboard | [Dashboard guide](demo/fpga-demo-dashboard/README.md) |
| Review current claims | [Reviewer guide](docs/start-here-reviewers.md) and [engineering decisions](docs/engineering-decisions.md) |

Use the [issue tracker](https://github.com/jasonphillip/tychon-quantum-sensing/issues) to find bounded tasks.
State which issue or result your change addresses.
Do not start a large dataset search, acquisition, training run, or hardware port from a documentation suggestion.

## Reproduce before changing a result

Run these commands from the repository root:

```sh
make install BENCH_PY=python3.11
make smoke
make verify-evidence KIT_EVIDENCE_DIR=/absolute/pinned-kit-checkout/evidence/2026-10-14-deployed-fcnn
```

The [reproduction guide](docs/reproduce-evidence.md) supplies the public kit source, pinned revision, setup, and output details.
Replace the example absolute path with that checkout's evidence directory.
Verification does not fetch missing evidence automatically.
Missing or corrupt inputs must fail; do not skip a bundle to obtain a pass.
The installation step can download dependencies. Saved-output verification performs no training or inference.

A successful check can reproduce a scientific FAIL.
For example, the stronger vector comparison preserved a failed 2× speed gate.
Do not replace a failed verdict with a checker-success label.

## Pull request checklist

- Describe the concrete problem and resulting behavior.
- List changed evidence claims and their supporting files, or state that claims are unchanged.
- Give the exact command, commit, environment, and result for each relevant check.
- Retain original predictions, labels, flags, manifests, failed fits, and consumed-test records.
- Keep source fixes separate from new experiments. Do not silently regenerate published evidence.
- Add a focused test when behavior changes. Documentation-only edits need link and claim checks.
- Record dependency and operating-system requirements. State any untested platform.
- Include attribution, source identifiers, hashes, units, and redistribution terms for new data.
- Do not commit credentials, private correspondence, personal identifiers, or machine-specific paths.

Report a reproduction failure with the failing command and a small sanitized output excerpt.
A missing dependency or unavailable artifact is an actionable finding.
Do not repair a metric mismatch by loosening the published tolerance.

## Rules for scientific comparisons

Agree on the task and eligibility before reading held-out measurements.
Record independent reference labels, acquisition groups, calibration access, and prior use.
Freeze the split, preprocessing, methods, metric, useful margin, and resource limits before scoring.
Optimize relevant classical baselines using development data only.
Charge every method for all labelled calibration used during selection.

Use whole acquisitions or days for confirmation when the claim concerns transfer.
Random rows from one acquisition do not establish that transfer.
Never tune against consumed tests or relabel old tests as fresh data.
Stop at the registered limit and publish the negative outcome when a gate fails.

A new method must show a useful advantage under equal information access.
A simpler classical method can be the preferred result.
Novelty requires a relevant prior-art comparison; a faster GPU or successful export does not establish it.

## Review and publication

The maintainer checks scope, evidence, tests, and licenses before merging.
An independent reviewer should recompute changed metrics from saved outputs.
Sensor specialists review the proposed measurement contract before any new sensing study starts.
These reviews have different purposes: software correctness does not prove measurement validity.

Repository maintainers handle publication checks and the normal push.
Public discussion does not authorize contacting dataset authors or operating hardware.
The [next study](docs/next-sensing-study.md) remains blocked until its explicit data and review requirements are met.
