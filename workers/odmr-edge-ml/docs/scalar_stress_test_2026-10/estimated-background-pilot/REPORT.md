# Estimated background pilot

Date: 2026-10-14.

Method fixed before execution: OLS using bins 0-19 and 80-99.
Subtract only the estimated slope. Recompute the unchanged PID detector and lock.
Score all three frozen C_direct FP32 models. No training or tuning occurs.

| Seed | MAE in microtesla |
|---|---:|
| 42 | 11.553202 |
| 20261014 | 17.653901 |
| 20261015 | 14.800582 |
| Mean seed error | 14.669228 |

Saved comparison MAEs: original 37.770530; known-slope correction 14.775606; clean 11.400246 microtesla.

All original outputs reproduced exactly. Sample pairing and source hashes passed.
Slope errors, PID errors, lock distribution, support counts, and provenance are in results.json.
Only 16 development rows were used. This does not establish held-out improvement or justify adoption.
The previous diagnostic remains unchanged. No further method or mask was tested.
