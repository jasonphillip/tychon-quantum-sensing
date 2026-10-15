# Preregistered approximation qualification

Frozen before numerical outputs: 2026-10-15.
This revision has not executed a qualification or development campaign.
The machine-readable contract is qualification_spec.json.
All methods remain classical. No FPGA work is authorized.

## What must pass

Seven fixed manufactured beliefs cover the prior, pilot scans, focused observations,
field-range edges, nuisance variation, and deterministic residual patterns.
They are algorithm checks, not evaluation cases.
Their counts follow round(lambda + z sqrt(lambda)).
No random seed or consumed dataset supplies these beliefs.

Compare:
- 16 posterior representatives and five quadrature nodes on the 101 x 5 x 3 grid.
- 32 representatives and nine nodes on the same grid.
- 32 representatives and nine nodes on a 201 x 9 x 5 grid.

Every comparison uses the same observations, calibration, parameter ranges, and dwell.
The refined discrete uniform grid changes the approximation to the same bounded uniform prior.
That prior-discretization effect counts as convergence error.

The saved checker compares low versus high quadrature, coarse versus fine grids,
and the operating low approximation directly against the fine reference.

## Fixed tolerances

| Quantity | Pass limit |
| --- | --- |
| Maximum utility difference across all 100 frequencies | 10% of the best reference utility plus 0.0025 uT^2 divided by minimum action cost |
| Regret of the candidate's selected action under reference utility | 5% of best reference utility plus the same absolute floor |
| Field posterior Wasserstein distance | 0.25 uT |
| Posterior field mean change | 0.25 uT |
| Posterior field median change | 0.5 uT |
| Largest 95% interval endpoint change | 0.5 uT |
| Posterior field variance change | Maximum of 10% of reference variance and 0.0625 uT^2 |
| Negative expected variance or negative expected gain | No value below -0.0025 uT^2 |
| Independent saved posterior probability reconstruction | Maximum absolute error 1e-7 |

The mean and distribution tolerances consume one eighth of the 2 uT internal precision target.
Median and interval tolerances allow one coarse field bin.
The variance floor equals 0.25 uT squared.
The gain floor equals 0.05 uT squared per action.
It prevents tiny numerical differences in uninformative bins from deciding qualification.

These are engineering tolerances, not confidence guarantees.
The 5% action-regret allowance is smaller than the proposed 25% acquisition benefit.
Different frequencies may pass when symmetry makes their reference utility equivalent.
Frequency-index agreement alone is therefore not a gate.

The Poisson likelihood update is exact on its finite grid.
Predictive design still uses a high-count Gaussian approximation and deterministic quadrature.
These checks qualify only the declared beliefs.
They do not prove global convergence or remove model mismatch.

## Stages and budget

Root must approve and reserve each stage before execution.
The provisional cumulative ceiling is 2400 CPU seconds and 900 numerical wall seconds.
Earlier charges remain charged; a stage never resets a budget.

| Stage | CPU ceiling | Wall ceiling |
| --- | ---: | ---: |
| Manufactured unit tests and convergence evidence | 1200 seconds | 420 seconds |
| At most eight fresh development cases | 900 seconds | 390 seconds |
| Saved-output verification, both artifacts combined | 300 seconds | 90 seconds |

Use one CPU worker, one BLAS thread, and no more than two GiB.
Root may allocate smaller limits based on remaining shared capacity.
A timeout preserves partial evidence and fails qualification.
Do not retry with higher resolution after seeing a failed comparison.

The qualification driver first runs all test_sparse*.py tests.
It writes the test result before building calibration tables.
It records grid progress, each completed design, and each completed belief.
The output remains unadjudicated until the separate verifier runs.

Every belief and every gate must pass.
A missing file, invalid value, arithmetic mismatch, failed unit test, or tolerance failure blocks development.
No automatic tuning, alternate quadrature, new belief, or new seed is permitted.

## Independent verification

qualify.py saves calibration tables, observations, joint posterior weights, expected variances,
utilities, selected actions, source hashes, and an artifact manifest.
verify_saved.py imports no estimator, forward model, or policy.
It reconstructs the posterior from saved likelihood-table values and acquired counts.
It independently computes field marginals, distribution distances, gains, regrets, and the verdict.

This verifies saved arithmetic and source provenance.
It does not independently reimplement the spin Hamiltonian.
The frozen source and unit checks cover that separate implementation boundary.

For development, the verifier recomputes errors, coverage, failure counts, percentiles,
photon totals, settling, recovery, and total modeled time from saved traces and labels.
It checks every policy/case pair and rejects missing rows.
No inference or data generation is required.

A fresh public checkout can run the saved verifier without a private accounting gate.
During the active campaign, root must run it under reserved accounting.
Passing qualification does not itself authorize development.

## Accounting adapter

TYCHON_ACTIVE_NUMERICAL_CONTEXT names the remote supervisor receipt.
The receipt binds its PID, approved gate hash, per-job held lock, central reservation ID,
central specification hash, and spark2-reservation-journal-v1 authority.
The driver also checks TYCHON_NUMERICAL_APPROVAL_SHA256 and TYCHON_NUMERICAL_RUN_ID.

The lock is per job on the numerical host.
The Spark2 reservation journal controls the shared caps and concurrency.
Do not hold the legacy global lock for the full remote job.
Do not modify the legacy accounting wrapper.
The remote supervisor enforces resources and reports actual usage centrally.

## Exact numerical command forms

Root places the pinned source copy on Spark4:
 ~/projects/tychon-sparse-screen-2026-10-15/source

Use:
 ~/miniconda3/envs/ctrain/bin/python

The following commands must be children of the registered supervisor.
Replace approval and output placeholders with the exact absolute paths from the reservation.

Qualification:
```sh
~/miniconda3/envs/ctrain/bin/python ~/projects/tychon-sparse-screen-2026-10-15/source/experiments/sparse_acquisition_screen/qualify.py --gate /ABSOLUTE/qualification-approved.json --out /ABSOLUTE/qualification-output
```

Qualification verification:
```sh
~/miniconda3/envs/ctrain/bin/python ~/projects/tychon-sparse-screen-2026-10-15/source/experiments/sparse_acquisition_screen/verify_saved.py --kind qualification --input /ABSOLUTE/qualification-output --out /ABSOLUTE/qualification-verdict.json --gate /ABSOLUTE/verification-approved.json
```

Development, only after a verified pass:
```sh
~/miniconda3/envs/ctrain/bin/python ~/projects/tychon-sparse-screen-2026-10-15/source/experiments/sparse_acquisition_screen/run_screen.py --gate /ABSOLUTE/development-approved.json --cases /ABSOLUTE/development-cases.json --out /ABSOLUTE/development-output
```

Development verification:
```sh
~/miniconda3/envs/ctrain/bin/python ~/projects/tychon-sparse-screen-2026-10-15/source/experiments/sparse_acquisition_screen/verify_saved.py --kind development --input /ABSOLUTE/development-output --out /ABSOLUTE/development-verdict.json --gate /ABSOLUTE/verification-approved.json
```

The source copy and output directory do not yet exist merely because these commands are documented.
Root supplies the remote reservation and source transfer.
No development or final evaluation runs automatically.
