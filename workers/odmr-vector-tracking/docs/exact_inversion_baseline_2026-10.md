# Exact inversion comparator: development evidence

Date: 2026-10-14. Base revision: `ba640fc2b8303ef0c0dc7f6506b8152fd0635e75`.

E3 is implemented and tested. Development results expose substantial remaining association errors.
These are synthetic development measurements, not a final comparison or a state-of-the-art claim.
No validation or final data was read. No model was trained. No hardware was accessed.

## Method and information boundary

The shared detector reads frame 0, the frequency grid, linewidth, and calibrated bias.
It uses Gaussian smoothing of 0.15 linewidth and a noise-scaled prominence threshold.
Hungarian matching assigns observed minima to the bias's exact resonance predictions.
Missing minima retain explicit bias seeds. Diagnostics count those substitutions.
The same detector is available to E1 and E2 through `tracking/acquisition.py`.

E3 fits eight independent Lorentzian centers and depths, a constant baseline, and a linear baseline.
The linewidth stays at the manifest's rendered linewidth. No truth initializes the fit.
Constant-velocity prediction carries centers between frames. The gate is six linewidths.
An analytic Jacobian avoids finite-difference optimization overhead.

For E=0, exact spin-one invariants give field magnitude and absolute axis projection.
The implementation uses the repository's D=2.871 GHz and gamma=2.8035e10 Hz/T.
BLUE reconstructs vectors for all 16 projection signs. Every accepted candidate must reproduce all eight frequencies within one linewidth.
The calibrated bias chooses the initial branch. Subsequent estimates choose the closest continuous branch.
Spectrally indistinguishable alternatives remain explicitly marked `ambiguous=True`.
Without a prior, ambiguous inversion returns candidates and no guessed vector.

Initial fitting can mispair lines despite detecting all eight minima.
A bounded development repair pairs the four lower and four upper lines by agreement of inferred magnitude.
For the best valid pairing, it enumerates 24 axis assignments and 16 sign assignments.
It checks exact forward frequencies and chooses the candidate nearest the allowed prior.
This reassociation runs after initial fitting and after a failed maintained pairing.
It preserves the common detector. It does not fit a rigid field directly to simulated spectra.
It assumes four lower and four upper observable transitions in this registered millitesla envelope.
It can still choose the wrong symmetry-related branch. Remaining failures are reported below.

`TrackState.locked` describes fit/physics consistency, not truth-based vector lock.
The evaluation computes the registered magnitude-and-angle lock independently.

## Source and supported physics

Formula source: `nvtools` 1.0.0 wheel, `nvtools/solver.py::Solver.field_from_resonances`.
Wheel SHA256: `db24e0cfe5723d73fc28aad9e66b0c1b6b6257bfaef03b3c386ebff335f0353c`.
[Upstream source](https://gitlab.rlp.net/agwidera/public/nvtools).
The adapted E=0 formulas use trace and determinant invariants for numerical stability.
The full upstream MIT notice is included in `exact_inversion_baseline.py`.

The installed environment lacks uncertainties, pint, prettytable, and colorama.
The wheel also requires NumPy>=2, beyond this repository's NumPy>=1.26 minimum.
The formulas were vendored. No base dependency was installed or upgraded, and pyproject.toml stays unchanged.
Implementation uses portable NumPy/SciPy operations; performance was measured only on Spark2 Linux.

Nonzero transverse strain E is explicitly unsupported without transverse azimuth information.
Two transitions identify magnitude but do not generally identify polar angle when E is nonzero.
A regression constructs two fields with equal eigenvalues and different polar angles at E=20 MHz.
The public inversion therefore raises ValueError for E!=0 instead of returning an unjustified angle.
Hyperfine, unknown D, temperature drift, and strong-field level crossings are outside this implementation's claim.

The current simulator calls `NVSystem.field_hamiltonian` without electric/strain arguments.
Its inspected `EGS_vec` default is zero. The selected dev manifest records 300 K and no hyperfine.
Live SimOS constants were D=2,871,000,000.0000005 Hz and |gamma|=28,034,956,331.865593 Hz/T.
E3 uses the required repository constants, including their small gamma rounding difference.

## Dated test-spec correction: 2026-10-14

The requested 3 mT, 70-degree example does not produce a first-order error above 10 microtesla.
Independent spin-one diagonalization gives a magnitude error of **1.0070403048357754 microtesla**.
Its projection error is **0.34442806939459675 microtesla**.
The 70-degree regression retains those facts and requires exact inversion within 1 microtesla.
An additional 85-degree regression gives **40.110867008355186 microtesla** first-order magnitude error.
Exact inversion remains within 1 microtesla there.
The orchestrating Codex session approved this explicit correction before the green run.
The original >10-microtesla-at-70-degrees assertion was not satisfied or represented as passed.
This correction does not change registered comparison margins.

## Tests

The first focused run failed collection because `tracking/acquisition.py` did not exist.
Implementation followed that recorded failure. The final focused run passed **17 tests** in 0.89 seconds.

Coverage includes 1,000 random fields from 0.1 to 3 mT against an independent eigenvalue oracle.
Magnitude error must be below 1 microtesla; absolute-cosine error must be below 1e-4.
Additional tests cover sign ambiguity, prior selection, nonzero-E nonidentifiability, endpoint fields,
invalid frequencies, detector fallback diagnostics, invalid frames, fitting without true centers,
the analytic Jacobian, and recovery of scrambled axis assignments.

The root session owns the combined repository suite after Tasks 4 and 5 finish.

## Development measurement

Only `data/comparison_test_v1/dev/clean/seed_0` was evaluated: 14 sequences, 256 frames each.
The per-seed manifest supplies linewidth and bias. Truth is read only after each sequence's inference.
Missing estimates use the previous finite estimate, or bias before acquisition, for numerical errors.
Missing frames count as unlocked. A sequence with >10% missing frames counts as lost.
The existing `fieldcone_metrics_row` supplies ordinary numerical metrics.
The script applies registered missing-frame accounting explicitly instead of dropping failed frames.

| Development implementation | Mean lock fraction | p90 of sequence angular p90 | Mean sequence RMSE | Lost sequences | Missing frames |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial nearest-bias assignment | 40.4018% | 77.7135 degrees | 1.819619 mT | 10/14 | 1,337/3,584 |
| After physical reassociation | **76.3393%** | **30.6524 degrees** | **0.785721 mT** | **5/14** | **56/3,584** |

Seven sequences contain missing frames after repair. The worst sequence angular p90 is 68.9351 degrees.
Several sequences achieve sub-0.001-degree p90, while association failures dominate the aggregate.
This is evidence of a useful inverse and an incomplete tracker, not reliable recovery across this dev cell.
Tuning stopped after this one bounded reassociation repair. Both receipts are retained.

One full sequence warmed the estimator before timing all 3,584 scored calls.
Direct end-to-end `step` latency: **4.424048 ms median; 6.759523 ms p90**.
Acquisition and reassociation are included. CPU affinity was 0; thread limits were all 1.
Repaired evaluation used 20.7493 CPU seconds and 20.7504 wall seconds.
The initial evaluation used 17.8045 CPU seconds; the 16-frame pilot used 0.0653 seconds.
No cross-estimator speed verdict follows from these separate development runs.
Host: Spark2, Linux aarch64, Python3.13.11, NumPy2.4.2, SciPy1.17.1, h5py3.14.0, Torch2.11.0+cu130.

Data SHA256: `0d6383af36a0cb4a6b084fbc78705c401b2ec3c3274062e029432aac5a6e4618`.
Per-seed manifest SHA256: `503aeb8225619baa456f4a3a9eb374674b1a468a247448f466ac1e2eaf61d87f`.
The manifest's original generator hash predates augmentation; the HDF5 hash above identifies evaluated bytes.

## Reproduction on the measurement host

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -m pytest tests/test_exact_inversion_baseline.py -q
PYTHONPATH=src python3 experiments/evaluate_exact_inversion_dev.py --data data/comparison_test_v1/dev/clean/seed_0 --out <path> --cpu 0
```

The evaluation deliberately refuses other cells and val/final paths.
Further scoring must follow the registered protocol and its separate selection/final gates.
