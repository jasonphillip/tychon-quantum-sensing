# FCNN v2 INT8 vs Float Equivalence - 2026-06-21

## Summary

This run compares the float checkpoint for `fcnn_v2_residual_dataset_a` against the deployed INT8 TFLite artifact on the held-out `production_50k_v2_aic` test split (`n=5000`).

This is **not** a bit-exact equivalence claim. It measures the quantization gap and the deployed safety-clamped accuracy.

## Artifacts

- Script: `experiments/fcnn_v2_int8_float_equivalence.py`
- JSON result: `experiments/fcnn_v2_int8_float_equivalence_2026-06-21.json`
- Float checkpoint SHA-256: `e0c314265017a999cd57c2b0c168c2d3dc229c9edbb3c630887ffb94ff57ed0a`
- INT8 TFLite SHA-256: `e3b55da96ee633a58109007d4244304e2ad4a22853b10335fa41879e815b5371`

## Results

| Metric | Value |
|---|---:|
| Float-vs-INT8 delta MAE | 0.0346 uT |
| Float-vs-INT8 delta RMSE | 0.0452 uT |
| Float-vs-INT8 max abs delta | 0.7033 uT |
| Float-vs-INT8 p95 abs delta | 0.0872 uT |
| Float-vs-INT8 p99 abs delta | 0.1232 uT |
| INT8 output saturation fraction | 0.0012 |
| Float raw reduction vs PID | 5.03% |
| Float clamped reduction vs PID | 4.97% |
| INT8 raw reduction vs PID | 4.95% |
| INT8 clamped reduction vs PID | 4.90% |

## Command

```bash
python3 experiments/fcnn_v2_int8_float_equivalence.py
```

## Interpretation

- The dashboard/report claim should be "deployed INT8 model gives about 5% reduction on Dataset A"; the exact held-out INT8 clamped result from this run is 4.90%.
- The old "bit-exact INT8" wording should stay retired. The measured output gap is small but nonzero.
- The phase-C table value of 4.97% corresponds to the float clamped test result and is reproduced here.
