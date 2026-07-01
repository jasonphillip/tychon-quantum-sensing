# FCNN v2 Authority Sweep - 2026-06-21

Quick post-clamp/output-authority sweep only. No retraining, re-quantization, or VNNX rebuild was performed.

- Dataset: `~/projects/tychon-shared-data/production_50k_v2_aic`, split `test`, n=5000
- Assumed deployment range: `50.0 uT`

| Authority | Clamp (uT) | INT8 MAE (uT) | INT8 reduction vs PID | INT8 raw > clamp | Float reduction vs PID |
|---:|---:|---:|---:|---:|---:|
| 4.5% | 2.2500 | 22.3817 | 4.9033% | 7.38% | 4.9697% |
| 5.0% | 2.5000 | 22.3710 | 4.9485% | 1.02% | 5.0214% |
| 10.0% | 5.0000 | 22.3700 | 4.9529% | 0.00% | 5.0270% |
| 15.0% | 7.5000 | 22.3700 | 4.9529% | 0.00% | 5.0270% |
| 20.0% | 10.0000 | 22.3700 | 4.9529% | 0.00% | 5.0270% |
| 25.0% | 12.5000 | 22.3700 | 4.9529% | 0.00% | 5.0270% |

Unclamped INT8 reference: MAE `22.3700 uT`, reduction `4.9529%`.

Interpretation: widening the post-clamp to 25% authority does not move the current deployed model beyond its raw/unclamped result. A larger public accuracy claim needs retraining/output-scale changes, not just a wider runtime clamp.
