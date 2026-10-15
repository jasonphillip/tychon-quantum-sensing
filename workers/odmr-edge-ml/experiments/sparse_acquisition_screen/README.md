# Sparse ODMR acquisition preparation

Status: PREPARATION ONLY. No numerical experiment or numerical test has run.

This package asks whether adaptive frequency selection saves useful time.
It compares four classical policies using the same estimator and calibration.
It does not propose a learned policy yet.

The protocol is [PROTOCOL.md](PROTOCOL.md).
The deliberately blocked registration is [registration.draft.json](registration.draft.json).
The source uses the existing scalar Hamiltonian forward model.
It never loads a consumed dataset.

## Prepared components

- A private evaluator returns photon counts only at the requested frequency.
- A fixed schedule spreads samples across the whole frequency range.
- A coarse-to-fine policy samples near estimated resonance slopes.
- A nuisance-aware Fisher policy estimates information gained per acquisition cost.
- An approximate Bayesian policy minimizes expected posterior field variance.
- Every policy uses the same discrete Poisson posterior and median estimator.
- Every episode records dwell, photon exposure, settling, decision time, estimation time, and recovery.
- A numerical driver refuses an unapproved registration.

The Bayesian design approximation needs convergence checks before it becomes a strong baseline.
A narrow internal posterior interval does not prove accuracy.
The simulator reports its interval flag separately from actual error.

## Dependencies

Python 3.10 or newer and NumPy are sufficient for this package.
The inherited forward model also uses NumPy.
Tests use the standard library unittest module.
There is no Torch, GPU, training, hardware, network, or measured-data dependency.

## Execution boundary

Root owns numerical registration and accounting.
Do not execute imports, tests, the driver, or example data generation until root registers them.
The commands and required accounting context appear in the protocol.
Syntax parsing does not execute numerical code.
