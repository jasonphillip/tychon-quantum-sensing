# Frozen drift and calibration stress

The October 17, 2026 extension tests the unchanged integer boxcar against fresh synthetic parameter groups.
The [protocol](FROZEN_PROTOCOL.md) and [config](config.json) were frozen before evaluation.
Development, validation, and final groups are disjoint. The recorded final set is now consumed.

| Final scenario | Raw boxcar | Host calibration + same boxcar | Local matched filter | Local LDA |
| --- | ---: | ---: | ---: | ---: |
| Nominal | 99.32% | 99.32% | 99.32% | 99.41% |
| Receiver drift | 80.47% | 98.34% | 98.24% | 97.95% |
| Cavity mismatch | 90.43% | 99.41% | 99.51% | 99.02% |
| Short T1 | 89.26% | 91.41% | 91.60% | 89.16% |
| Stale calibration | 87.21% | 96.00% | 97.17% | 95.12% |

Each final scenario has 1,024 shots across 32 synthetic groups.
Calibration uses 32 separate known-label shots per class per group; it excludes hidden parameters and evaluation labels.
Local matched filtering and LDA use those same calibration shots.
The complete extension contains 240 groups, 7,680 evaluation shots, and 15,360 calibration shots.
The exported pack includes all 5,120 final shots, each in raw and calibrated form. These paired views are not independent observations.

The generator assumes gain/phase drift, IQ imbalance, offsets, correlated noise, cavity mismatch, and one-way stochastic relaxation.
An excited shot can undergo one prescribed exponential transition to ground; cavity amplitude remains continuous.
This is not measurement-conditioned quantum trajectory simulation.
All ranges are benchmark assumptions, not measured device distributions.
Leakage, upward transitions, nonlinear cavity effects, preparation errors, and measured receiver transfer functions are absent.

The worst calibrated short-T1 group scored 78.13%; the worst stale-calibration group scored 65.63%.
One corrected short-T1 value saturated at −32768. It remains included in the replay and accuracy results.
See [clipping diagnostics](artifacts/frozen_v2/clipping_report.json).
Aggregate accuracy does not establish dependable performance for every group.

Host calibration is preprocessing. It is not implemented by the FPGA inference core.
The [record metadata](artifacts/frozen_v2/board_replay/records.json) identifies scenario, group, shot, and raw/calibrated mode.
Labels describe initial state; expected scores describe integer arithmetic, including misclassifications.
Machine-readable [metrics](artifacts/frozen_v2/metrics.json), [group results](artifacts/frozen_v2/group_results.json),
and [calibration fits](artifacts/frozen_v2/calibration_fits.json) preserve these distinctions.

The optional generator is CPU-based. The earlier four-case CUDA-Q check does not validate every relaxation or drift scenario.
No scientific experiment or GPU run was repeated to curate this publication package.
