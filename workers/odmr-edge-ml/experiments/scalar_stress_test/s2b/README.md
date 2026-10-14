# Prior-aware scalar baseline and four-pair applicability gate

Date: 2026-10-14. This is an isolated development artifact, not a repository modification.
The original four-pair S2b is **not applicable** to the scalar production recipe.
The delivered replacement uses a declared magnitude-and-direction prior with existing scalar projection estimators.
It is prior-based inference, not an exact field-magnitude measurement or a four-axis reconstruction.

## Why the four-pair proposal was stopped

The verified scalar recipe calls `generate_dataset` without `multi_axis_mode`.
That option defaults to false. The stochastic branch calls the single-axis `corrupt_spectrum`.
That function averages microwave-drive strength across spatial bins, not crystal orientations.
`SimOSAdapter.generate_odmr_spectrum` builds one spin-only NV system and one Hamiltonian.
It finds transitions from one ms=0 state and sums the two allowed Lorentzians.
The four-orientation loop exists only in the separate `generate_multi_axis_spectrum` path.
Spherical field sampling changes field direction relative to one axis; it does not create four measured axes.
An eight-line fit would add six unsupported lines and cannot be called a valid four-pair comparator here.

Source chain, inspected on Spark2:

- Scalar `scripts/make_production_50k_v2_aic.py:166–176`: generation call without the multi-axis option.
- Simulator `pipelines/batch_generate.py:344`: `multi_axis_mode=False` default.
- Same file `230–243`: spherical field sampled, then single-axis corruption.
- Simulator `physics/lineshape.py:138–155,199–256`: power-gradient averaging and the single-axis corruption path.
- Simulator `adapters/simos_adapter.py:250–288,325–332`: one NV Hamiltonian, two transitions, Lorentzian sum.
- Simulator `physics/lineshape.py:310–336`: separate four-orientation loop.

Existing vector acquisition also requires a calibrated bias and supplied linewidth.
Neither may be borrowed from hidden scalar nuisance values.
No vector validation/final data or source modifications were used.

## Fixed replacement rule

Assume magnitude `B ~ Uniform(20,70)` microtesla and isotropic direction.
Then `|cos(theta)| ~ Uniform(0,1)` independently of B.
For an ideal measured axial magnitude `z=|B cos(theta)|`, the likelihood density is `1/B` when `0<=z<=B`.
The posterior therefore has density proportional to `1/B` over `[a,70]`, where `a=max(20,z)`.
Its CDF is `log(B/a)/log(70/a)`; the absolute-error-optimal median is `sqrt(70*a)`.
At z=70 the posterior collapses to the endpoint and the estimate is 70.

Both implemented arms apply the same fixed transformation:

1. `two_line`: reuse `experiments/scalar_fit_baseline.py::fit_field_magnitude` unchanged.
2. `pid`: reuse `DerivativeZeroCrossingPID` unchanged.

These estimate z from the observed spectrum. Their errors are not included in the ideal posterior model.
The transformation is therefore a plug-in baseline, not a calibrated uncertainty estimate.
It may fail under changed magnitude/direction priors, unresolved lines, thermal shifts, or instrument offsets.
It does not prove the scalar spectrum uniquely identifies full magnitude.

The two-line arm retains its existing gamma=2.8035e10 Hz/T and optimizer bounds.
The PID retains gamma=2.8024e10 Hz/T. No constants or source files were changed.
No true field, true centers, true nuisance values, or row labels enter the API.
No model training or parameter selection occurred.

## Interface and failure accounting

```python
from prior_aware_scalar import fit_batch
result = fit_batch(spectra, frequencies_hz, scalar_repo=absolute_repo_path,
                   backend="two_line", lower_uT=20., upper_uT=70.)
```

Use `backend="pid"` for the second arm. The explicit defaults constitute the declared prior.
The function returns arrays `raw_projection_uT`, `magnitude_uT`, `failed`, `out_of_support`, and `latency_seconds`.
It also returns per-row diagnostic dictionaries and the prior specification.
Finite raw z outside [0,70] is clipped to this support and counted in `out_of_support`.
Fit failures, flat spectra, and nonfinite spectra return NaN with `failed=True`.
The wrapper never substitutes a fallback silently.
The root evaluator applies its frozen original-training-mean fallback and retains all rows in accuracy statistics.
Coverage and support violations must accompany every results table.

The existing two-line fitter may converge to a poor local solution without reporting optimizer failure.
The wrapper does not invent a truth-based rejection threshold or claim statistical identifiability from convergence.
No speed or accuracy acceptance threshold was chosen from the pilot.

## Tests and one bounded training-only pilot

Fourteen tests passed in 0.33 seconds on Spark2.
Numerical integration verifies normalization, the posterior median, and absolute-error optimality.
Manufactured valid two-line spectra verify projection recovery and the fixed transformation.
Other tests cover endpoint behavior, invalid priors, support flags, and explicit missing estimates.

The only production data read was original `train/spectra[0:16]` and `train/frequencies`.
No labels, original test rows, scalar consumed holdout, or vector val/final data was read.
Both arms had 0/16 failures and 0/16 out-of-support projections in that timing pilot.
No accuracy was calculated.

| Arm | Median per row | p90 per row | Observed-mean estimate for 2,688 rows |
| --- | ---: | ---: | ---: |
| Prior on two-line fit | 0.769 ms | 1.065 ms | 2.130 seconds |
| Prior on PID | 0.0121 ms | 0.0170 ms | 0.0355 seconds |

These are rough estimates from 16 training rows, not upper bounds for narrow or noisy stress cells.
CPU library thread limits were 2. No warm-up rows were excluded.
Lazy source loading was outside per-row timing; total pilot wall time including setup was 0.286 seconds.
The reused fitter caps each call at 200 optimizer evaluations.
The root should apply a campaign wall-time cap before fresh stress scoring.

Train-spectra SHA256: `d86a34c3e0ef1c6bd1c40f30f158297243feebce337cdc7d48c83cd6e0f0222f`.
Frequency-array SHA256: `0199f4e0bfe0560a04dfd50fe65536c40a3fdf7ed65576171d63f680223dab19`.
See `pilot_train_only.json` for every raw prediction, failure flag, timing, and implementation hash.

## Physically appropriate exact-inverse scope

A calibrated single-axis spin-one Hamiltonian can recover magnitude from its two exact transition frequencies when D and frequency calibration are known.
The existing E3 `invert_axis` already provides this E=0 primitive; duplicating it is unnecessary.
However, unknown temperature changes D, and an unknown instrument offset changes both observed centers.
Two measured centers do not generally identify field magnitude, polar angle, and a free common offset together.
An unconstrained two-Lorentzian fit supplies no additional independent field observable through free fitted depths.
Claims based on the detailed dipole amplitudes would require a separately calibrated amplitude/polarization model and an identifiability study.
No such calibrated single-axis full-Hamiltonian estimator was implemented or represented as solved here.

## Reproduction

Set `S2B_WORK`, `SCALAR_REPO`, `PRODUCTION_DATA`, and `PYTHON_BIN` to absolute local paths.
The implementation and tests use portable Python/NumPy/SciPy; the recorded execution was on Spark2 Linux.

```sh
SCALAR_REPO="$SCALAR_REPO" PYTHONPATH="$S2B_WORK" OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 "$PYTHON_BIN" -m pytest "$S2B_WORK/test_prior_aware_scalar.py" -q
"$PYTHON_BIN" "$S2B_WORK/pilot_train_only.py" --dataset "$PRODUCTION_DATA" --scalar-repo "$SCALAR_REPO" --out "$S2B_WORK/pilot_train_only.json"
```

The pilot command was executed once. It has no split-selection option and opens only original training spectra.
The root owns stress pre-registration, freezing, fallback application, and future scoring.
