# Repository map

This file maps the published source and evidence. The [reviewer guide](docs/start-here-reviewers.md) gives a 20-minute reading path.

## Layout

| Path | Contents |
| --- | --- |
| [README.md](README.md) | Project scope, representative results, and entry points |
| [docs/](docs/) | Case study, engineering decisions, tutorials, and glossary |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Bounded contribution routes and acceptance checks |
| [bench/](bench/README.md) | Reproducible CPU benchmark on synthetic scalar spectra |
| [workers/nv-sensor-sim/](workers/nv-sensor-sim/) | Spectrum generation, manifests, and comparisons with measured spectra |
| [workers/odmr-edge-ml/](workers/odmr-edge-ml/) | Scalar models, dataset recipes, evaluation, and model export |
| [workers/odmr-vector-tracking/](workers/odmr-vector-tracking/) | Vector estimators and sequence evaluation |
| [workers/polarfire-hybrid-control/](workers/polarfire-hybrid-control/) | FPGA design, firmware, and board evidence |
| [demo/fpga-demo-dashboard/](demo/fpga-demo-dashboard/) | Dashboard, including a software dry-run mode |
| [orchestrator/tvw/audits/](orchestrator/tvw/audits/) | Historical reviews, dispatches, and critic outputs |
| [planning/](planning/) | Historical plans and conversation excerpts |

## Commands and saved evidence

The root [Makefile](Makefile) exposes `make install`, `make smoke`, `make verify-evidence`, and `make bench`.
Installation downloads pinned CPU packages. The smoke check imports dependencies and generates four synthetic spectra without training.
The [reproduction guide](docs/reproduce-evidence.md) lists tested platforms, Python versions, prerequisites, and exact commands.

`make verify-evidence KIT_EVIDENCE_DIR=/absolute/path/to/pinned/kit-evidence` checks the documented saved bundles without inference or training.
The guide supplies the separate public kit checkout and its pinned revision. Verification does not fetch missing evidence.
Reports go outside the checkout. A reproduced scientific FAIL is successful verification of that recorded outcome.
Missing evidence or a hash mismatch must fail; this command does not validate every historical claim.

`make bench` trains and evaluates the separate synthetic CPU benchmark. The [benchmark workflow](.github/workflows/bench.yml) runs it on Ubuntu.

The command generates `bench/results.json`; that file is absent from a clean checkout. [bench/README.md](bench/README.md) records reference results. [bench/expected.json](bench/expected.json) defines reference values and tolerances. The [workflow run logs](https://github.com/jasonphillip/tychon-quantum-sensing/actions/workflows/bench.yml) provide execution evidence for their associated commits.

The root Makefile has no `test` target. The [test workflow](.github/workflows/tests.yml) lists dependencies, working directories, and test commands by component. Component documentation describes additional requirements.

## Evidence boundaries

- [CPU benchmark](bench/README.md): synthetic test spectra and a model trained during the run. This is separate from the deployed INT8 model.
- [Deployed scalar model](workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md): synthetic labels, with CPU, simulator, and kit outputs compared. The reported NPU timing excludes the full sensing and control path.
- [Controller evidence](docs/engineering-decisions.md): replayed input on a development kit. Watchdog recovery depends on processor execution.
- [Vector tracker](workers/odmr-vector-tracking/docs/association_loss_multiseed.md): FP32 synthetic evaluation. The documented loss ablation does not demonstrate FPGA execution. The [pre-registered comparison study](workers/odmr-vector-tracking/docs/comparison_study_protocol_2026-10.md) names the classical exact-inversion estimator as the reference under its realistic synthetic conditions; the learned tracker as trained is not a usable estimator.
- [Simulator fitting](workers/nv-sensor-sim/docs/simulator_fit_results.md): an in-sample fit to measured spectra, separate from held-out estimator validation.
- [Dashboard recording](demo/fpga-demo-dashboard/README.md): software dry-run output, including its status badges.

These artifacts do not establish live-diamond sensing, measured sensor sensitivity, or field deployment. Historical plans and critic verdicts are distinct from executed results. [Engineering decisions](docs/engineering-decisions.md) records corrections and remaining limits.

The [detailed results index](docs/results-index.md) preserves experiment routes from the shorter front page.
The [next sensing study](docs/next-sensing-study.md) defines a data-eligibility and external-review gate, not a completed experiment.

## Terms and citation

Definitions: [glossary](docs/glossary.md) and [physics primer](docs/primer.md). Citation metadata: [CITATION.cff](CITATION.cff). A release archive describes its recorded version; later commits can contain additional evidence.
