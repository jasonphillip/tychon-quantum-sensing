# Independent Stage 1 verification

Date: 2026-10-15.

Global result: **FAIL**. The original singular-value criterion failed at three rows. No criterion was relaxed.

The second attempt completed all 12,960 rows at 432 grid points. It recomputed 11,880 regular rows using SciPy LAPACK gesvd. The production calculation used NumPy SVD. No experiment module or forward model was imported.

All rank, target-null, finite-bound, photon, mask, key, and saved-zero checks passed. The largest relative bound difference was 1.23024e-7. All 5,908 comparable noise checks and 5,940 full-rank nuisance checks passed.

The three failures are Cartesian unknown-direction rows for one point: B20 µT, cos(theta)=0, phi=pi/4, bias0, width7 MHz, historical normalization, SNR10. Each cutoff fails singular-value agreement at rtol=2e-9 and atol=1e-14. Rank and target-null decisions still agree. The 1e-8 cutoff is unidentifiable; 1e-10 and 1e-12 produce bounds near 171 million µT. These are not useful quantitative sensing claims.

No discrepancy affects the known-axis fixed, center or shape rows. These checks support that limited diagnostic scope. They do not convert the whole-grid result to PASS.

## Known-axis primary cell

Fixed-amplitude normalization, width5 MHz, SNR10. Each value is a local standard-deviation bound in µT. Direction is known. All three cutoffs (1e-8, 1e-10, 1e-12) agree for every entry below.

| Field µT | Bias µT | Fixed nuisance | Center unknown | Shape unknown |
|---:|---:|---:|---:|---:|
| 20 | 0 | 3.071440 | 3.096635 | 7.060057 |
| 20 | 250 | 1.426096 | 1.426102 | 1.430605 |
| 20 | 500 | 1.447197 | 1.447204 | 1.447401 |
| 20 | 1000 | 1.449384 | 1.449408 | 1.449413 |
| 45 | 0 | 1.623560 | 1.628941 | 2.673582 |
| 45 | 250 | 1.432078 | 1.432083 | 1.435214 |
| 45 | 500 | 1.447706 | 1.447713 | 1.447865 |
| 45 | 1000 | 1.449518 | 1.449543 | 1.449549 |
| 70 | 0 | 1.338785 | 1.339356 | 1.594111 |
| 70 | 250 | 1.436313 | 1.436317 | 1.438531 |
| 70 | 500 | 1.447984 | 1.447992 | 1.448114 |
| 70 | 1000 | 1.449424 | 1.449450 | 1.449457 |

## Cutoff sensitivity

Of 3,960 regular groups, 64 change rank and identifiability across the three cutoffs. All 64 use unknown direction and zero bias. There are 16 groups for each coordinate/normalization combination: spherical/historical, Cartesian/historical, spherical/fixed-amplitude, Cartesian/fixed-amplitude. No group has two finite bounds differing by more than 2%; unstable groups switch between null and finite results.

The saved grid has 1,080 unavailable rows and 64 target-null rows. All counts matched independently. The masks contain 108 theta-branch, 108 bz-branch, and 864 polar-coordinate-singularity entries. The verifier checked 6,048 symmetry-column predicates and 936 exact-zero columns.

## Provenance and limits

All five grid artifacts remained byte-identical across the two verification attempts. The current forward, information, runner and configuration source hashes match the grid summary. The original registration and approved public derivative are bound through the recorded mapping.

Derivative metadata passed internal consistency checks. Original perturbation spectra are absent, so the verifier did not recompute derivatives. Forward-model physics and source parity experiments were not repeated. A local Cramer-Rao bound does not bound arbitrary estimator MAE.

The first attempt stopped at the singular-value criterion and lost the original assertion location. The sole retry retained all discrepancies and source locations. Both failed attempts remain preserved.

Both guarded attempts used 1.111392 CPU seconds and 1.137257 wall seconds. Peak memory was 124555264 bytes. Both used the shared lock, both earlier ledgers, the information ledger and stage guard.

Metadata-only diagnosis read JSON, CSV and NPY headers or exact saved values. It performed no matrix decomposition, forward evaluation, new spectrum generation or inference. No further numerical run occurred.

Machine-readable evidence: public-independent-stage1-verification.json.
