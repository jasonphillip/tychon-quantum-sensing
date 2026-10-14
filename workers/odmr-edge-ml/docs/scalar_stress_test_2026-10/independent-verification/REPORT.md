# Independent saved-output verification

Status: passed. Discrepancies: 0.
Recomputed 126 model metric sets, 28 paired intervals, 42 FP32/INT8 disagreement sets, and 14 failure/support sets.
Largest numeric difference: 6.82e-13. Primary criterion: False.

| Primary cell | C INT8 MAE | Training mean MAE | Prior fit MAE |
|---|---:|---:|---:|
| clean | 11.09564959 | 13.04273196 | 10.94069173 |
| realistic_anchor | 33.57523765 | 13.04273196 | 25.09654227 |

All six checkpoints were loaded with weights_only=True for sigma metadata. Candidate file hashes were checked. No model was constructed.

Calibration validation mean MAE: {"float": 10.805220418246849, "prefix_int8": 13.833197497996858, "rank_int8": 10.823257085395163}

Raw final accesses: 0. Inference calls: 0.

Limits:
- Failure counts verify saved masks; optimizer failure causes cannot be independently established without rerunning fits.
- Input endpoint counts and measured inference timings cannot be recomputed from saved predictions.
- Calibration headline comparison uses the prior verification handoff values, without opening another result file.
