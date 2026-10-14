# Development-only mechanism diagnostic

Date: 2026-10-14.

All 16 rows retain paired sample seeds, true fields, and frequency grids.
All three frozen C_direct FP32 models are scored. No training or seed selection occurs.

| Variant | Seed 42 MAE | Seed 20261014 MAE | Seed 20261015 MAE | Mean seed MAE |
|---|---:|---:|---:|---:|
| Clean reference | 11.152374 | 11.195566 | 11.852797 | 11.400246 |
| A_original_original_lock | 37.754142 | 49.684472 | 25.872975 | 37.770530 |
| B_original_clean_lock | 59.667946 | 56.633834 | 48.792439 | 55.031406 |
| C_detrended_recomputed_lock | 11.784235 | 17.732474 | 14.810110 | 14.775606 |
| D_detrended_clean_lock | 15.397673 | 17.021050 | 12.382676 | 14.933800 |

All errors are in microtesla. Means average seed errors, not predictions.

Variant A reproduces saved outputs within 0.000001 microtesla.
Exact comparison details, detector distributions, support violations, and hashes are in results.json.

B and D use matched clean locks. C and D subtract the known injected slope.
These oracle interventions diagnose mechanisms. They do not demonstrate a deployable improvement.
Noise, linewidth broadening, and frequency offset remain. Only four fixed variants were evaluated.

No validation/final raw data or predictions were opened. The evaluator remains unchanged.
