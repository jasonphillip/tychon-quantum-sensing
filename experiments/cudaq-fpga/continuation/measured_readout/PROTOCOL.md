# Frozen measured-readout protocol

The primary record is [Zenodo 10000511](https://zenodo.org/records/10000511), licensed CC-BY-4.0.
Authors identify run 76 as full single-shot time traces in `single-shot.py`, lines 459–474.
Its two acquisition channels are real and imaginary readout voltage.
The preparation coordinate contains pulse amplitudes 0 and 1.
These labels describe intended preparation, not independently measured true state.

Run 76 contains one acquisition with 1,000 shots per preparation and 781 samples per shot.
Run 77 contains a separate acquisition of already-integrated IQ points.
Its different measurement format does not establish independent compatible trace groups.
**Drift-transfer eligibility fails.** The permitted study is within-acquisition classification.
We do not treat shot blocks as independent acquisition groups.

The exact splits, methods, budgets, selection, metrics, and acceptance rules are in `protocol.json`.
No final signal values were read during source-format qualification.
Reference, calibration, validation, and final blocks use disjoint recorded shot indices.
All methods receive the same available labelled reference/calibration records.
The affine method retains the earlier formula and conditioning limits, but learns new measured coefficients.
It does not test the original synthetic coefficients unchanged.
All time samples enter 64 fixed bins. No window or dimensionality is selected from final outcomes.

The selected method is frozen from validation before final records are loaded.
Final metrics describe agreement with preparation labels.
IID uncertainty intervals are descriptive and do not establish independence or acquisition-level generalization.
We retain every error, invalid calibration, and clipped integer value.
A useful result need not demonstrate a calibration benefit.

Run registration hashes the protocol, implementation, raw input, and tests before evaluation.
The runner requires an unused output directory and refuses changed registered inputs.
The final set becomes consumed after one execution, even if acceptance fails.
The integer export preserves 64 interleaved IQ pairs and signed int64 scores.
New measured coefficients require a new FPGA build; this study performs no FPGA execution.
