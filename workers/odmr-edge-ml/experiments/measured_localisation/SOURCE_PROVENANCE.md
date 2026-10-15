# Localisation source qualification

Prepared 2026-10-15. This is a static source review, not a numerical result.
The original archive and custody receipts are immutable. No original notebook or model was executed.
No fitted feature values, prediction values, or position-array values were inspected during this preparation.

## Exact source and feature meaning

The archive SHA256 is `b5717b233590d041fb4bd752af479df7c426e37675743ca3f9d3c93ae32f7aa4`.
Every member below starts with `Data availability update 20260220/`.

| Source member | SHA256 | Relevant source cells, zero based |
|---|---|---|
| `Fig.S4/Fig.S2c.ipynb` | `bcf583393f623f449f4fb5b9f63c46ce5798bca880ce4ac4341980a3a2f19fd3` | 1: unsorted traversal; 2–5: GHz fits; 6–7: aligned labels and saved parameters; 8: declared bounds |
| `Fig.3 and ML model and data/Fig. 3d and Fig. 3e/Fig. 3d and Fig. 3e.ipynb` | `209eb1afdcc6ff56e1edd0ad264559843da108f82786fd96926aa4f8567bd0c0` | 1: 24 feature construction; 2: commented random split; 3: paired prediction and label files |
| `Fig.S5/Fig. sample.ipynb` | `a1ca93ce3a44d36abdfb54a9c9bb44a88a079e4c56c6079038fe1bc0a370e2f8` | 1: plots three saved coordinate tables, without row indices |
| `Fig.3 and ML model and data/Fig. 3b and Fig. 3c/Fig. 3b and Fig.3c.ipynb` | `e4037f0c4e95b034a85c4941d74924364ac6b9ab6a30738c7b9a9b5d9a9c8fa4` | 1: separate-day raw folder; 2–5: GHz fits and display ordering |

These are code-cell reads. Notebook outputs and embedded images were not read or used as evidence.
The fitted frequencies use 2.77–2.97 GHz. The six parameters are amplitude, centre, width, amplitude, centre, baseline.
The feature triplet is absolute centre separation, first centre standard deviation, second centre standard deviation.
The saved eight-sensor order already includes the author's reordering. The adapter preserves it.
The new adapter multiplies all triplet values by 1000 for MHz, then applies training-only scaling after logarithms.
It reads requested rows only. It does not fit raw spectra or use held-out aggregate statistics.

## Position and session provenance

Custody reports 819 measured rows and eight source acquisition folders.
Custody reports a 14×51 grid with 714 unique coordinates and 105 additional repeated measurements.
The geometry stage must confirm these counts from position labels before any comparison.
The author saves parameter rows and filename-derived X/Y labels in the same traversal order.
However, that traversal uses unsorted `os.walk`. ZIP order does not establish its original order.
Repeated coordinates therefore cannot be assigned a unique acquisition session from labels alone.

The requested raw-position catalog lists possible sessions for each exact coordinate.
The main fitted arrays must match the Fig.S4 source arrays by byte hash before this catalog is accepted.
No model receives filenames, sample IDs, session IDs, coordinates, or paths as features.
All rows with the same coordinate stay together. The primary calibration budget counts unique coordinates.
Measurement-row counts and possible cross-partition session overlaps are reported separately.

The default draft studies spatial generalization within represented sessions.
It does not establish generalization to an independent acquisition, sensor array, target orientation, or specimen.
Root must approve that limitation before the geometry stage.
If independent acquisition is required, a connected-session partition needs separate prospective review before signal access.

## Published split and reproduction

The Fig.S5 headers contain 737 training, 57 validation, and 25 test coordinate rows.
The Fig.3d/e source contains a commented two-stage random split with random_state 42.
This code does not prove the saved tables match that split exactly.
Geometry-only qualification compares the saved coordinate multisets and reports overlap and ambiguity.
It must not manufacture unique source-row indices when coordinates repeat.

The Fig.3d/e source loads `estimated_position.npy` and `pos_test.npy` as paired saved prediction and label tables.
Scoring that pair is reproduction only. It does not run the supplied CNN or create a new confirmation result.
No source evidence establishes that this table equals the separate-day Fig.3b/c raw sweep set.
That relationship must remain unresolved unless new provenance establishes it.

## Physical comparator eligibility

The reviewed source supplies frequency fits and sensor markers used for plotting.
It does not supply a complete calibrated sensor-frame transform, target height/moment, and per-channel splitting likelihood.
The field-conversion tables in Fig.S4 do not, by themselves, establish a calibrated position inverse.
Approximating geometry from a plot would create unsupported calibration assumptions.

This bounded review supports excluding an independently calibrated physical inverse from the current software comparison.
It does not establish that no physics-based method could work.
A physical model calibrated from training labels could be a later comparison, with its own budget and validation.
If custody locates complete usable calibration, the current lane must stop until that comparator is implemented and frozen.
The planned result compares the candidate only against the registered classical regression methods.

## Safety and unresolved checks

Never load object arrays or use `allow_pickle=True`.
The four Fig.3f object arrays, six supplied HDF5 models, Fig.5 demonstration, and Fig.S8 simulation stay excluded.
Use safe float arrays and Unicode X/Y arrays only.
Stage calibration uncertainty remains unverified.
No measured-data test, training, inference, or fixture test has run in this preparation.
