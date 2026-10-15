# Scalar information diagnostic, 2026-10-15

This is a conditional simulator diagnostic. It is not a new scalar evaluation campaign. Stage 2 remains closed pending independent review.

## Model and assumptions

The target is the magnitude of the original field before adding a known z bias. This is one NV orientation. The renderer uses a signed spin-1 Hamiltonian and squared Sx transition dipoles. It omits dipoles at or below 1e-6, matching the original simulator.

The constants are D = 2.871 GHz, electron gamma = -1.76085963023e11 rad/s/T, and the SimOS NV multiplier 1.000357. Temperature contributes -74.2 kHz/K relative to 300 K. The frequency grid contains 100 points from 2.82 to 2.92 GHz.

The intrinsic linewidth parameter is FWHM. Each spatial component has HWHM equal to half that FWHM multiplied by sqrt(1 + saturation). Ten microwave components are averaged before noise. They are not ten independent photon observations.

Historical normalization fixes the largest sampled dip depth to the requested contrast. The alternative uses one global amplitude factor, 0.9957299574916568. Its reference is B = 45 µT along z, bias = 1000 µT, FWHM = 5 MHz, temperature = 293.15 K, microwave scale = 1, and gradient = 0.196875. The reference is evaluated before interpolation. Every point reuses the same factor.

A 0.3 MHz interpolation offset shifts the rendered spectrum, with fixed endpoint values outside the band. A dimensionless slope of 0.02 adds a linear background across the band. These are renderer conventions.

The conditional noise is independent Gaussian noise with mean mu and variance mu/P in each bin. P = (reference SNR / (0.30 × 0.015))². When contrast is an unknown parameter, the photon budget remains fixed.

Temperature, microwave scale, and gradient remain fixed. Unknown post-interpolation center does not exactly marginalize the original random thermal process. Temperature changes the Hamiltonian before sampling. This diagnostic does not integrate the original correlated temperature and microwave nuisance distribution.

## Nuisance and rank checks

The four nuisance ladders are: all nuisance values known; unknown post-interpolation center; unknown center, FWHM, contrast, and background slope; and unknown direction plus those four quantities.

Unknown direction has spherical and Cartesian diagnostics. A spherical polar singularity makes that spherical bound unavailable. Cartesian coordinates provide a local check. Local estimability at an axial pole does not prove global identification with unknown direction.

Derivatives use scaled coordinates and relative steps 1e-4, 3e-5, and 1e-5. The convergence tolerance is 2%, with the original denominator floor of 1e-8. A required branch change makes that bound unavailable. Unused angular derivatives do not invalidate a known-direction ladder.

For Gaussian variance mu/P, the information weight is P/mu + 1/(2 mu²). SVD uses relative rank cutoffs 1e-8, 1e-10, and 1e-12. A target component in a discarded singular direction gets no finite bound. An unavailable derivative does not get a pseudoinverse result.

A local standard-deviation bound concerns local unbiased estimation. It is not an MAE bound for all estimators. Priors, finite ranges, bias, and global ambiguity matter. No neural advantage or reliable sensing result follows from this calculation alone.

## Preserved checks and correction history

The self-contained NumPy renderer matched the unchanged original simulator in 12 manufactured cases. The largest absolute difference was 7.99e-15. Analytic two-Lorentzian derivatives passed at three step sizes, with maximum relative error 1.23e-8.

Both preflights retain failed status. They stopped at the original simulator's hard dipole threshold. The first attempt did not save its partial derivative diagnostics. One logging-only retry preserved them. Neither preflight was repeated after that retry.

An append-only clarification allowed per-parameter validity reporting before the first grid. It changed no renderer formula, step, or rank cutoff. The previously unreached mathematical checks then passed once. They covered nuisance and noise monotonicity, independent-repeat additivity, null-target handling, the high-photon limit, and the projection-only prior integral.

The first grid stopped after 169 of 432 points and saved 5,070 rows. At B = 45 µT, cos(theta) = 0, azimuth = pi/4, zero bias, FWHM = 1.5 MHz, and historical normalization, theta's convergence diagnostic was 0.0288978066. It exceeded 0.02 without a detected branch change.

The exact theta derivative is zero at that point. The antiunitary transformation Rx(pi)K reverses Bz while preserving Hamiltonian energies, the ms0 projector, and squared Sx dipoles. At zero bias and theta = pi/2, theta+h and theta-h therefore give identical spectra. This is a numerical zero-derivative diagnostic problem, not a sensing failure.

The reviewer recorded a second append-only correction before permitting one changed-approach grid retry. Only exact symmetry-zero derivatives may replace numerical derivatives. Raw finite-difference errors remain saved. Branch flags still make affected bounds unavailable. All nonzero derivatives, steps, cutoffs, measurement budgets, and forward formulas remain unchanged.

## Analytic prior reference

For B uniform on [20, 70] µT and isotropic direction, let q = |Bz|. Conditional on B, q is uniform on [0, B]. The posterior density is proportional to 1/B on [max(20, q), 70]. Its median is sqrt(70 × max(20, q)).

The projection-only Bayes MAE is [b²/6 + a²/2 - (2/3) a sqrt(ab)] / (b - a), with a = 20 and b = 70. This equals (305 - 4 sqrt(1400)) / 15 = 10.355580301936156 µT. Numerical quadrature gave 10.355580301936154 µT.

The optimal prior-only constant is 45 µT. Its MAE is 12.5 µT and its RMSE is 14.433756729740645 µT. The projection-only oracle is a reduced-model reference. It is not a bound for the full Hamiltonian, which can retain transverse-field information.

## Public evidence

Code, registration, source hashes, failure receipts, and matrices are under [the experiment directory](../experiments/scalar_information_limit/README.md). The saved-output checker recomputes bounds from published means and scaled Jacobians. It generates no spectra and uses no private simulator source.

The original parity check used a pinned simulator checkout whose adapter differs from the public adapter. Reference means were not saved for those 12 cases. Its passing assertion is recorded evidence, not a parity command that a fresh public checkout can reproduce.

No consumed evaluation spectra or retired seeds were read. There was no retraining, GPU use, paid compute, measured-data ingestion, hardware purchase, or NV diamond connection. Every numerical operation used the original shared lock and both earlier ledgers. The wrapper's 'validation' label is only an accounting label for this new diagnostic.

## Completed grid and conditional examples

The corrected grid completed all 432 registered points and 12,960 rows. It retained 1,080 unavailable bounds and 64 target-null rows. Both the stopped grid and corrected grid passed saved-output recomputation. The corrected-grid maximum relative bound difference was 1.56e-15.

The new exact spin-matrix symmetry test passed with maximum operator residual 1.23e-15. The forward renderer, nonzero derivatives, steps, and rank cutoffs did not change. The first saved-output checker timed out because it repeatedly decompressed its archive. A cache-only fix loaded arrays once. Its one retry passed all original assertions and tolerances.

These examples use B = 45 µT, intrinsic FWHM = 5 MHz, reference SNR = 10, and fixed global amplitude. Each uses the same 100-bin photon budget. Bounds are standard deviations in µT at relative SVD cutoff 1e-10. They are not observed estimator errors.

| Added z bias, µT | Known axis, all nuisance fixed | Known axis, center unknown | Known axis, center/width/contrast/slope unknown |
| --- | --- | --- | --- |
| 0 | 1.62356 | 1.62894 | 2.67358 |
| 250 | 1.43208 | 1.43208 | 1.43521 |
| 500 | 1.44771 | 1.44771 | 1.44786 |
| 1000 | 1.44952 | 1.44954 | 1.44955 |

For unknown direction, consider cos(theta) = 0.5 and azimuth = pi/4. Cartesian direction plus unknown center/width/contrast/slope gives these local diagnostics:

| Added z bias, µT | Local standard-deviation bound, µT | Retained condition number |
| --- | --- | --- |
| 0 | 79,090.27 | 394,031.62 |
| 250 | 15,454.87 | 51,578.23 |
| 500 | 15,262.92 | 50,879.48 |
| 1000 | 15,607.64 | 96,246.47 |

These four rows retain rank seven across all three registered cutoffs. Their very weak local information does not establish a universal error floor. Fixed temperature and the interpolation renderer remain material assumptions.

Implementation recommendation, pending the coordinator's independent gate: consider a small known-axis biased scalar comparison under a new frozen protocol. That is a changed task. This study does not justify claims about arbitrary-direction magnitude recovery, neural advantage, or physical sensing performance. No next-stage data has been generated.

## Accounting and reproducibility

The compute receipt includes every failed and successful operation, including the checker timeout. The numerical lock and both earlier ledgers remained active. The original stage cap is 900 CPU seconds and 900 cumulative wall seconds; study and shared caps remain unchanged.

A fresh checkout with NumPy can recompute both saved grids without inference:

    python3 experiments/scalar_information_limit/check_saved.py \
      --directory experiments/scalar_information_limit/results/stage1-symmetry-retry

    python3 experiments/scalar_information_limit/check_saved.py \
      --directory experiments/scalar_information_limit/results/stage1

During this bounded study, run numerical verification through the same accounting wrapper. The recorded CPU, wall, and memory totals are in the [compute receipt](../experiments/scalar_information_limit/evidence/compute-receipt.json).
