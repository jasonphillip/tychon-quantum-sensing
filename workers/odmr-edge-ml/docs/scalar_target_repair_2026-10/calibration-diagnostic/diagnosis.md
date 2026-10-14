# Calibration coverage diagnosis

Training and validation only. No test or fresh holdout reads, conversion, or training.

The converter uses the first 1000 training rows without shuffling.

- calibration_first1000: n=1000; float output -18.743061 to 32.662941 uT.
- train: n=40000; float output -55.661160 to 62.649384 uT.
- val: n=5000; float output -55.246445 to 59.142269 uT.
- train: 8244 below and 789 above calibration output bounds (22.58%).
- val: 906 below and 161 above calibration output bounds (21.34%).

INT8 output metadata: {"dtype": "<class 'numpy.int8'>", "scale": 0.20159217715263367, "zero_point": -35, "representable_range_uT": [-18.74807247519493, 32.657932698726654]}

The calibration prefix excludes lock-bin 52, which occurs later in training and validation.
Consecutive 1000-row training block output means span -41.265 to 21.999 uT. This is strong stored-order heterogeneity.
The output tensor bounds match the calibration prefix, not full training output support.

This supports calibration coverage as the immediate range bottleneck. It does not measure a re-export improvement or establish the data generator ordering rationale.
No model changes, training, conversion, original-test reads, fresh-holdout reads, or evaluation-metric reads occurred.

Measured float outputs outside the actual INT8 representable range:
- train: 8244 below, 791 above; total 22.587%.
- val: 906 below, 162 above; total 21.360%.

Calibration lock counts: {"50": 50, "51": 950, "52": 0}.
The calibration prefix covers nearly the full 20–70 uT field-magnitude range; the missing output support is not explained by a narrow field-magnitude span.
