# NLS baseline diagnosis and bounded repairs

Date: 2026-10-14. This is development evidence, not the registered final comparison.
The saved numerical receipt is [nls_baseline_diagnosis_2026-10.json](nls_baseline_diagnosis_2026-10.json).

## Outcome

The campaign completed: `True`.
It evaluated 120 historical field-cone sequences and 42 development-clean sequences.
No validation or final partition was opened. No comparison-root manifest was opened.
The numerical receipt records every sequence, data hashes, calibration, software hashes, and failure accounting.

## Development comparison: identical cold acquisition

Both estimators receive the same frame-zero centers from the shared detector.
The detector uses observed minima, fixed bias, calibrated constants, and manifest linewidth.
Missing detected peaks use explicitly counted bias seeds. Truth never initializes the development comparison.
Both estimators use `line_depths=None`. Source depths predate contrast augmentation and are not permitted calibration.

| Estimator | Sequences | Lost | Lock fraction | Angular p90 (deg) | RMSE (mT) | Median / p90 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E1 | 42 | 20 | 0.634301 | 22.114017 | 0.553903 | 3.6170 / 7.4624 |
| E2 | 42 | 19 | 0.652995 | 21.314282 | 0.525490 | 3.7998 / 16.2460 |

Angular p90 means the p90 of per-sequence angular p90 values.
RMSE means the mean per-sequence vector RMSE, converted from Tesla to mT.
The pooled 42-sequence table cannot be compared directly with a 14-sequence E3 run.
The matched `seed_0` subset is:

| Estimator | Sequences | Lost | Lock fraction | Angular p90 (deg) | RMSE (mT) |
| --- | ---: | ---: | ---: | ---: | ---: |
| E1 | 14 | 6 | 0.664062 | 22.582868 | 0.753586 |
| E2 | 14 | 8 | 0.631417 | 22.582868 | 0.758951 |

## Historical field-cone diagnosis

This cohort retains the published true-frame-zero initialization for both estimators.
It measures historical hold behavior. It is not an eligible cold-acquisition comparison.

| Estimator | Sequences | Lost | Lock fraction | Angular p90 (deg) | RMSE (mT) | Median / p90 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E1 | 120 | 23 | 0.923210 | 7.659563 | 0.075187 | 3.5390 / 3.6424 |
| E2 | 120 | 10 | 0.964258 | 4.061632 | 0.027703 | 3.7553 / 16.1155 |

## Diagnostic indicators

Flags are nonexclusive and appear only for lost sequences. Their counts need not sum to total losses.
`never_acquired` means no vector lock in the first 20 frames.
`exchange_swap` requires a resolved reciprocal slot assignment across a labeled collision window.
`local_minimum` is the requested residual heuristic: sequence median RMS exceeds three times its cohort/estimator median.
That heuristic does not establish an optimization cause.
`wrong_linewidth` means a half-width or double-width refit changes the lost verdict.
Those refits keep the original seeds and physical center gate fixed. Width-dependent crossing detection can still change.
They establish sensitivity, not a uniquely wrong physical linewidth. Unclassified losses remain unclassified.

Historical cohort:

| Estimator | Never acquired in first 20 | Exchange observed | Residual >3× median | Width-sensitive loss verdict | Unclassified lost | Pending width probes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E1 | 0 | 21 | 0 | 4 | 2 | 0 |
| E2 | 0 | 6 | 0 | 3 | 3 | 0 |

Development cohort:

| Estimator | Never acquired in first 20 | Exchange observed | Residual >3× median | Width-sensitive loss verdict | Unclassified lost | Pending width probes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E1 | 10 | 3 | 3 | 4 | 8 | 0 |
| E2 | 10 | 4 | 3 | 2 | 7 | 0 |

## Implemented repairs and limits

All repair flags default off. Explicit initial centers then use the unchanged published arithmetic loop.
The receipt verifies exact equality of all five output arrays on a whole historical and development sequence.
E1 scoring loads its frozen module directly from `ba640fc2b8303ef0c0dc7f6506b8152fd0635e75`.

E2 enables three starts around the closest merged pair and its exit.
Candidate fits share velocity/depth canonicalization. Spectrum residual selects the fit; numerical ties use continuity history.
This matters because exchanging a fitted center and its depth leaves the spectrum residual unchanged.
The method does not search every simultaneous crossing permutation. Equal unresolved lines remain unidentifiable.

The optional Voigt profile uses a fixed Gaussian-sigma/FWHM ratio, default 0.15. It was not selected for this campaign.
Missing linewidth can be estimated from isolated dip widths in the first ten frames.
That option requires a ten-frame calibration buffer. It fails explicitly when no isolated dip is resolved.
Both evaluated cohorts supply linewidth, so width estimation was inactive.

The crossing regression uses unequal depths and informative motion history.
Legacy fitting collapses the weak line onto the strong line; multistart recovers the final centers within 0.2 MHz.
This synthetic test establishes that bounded case, not universal identity recovery.

## Failure accounting and timing

Missing/nonfinite predictions use the last finite estimate, or bias before acquisition, for accuracy metrics.
They remain unlocked. More than ten percent missing frames makes a sequence lost.
Near-zero estimates have undefined direction and use the same explicit fallback rule.
The receipt reports missing frames, affected sequences, and valid-frame counts.

Runs used Spark2 CPU 1 with OpenBLAS, OMP, and MKL thread limits of one.
One warm-up sequence per estimator and cohort is excluded from latency samples.
E1 fits all frames and then decodes all frames. Its samples combine each frame's timed solver and decoder calls.
Initialization and remaining Python overhead are charged to frame zero. E2 uses the same end-to-end accounting convention.
These reconstructed samples are not independent streaming measurements. Do not infer a cross-estimator speed verdict from them.
Other project jobs used separate cores; the host was not exclusively reserved.

The accepted run took 1496.93 seconds wall time and 1496.44 CPU seconds.
Its cap was 2,200 CPU seconds and 2,800 wall seconds.
An earlier campaign stopped during historical scoring before development. Its partial receipt remains in the scratch handoff.
Two preliminary one-sequence dev pilots used unregistered source depths; their numerical results were discarded.
The corrected campaign reran both cohorts from the beginning with `line_depths=None`.

## Reproduction and provenance

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3 experiments/nls_failure_diagnosis.py --cpu 1 --cpu-budget 2200 --wall-budget 2800 --output docs/nls_baseline_diagnosis_2026-10.json
```

Use the same command with `--limit 1 --dev-seeds 1` for a bounded pilot and a separate output path.
Data remains ignored and uncommitted. The implementation requires only the existing NumPy, SciPy, and h5py dependencies.

| Input | HDF5 SHA256 | HDF5 MD5 |
| --- | --- | --- |
| `data/sequence_eval_fieldcone_v1` | `f271252c6bcbfaaa9f4dc1c42330ad01230ca430978591c7dff53c182bf6b814` | `b152cb6bd1b5090b54389f6404856c23` |
| `data/comparison_test_v1/dev/clean/seed_0` | `0d6383af36a0cb4a6b084fbc78705c401b2ec3c3274062e029432aac5a6e4618` | `68116b95260499a33fb427106384e68f` |
| `data/comparison_test_v1/dev/clean/seed_1` | `7b78572ea11ae06efe6835070a58b20a0496b051d664dab25b07c6ee387433ac` | `7c90c86a9c29941fdcdd6cbaa1ca0191` |
| `data/comparison_test_v1/dev/clean/seed_2` | `653f91687fca9147696e5caf6f86977ab8a6bc043a717a42a346936211b68d23` | `3da68c6124e9468c1008d664dbdde077` |

Frozen E1 source SHA256: `17dcbe0562a2d7fce0b65102b2564fc289d11e5e5293623de5d7b8d943e55106`.
Evaluated repaired NLS source SHA256: `743cd73602261e698a00fc287fe8d16a6dd5a3e01480c4bd047b85a09acc4363`.
Final NLS source SHA256 after docstring clarification: `e4684259f46d47a0d61bb631ff422bd2e192b3da401f4b641544398f69296840`.
The executable AST is unchanged. The receipt verifies reconstruction of the evaluated source from the final file.
Shared acquisition SHA256: `30c8cae77ccf301a948d3e1df58cc53240216becc7290b78f7d4b8a638690c28`.
Protocol SHA256 at evaluation: `7efaab53c2e9199c8ef71f4251c1abef80e5708cd595db1a8c525d93252deaf0`.

The initial ten new tests failed against E1. The completed focused suite contains twelve passing tests.
The orchestrating session also ran the combined suite: 307 passed, two skipped, five subtests, and one existing warning.
The orchestrating session owns commits, integration, and the later comparison gate.
