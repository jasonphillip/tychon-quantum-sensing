# FCNN v2 Clamp Oracle Ceiling - 2026-10-12

Saved rerun of the bounded additive-correction oracle. No model training is involved.

- Dataset: `production_50k`, split `val`; PID baseline MAE: 23.7500 µT.

| Clamp (µT) | Oracle MAE (µT) | Oracle reduction vs PID |
|---:|---:|---:|
| 2.25 | 21.5480 | 9.27% |
| 2.50 | 21.3101 | 10.27% |
| 5.00 | 19.0309 | 19.87% |
| 7.50 | 16.9130 | 28.79% |
| 10.00 | 14.9633 | 37.00% |
| 12.50 | 13.1731 | 44.53% |
| 15.00 | 11.5501 | 51.37% |
| 25.00 | 6.4150 | 72.99% |

- Dataset: `production_50k_v2_aic`, split `test`; PID baseline MAE: 23.5357 µT.

| Clamp (µT) | Oracle MAE (µT) | Oracle reduction vs PID |
|---:|---:|---:|
| 2.25 | 21.3346 | 9.35% |
| 2.50 | 21.0972 | 10.36% |
| 5.00 | 18.8118 | 20.07% |
| 7.50 | 16.6935 | 29.07% |
| 10.00 | 14.7510 | 37.33% |
| 12.50 | 12.9757 | 44.87% |
| 15.00 | 11.3747 | 51.67% |
| 25.00 | 6.2781 | 73.33% |

## Provenance

- First computed 2026-06-21 (about 22:49 UTC) as an inline, unsaved script in a coding-agent session.
- This file re-runs the same arithmetic from saved `experiments/clamp_oracle_ceiling.py` on 2026-10-12.
- The oracle clips the true residual to ±clamp and subtracts that bounded correction from the residual. Its MAE is `mean(abs(delta - clip(delta, -clamp, clamp)))`.
- Deployed INT8 clamped reduction: 4.9033% on the same AIC test split, from `experiments/fcnn_v2_int8_float_equivalence_2026-06-21.json`.
- Captured fraction: 4.9033/9.35 = 52.4% using the exact oracle ceiling (9.35% displayed); 4.9033/9.3 = 52.7% (displayed as "~53%") with the dashboard's 9.3 constant.
- Caveat: synthetic data, scalar residual target, not lab-validated.
