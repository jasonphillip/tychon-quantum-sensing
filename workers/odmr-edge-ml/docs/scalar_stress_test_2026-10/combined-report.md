# Scalar calibration repair and stress test

Completed 2026-10-14. Scope: single-NV-orientation synthetic spectra, frozen models, CPU evaluation.

The calibration repair recovered the residual model's lost INT8 accuracy on its original validation data.
The fresh stress test failed its declared success criterion.
The direct model beat a constant estimate on clean spectra, but did not establish an advantage over the prior-aware fit.
Under the combined stress condition, it performed worse than both comparisons.

**Calibration repair**

Three frozen residual models received new INT8 exports. Calibration used 1,000 training rows per model, spread across its output range.
The models were not retrained. Validation average error fell from **13.833 to 10.823 µT**, close to the float result of **10.805 µT**.
All three seeds improved. Mean float-to-INT8 disagreement fell from 5.824 to 0.509 µT.
Output endpoint occupancy fell from 21.573% to 0.033%; occupancy alone is not proof of clipping.
These validation rows previously selected the checkpoints. This result diagnoses the export repair; it is not a fresh generalization result.

**Fresh stress results**

Each cell contains the same 256 fresh field samples under a different condition.
The seven cells contain 1,792 scored spectra, not 1,792 independent fields.
Model columns average the errors of three fixed seeds. They do not average predictions or select a winning seed.
All values below are full-field magnitude mean absolute errors in µT. Lower values are better.

| Condition | Direct float | Direct INT8 | Repaired residual INT8 | Constant | Prior-aware fit |
|---|---:|---:|---:|---:|---:|
| clean | 11.000 | 11.096 | 11.358 | 13.043 | 10.941 |
| realistic_anchor | 38.469 | 33.575 | 824.786 | 13.043 | 25.097 |
| wide_lines | 14.763 | 14.797 | 833.717 | 13.043 | 24.984 |
| low_snr | 38.355 | 31.847 | 650.352 | 13.043 | 24.002 |
| negative_slope | 28.306 | 25.703 | 777.236 | 13.043 | 25.014 |
| negative_offset | 34.941 | 31.820 | 827.919 | 13.043 | 24.871 |
| higher_contrast | 25.891 | 24.767 | 826.429 | 13.043 | 25.020 |

The constant always predicts the original training mean, 45.064 µT.
The prior-aware fit converts a fitted axial projection using the declared field-magnitude and direction distributions.

On clean spectra, direct INT8 improved on the constant by 1.947 µT.
The paired 95% interval for direct minus constant was [-2.729, -1.156] µT.
Against the prior-aware fit, its difference was +0.155 µT, with interval [-0.036, +0.343] µT.
That comparison establishes no clear advantage for the network.

In `realistic_anchor`, direct INT8 was worse than the constant by 20.533 µT, with interval [18.501, 22.609] µT.
It was worse than the prior-aware fit by 8.479 µT, with interval [5.202, 11.789] µT.
The float model also failed, scoring 38.469 µT. The export cannot explain this failure by itself.

The declared criterion required a clear direct-INT8 advantage over both baselines in both primary cells.
It failed in clean against the prior-aware fit, and in `realistic_anchor` against both baselines.
Secondary cells cannot reverse that decision.

**Observed failure behavior**

In `realistic_anchor`, the original peak detector produced estimates outside the 20–70 µT training range on 251 of 256 rows.
Its median estimate was 865.059 µT. The true magnitudes remained within 20–70 µT.
The residual estimator adds its learned correction to that detector output. Its mean error reached 824.786 µT.
The detector also supplies the spatial anchor used by the direct model.
The inspected PID source selects the two deepest local minima without first fitting the background.
The saved outputs establish incorrect detector estimates; the development-only diagnostic below separates two contributing mechanisms.

The prior-aware fit also degraded. Its raw projections exceeded its allowed support on 246 of 256 primary stress rows.
The fit wrapper recorded zero failures. That status did not establish a physically plausible estimate.

**Development diagnosis and repair candidate**

Four exploratory interventions used the same 16 development rows and three frozen float models.
Original inputs scored 37.771 µT. Substituting clean peak anchors alone scored 55.031 µT.
Subtracting the known injected slope and recomputing anchors scored 14.776 µT.
Combining slope subtraction with clean anchors scored 14.934 µT. The saved clean reference scored 11.400 µT.
The original condition reproduced the saved model outputs exactly.
These interventions identify background distortion as a major contributor within this development batch.
The clean-anchor and known-slope inputs are oracle information and cannot establish a deployable gain.

A separate pilot estimated the background from the input spectrum itself.
It fitted a line to the first 20 and last 20 frequency samples, then subtracted its slope.
The method and sample mask were fixed before that pilot ran. No alternate masks or thresholds were tried.
This correction scored **14.669 µT**, compared with the saved original **37.771 µT**, without retraining.
Known injected slope entered diagnostic scoring only; it did not enter the correction.
The unchanged peak detector still scored 103.448 µT and exceeded projection support on 15 of 16 rows.

The implementable correction is a concrete candidate for the next experiment.
Only 16 reused development rows support it. Its benefit needs fresh validation and final data across all stress cells.
It has not been tested here with INT8, the prior-aware fit, nonlinear backgrounds, or shifted resonance windows.
The next bounded study should compare background correction for both learned and classical estimators before deciding on longer training.

**Comparator scope correction**

The production scalar recipe generates one NV orientation. The source follows one NVSystem and two transitions.
The separate four-orientation renderer is not selected by that recipe.
A comparator requiring four resonance pairs would use a different measurement problem.

The implemented comparator uses the existing two-line fit and a declared prior.
For an exactly observed axial projection z, its conditional median is `sqrt(70 * max(20, clip(abs(z), 0, 70)))` µT.
This formula assumes isotropic directions and uniform field magnitude on [20,70] µT.
A noisy fitted projection does not satisfy the ideal observation assumption.
It is an applicable prior-dependent comparison, not an exact inverse for unknown direction and nuisance parameters.
Its 14 tests passed, including numerical posterior integration and manufactured spectra.

**Test conditions and limits**

The clean cell uses intrinsic linewidth 1.5 MHz, contrast 0.030, no added shot noise, zero slope, and zero offset.
The primary stress cell uses intrinsic linewidth 5 MHz, contrast 0.015, reference SNR 10, slope +0.02, and offset +0.3 MHz.
Secondary cells change one of those primary stress settings, as specified in the fixed protocol.
The SNR reference is 0.30 times contrast; it is a convention, not a measured faintest-line depth.
These are prescribed synthetic stress conditions. The label `realistic_anchor` does not establish measured laboratory realism.

The generator deliberately changed the P1 distribution to obtain each intrinsic linewidth.
Power broadening remained active. Final rendered component widths were 1.550–1.600, 5.168–5.333, and 7.236–7.466 MHz.
The unchanged 100-point, 100 MHz sweep triggered 2,560 narrow-line sampling warnings in the clean render.
Those warnings are preserved in the manifest. The study does not establish performance with a finer frequency grid.

Bootstrap intervals use 10,000 paired row draws and condition on the chosen simulator, nuisance trajectories, and three frozen models.
They do not include simulator uncertainty, new nuisance trajectories, or training-seed population uncertainty.
No hardware, controller-stability, or state-of-the-art result follows.

**Verification and handoff**

The candidate identities, evaluator, comparator, tests, generator, protocol, and data manifests were frozen before final scoring.
The freeze hash was sent to the coordinating session before final payload access.
The final campaign completed once, from 2026-10-14T22:37:13.434821+00:00 to 2026-10-14T22:37:15.977455+00:00.
Repeated final scoring is refused by an exclusive access receipt and an existing output directory.
The final data are consumed. Subsequent verification reads saved predictions, not the final spectra.

The evaluator passed 12 synthetic guard tests after review repairs.
Independent recomputation checked 1,326 numerical comparisons, including 126 metric sets and 28 paired intervals.
It found zero discrepancies; the maximum numerical difference was 6.82e-13.
Candidate, prediction, freeze, and summary hashes matched.
The calibration headlines also recomputed from saved validation predictions.
A separate check confirmed 59 development-diagnostic values and both saved prediction hashes.
Measured timings and input endpoint counts were not independently reconstructed.

The exact hashes and source locations remain in the attached JSON receipts and evidence archive.
Experiment execution took 3.688 seconds for the final scoring phase; this excludes setup and review.
CPU timings are batch measurements and do not establish FPGA or per-request latency.

Next work should follow the development diagnosis, then use fresh validation and final data for any changed estimator.
The coordinating session owns source integration, publication, and the separate vector comparison.
