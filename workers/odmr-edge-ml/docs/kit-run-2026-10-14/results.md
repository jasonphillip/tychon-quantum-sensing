# Deployed residual model evaluation

Rows: 512; PID-only MAE: 15.208568 uT

| Stage | Residual MAE/RMSE/p90/worst (uT) | Final-field MAE/RMSE/p90/worst (uT) | Clipped |
|---|---|---|---:|
| float | 14.456695/17.428528/29.044345/48.694453 | 14.466936/17.446331/29.044345/49.583339 | 11 |
| int8_cpu | 14.464910/17.442158/29.055860/48.951095 | 14.474249/17.456953/29.055860/49.583339 | 11 |
| simulator | 14.464910/17.442158/29.055860/48.951095 | 14.474249/17.456953/29.055860/49.583339 | 11 |
| kit | 14.464910/17.442158/29.055860/48.951095 | 14.474249/17.456953/29.055860/49.583339 | 11 |

CPU vs simulator max: 0 LSB; simulator vs kit max: 0 LSB
Float vs INT8 max: 0.703316 uT; MAE: 0.031385 uT
Kit latency: {'median_ms': 0.038, 'p90_ms': 0.038, 'max_ms': 0.069}

PASS: i_float_vs_int8: float vs INT8-CPU residual: max <= 5 uT and MAE <= 0.5 uT
PASS: ii_cpu_vs_simulator: INT8-CPU vs simulator: 0 LSB
PASS: iii_simulator_vs_kit: simulator vs kit: 0 LSB
PASS: iv_kit_final_field: kit final-field MAE <= float final-field MAE + 0.2 uT
Chain: PASS
