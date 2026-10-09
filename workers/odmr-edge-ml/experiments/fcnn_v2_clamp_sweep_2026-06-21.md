# FCNN v2 Clamp Sweep - 2026-06-21

Quick post-clamp/output-scale sweep only. No retraining, re-quantization, or VNNX rebuild was performed.

- Dataset: `~/projects/tychon-shared-data/production_50k_v2_aic`, split `test`, n=5000
- Base clamp: ±2.2500 uT
- TFLite: `~/projects/odmr-edge-ml/exports/fcnn_v2_residual_dataset_a_int8.tflite`

| Increase | Clamp (uT) | INT8 MAE (uT) | INT8 reduction vs PID | INT8 raw > clamp | Float reduction vs PID |
|---:|---:|---:|---:|---:|---:|
| +0% | 2.2500 | 22.3817 | 4.9033% | 7.38% | 4.9697% |
| +5% | 2.3625 | 22.3752 | 4.9310% | 4.64% | 5.0000% |
| +10% | 2.4750 | 22.3714 | 4.9471% | 1.64% | 5.0191% |
| +15% | 2.5875 | 22.3706 | 4.9505% | 0.40% | 5.0238% |
| +20% | 2.7000 | 22.3703 | 4.9517% | 0.24% | 5.0250% |
| +25% | 2.8125 | 22.3701 | 4.9526% | 0.20% | 5.0259% |

Unclamped reference:
- INT8 raw/unclamped MAE `22.3700 uT`, reduction `4.9529%`.
- Float raw/unclamped MAE `22.3526 uT`, reduction `5.0270%`.

Interpretation: changing only the output clamp by up to +25% has negligible effect because the deployed model was trained/exported around the original ±2.25 uT target and raw deployed outputs only slightly exceed that clamp.
