# Known-axis scalar bias comparison

Date: 2026-10-15. Status: **primary gate PASS; independently verified saved evidence**.

A +250 µT axial bias improved the classical estimator under the registered primary simulation conditions.
The biased fit achieved 1.072 µT MAE, versus 2.560 µT without bias and 12.821 µT for constant 45.
Independent review passed 105,875 checks with zero failures across six phases.
This is a classical measurement-design repair. It does not establish neural superiority, novelty, or reliable measured sensing.

## Scope and fixed design

The target field is uniform on [20,70] µT and always points positively along one known NV axis.
The earlier scalar task used unknown isotropic direction. Its negative result and consumed tests remain unchanged.
Do not compare these scores directly with the historical 33.575 µT result.
The target distribution, nuisance treatment, and measurement design differ.

The [registered protocol](../experiments/scalar_bias_design/PROTOCOL.md) compares zero bias with +250 µT.
Both arms share each field, thermal/MW state, gradient, and standard-normal noise vector.
Both use 100 frequency bins and equal photon budgets per bin. One fixed amplitude factor applies throughout.
No spectrum receives individual depth normalization.
A weighted least-squares fit estimates field, common center, width, contrast, baseline, and slope.
Six fixed starts and fixed bounds apply to every spectrum. No neural network is evaluated or trained.
The nominal microwave mixture approximates unknown row-specific MW and gradient values.
The fit receives no labels, exact means, noise vectors, or nuisance states.

One 32-field development batch preceded one sealed 256-field evaluation: 192 and 1,536 spectra, respectively.
No tuning, replacement evaluation, or additional batch followed the results.
Every row remains in the operational metrics. A failed fit would return the registered fallback, 45 µT.
The sealed evaluation had no failed fits.

## Evaluation results

Errors below are in µT. Intrinsic linewidth denotes FWHM. SNR uses the simulator's reference definition.

| Cell | Arm | MAE | p90 absolute error | Failure fraction |
|---|---|---:|---:|---:|
| Primary: 5 MHz, SNR 10 | Zero bias | 2.559976 | 5.411546 | 0% |
| Primary: 5 MHz, SNR 10 | +250 µT | 1.072024 | 2.255632 | 0% |
| Secondary: 7 MHz, SNR 10 | Zero bias | 4.161997 | 9.250059 | 0% |
| Secondary: 7 MHz, SNR 10 | +250 µT | 1.236212 | 2.611750 | 0% |
| Secondary: 5 MHz, SNR 3 | Zero bias | 6.934382 | 15.581341 | 0% |
| Secondary: 5 MHz, SNR 3 | +250 µT | 3.435782 | 7.258856 | 0% |
| All cells | Constant 45 | 12.820856 | 22.799966 | 0% |

The primary gate requires both paired improvement intervals below −0.5 µT.
It also requires MAE ≤2 µT, p90 ≤5 µT, and failure fraction ≤1%.
All five conditions passed. Intervals use 5,000 paired field bootstrap resamples with published indices.

| Cell | Biased minus zero: mean MAE difference [95% interval] | Biased minus constant: mean [95% interval] |
|---|---:|---:|
| Primary: 5 MHz, SNR 10 | -1.487951 [-1.792458, -1.184006] | -11.748832 [-12.590579, -10.874201] |
| Secondary: 7 MHz, SNR 10 | -2.925786 [-3.356507, -2.501378] | -11.584644 [-12.438100, -10.708706] |
| Secondary: 5 MHz, SNR 3 | -3.498601 [-4.321218, -2.710153] | -9.385074 [-10.305534, -8.420002] |

The low-SNR secondary cell misses the 2 µT MAE and 5 µT p90 thresholds.
Secondary cells cannot alter the registered primary decision.
This result does not claim success across every tested noise condition.
Full RMSE, medians, p95, maxima, and diagnostics remain in the [saved metrics](../experiments/scalar_bias_design/results/evaluation/metrics.json).

## Boundaries and timing

Boundary flags mean SciPy reported an active fit bound. Boundary rows remain in all metrics.

| Cell | Arm | Boundary fraction | Median fit latency (ms) | p95 latency (ms) |
|---|---|---:|---:|---:|
| Primary: 5 MHz, SNR 10 | Zero bias | 0.7812% | 11.907 | 17.577 |
| Primary: 5 MHz, SNR 10 | +250 µT | 0.0000% | 11.021 | 16.292 |
| Secondary: 7 MHz, SNR 10 | Zero bias | 1.1719% | 13.930 | 19.747 |
| Secondary: 7 MHz, SNR 10 | +250 µT | 0.3906% | 11.938 | 15.876 |
| Secondary: 5 MHz, SNR 3 | Zero bias | 15.6250% | 14.737 | 19.789 |
| Secondary: 5 MHz, SNR 3 | +250 µT | 7.4219% | 13.520 | 17.335 |

Per-spectrum latency includes preprocessing and all starts.
The evaluation prediction job used 20.843 CPU seconds and 20.899 wall seconds.
Scoring used 0.114 CPU seconds and 0.167 wall seconds.
These are shared-host timings, not an independent speed benchmark or portable hardware guarantee.
The receipt reports aarch64, Linux 7.0.0-1019-nvidia, Python 3.13.11, NumPy 2.4.2, and SciPy 1.17.1.
The recorded CPU model string was only aarch64.
One worker and one numerical thread ran within an 8 GiB cap.

## Calibration and temperature limits

Calibration sensitivity subtracts an assumed bias offset from saved successful estimates, without clipping or fitting again.
Failed rows would retain 45 µT.
This postprocessing approximation is less reliable at constrained-fit boundaries.
The offsets are explicit assumptions, not measured magnet specifications.

| Cell | MAE at −5 µT offset | −1 µT | 0 µT | +1 µT | +5 µT |
|---|---:|---:|---:|---:|---:|
| Primary: 5 MHz, SNR 10 | 4.991288 | 1.344799 | 1.072024 | 1.365997 | 5.008712 |
| Secondary: 7 MHz, SNR 10 | 4.957215 | 1.444239 | 1.236212 | 1.512627 | 5.042785 |
| Secondary: 5 MHz, SNR 3 | 5.539759 | 3.533428 | 3.435782 | 3.545491 | 5.631054 |

In the ideal known-axis model, the common thermal center shift cancels from the two-line splitting.
The fit still faces thermal/MW mixture variation, noise, finite sampling, and interpolation conventions.
The post-render +0.3 MHz offset is known.
Fitting a common physical center does not prove temperature robustness in hardware.

| Primary temperature range (K) | Fields | Zero-bias MAE | Biased MAE |
|---|---:|---:|---:|
| <288.15 | 78 | 2.505334 | 1.056156 |
| [288.15,293.15) | 35 | 2.863950 | 1.028125 |
| [293.15,298.15) | 57 | 2.635194 | 1.038089 |
| ≥298.15 | 86 | 2.435970 | 1.126774 |

The naive single-line thermal error scale uses 293.15 K as reference.
Its saved mean is 16.430 µT, p95 is 27.893 µT, and maximum is 32.379 µT.
This is a reference calculation, not another estimator result.

## Provenance and verification

The [Stage 1 gate](../experiments/scalar_bias_design/STAGE1_GATE.json) approves only the known-axis comparison.
Stage 1's global independent status remains FAIL.
Three strict singular-value checks failed for one unknown-direction case.
No singular-value tolerance was relaxed. The known-axis contrasts used for bias selection passed independently.
The 64 cutoff-sensitive unknown-direction groups are not precise magnitude-bound evidence.
The [Stage 1 report](scalar_information_limit_2026-10.md) retains its failures and numerical corrections.
Its original simulator-parity assertions are recorded checks, not fresh-checkout reproduction promises.
The private original parity check did not publish manufactured reference means.

| Milestone | Original study commit |
|---|---|
| Registered Stage 2 protocol | 2a70116fa96a1ce53ab42940d533936400f8f35f |
| Tested estimator and custody implementation | c5caf735aca02b09edba655f28891cef3c8d02c6 |
| Development predictions committed before truth scoring | a83d762e5b01d703c72034a292eebabcd6d3e15c |
| Evaluation source and seed-audit manifest | 9af6c2f4c564815b6427b81be0a0fa193bd63fb8 |
| Evaluation predictions committed before truth scoring | d8e1698209ff97ee411e99d4a8bec768bcb7370c |

These identify the original study history. The filtered public repository may have different publication commits.
The [frozen manifest](../experiments/scalar_bias_design/FROZEN_CODE.manifest.json) pins every frozen source byte.
Its SHA256 is 3de525b58e38f381b63a6617414060ffc0812bc0b4dc3d3bbeaec8cdd03d5b64.
The public [custody records](../experiments/scalar_bias_design/custody/) include commitment, freeze, access, revealed entropy, and retirement.
Custody is procedural separation on one user-owned host. It does not claim security from that host's owner.

The [independent report](../experiments/scalar_bias_design/evidence/stage2-verification.json) passed all six phases.
They covered hash/custody bindings, saved arrays, metrics, pairing/noise/flags, start selection, and revealed-seed/OU provenance.
Its source-history check ran against the original study checkout.
The exact full independent command is not claimed portable to the filtered public repository.
The [verifier source and report manifest](../experiments/scalar_bias_design/evidence/stage2-manifest.json) pin their unchanged bytes.
The portable public acceptance route is the saved-output checker below.

The bundles retain their original file bytes and manifest hashes.
The [accounting receipts](../experiments/scalar_bias_design/receipts/manifest.json) replace private absolute paths only.
Each receipt records its raw SHA256, changed JSON field pointers, original value hashes, and replacements.
Original command paths and the path map remain private.
Custodian and independent-review accounting are separate from these eight executor receipts.

## Recompute metrics from a fresh checkout

Use Python with NumPy installed.
SciPy, private paths, training, and inference are not required for these commands.
Set CHECKOUT and PYTHON_BIN to absolute paths on your machine.
The two expected hashes below are pinned independently of the downloaded bundle manifests.

```bash
CHECKOUT=/absolute/path/to/checkout
PYTHON_BIN=/absolute/path/to/python
"$PYTHON_BIN" "$CHECKOUT/experiments/scalar_bias_design/check_saved.py" \
  --bundle "$CHECKOUT/experiments/scalar_bias_design/results/development" \
  --expected-manifest-sha256 54dd32016d86351fe218defeb9b895782d5289c9b4f868b2dd6a8fd4454648e2
"$PYTHON_BIN" "$CHECKOUT/experiments/scalar_bias_design/check_saved.py" \
  --bundle "$CHECKOUT/experiments/scalar_bias_design/results/evaluation" \
  --expected-manifest-sha256 622b690acb502c1dc8aa38a81ed06172cc4574a17bd61fe37df5d890d57bd985
```

These checks hash every bundled artifact and recompute reported metrics and acceptance from saved arrays.
They do not regenerate spectra or rerun the estimator.
Optional regeneration of retired data is separate from metric verification. It must not start another experimental cycle.
Public-commit verification and workflow checks remain the publication coordinator's final acceptance step.
