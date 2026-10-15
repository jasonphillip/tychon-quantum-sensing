# Independent saved-validation verification

Completed at 2026-10-15 15:42:08 UTC, from the execution report.

Result: PASS for output verification. The scientific continuation decision is STOP.
The independently recomputed selections are `robust_prior_fit` and `joint_fit__int8`.
Neither selected method passes both primary conditions. No other repaired candidate passes that conjunction.
The frozen rule therefore does not authorize Freeze 2 or final-data generation.

Verification covers 3,584 retained rows across seven conditions and 168 method/condition summaries.
It checks 22 failure/support/ambiguity summaries per condition and accepted-only error summaries.
It also checks raw FP32/INT8 disagreement for every policy and checkpoint.
It independently recomputes 104 primary paired bootstrap contrasts, using 10,000 registered group draws each.
The bootstrap uses draw-frequency matrix weights, independently implemented outside the evaluator.
The verifier imports no evaluator code and performs no inference.
It opens only saved prediction/label/flag arrays and reporting metadata.
It checks their hashes, cross-condition identities, row retention, fallback predictions, and selection decisions.
The execution passed 8,949 checks with no retry, 0.299577 CPU-seconds, and 0.316409 wall-seconds.
Peak process memory was 52,187,136 bytes. Standard error was empty.

## Scope and metric interpretation

- Recorded pipeline timing supplies tie-breaks. Timing is checked for completeness but is not remeasured.
- Ties use a strict difference below 0.1 microtesla, followed by fallback fraction, latency, and lexical name.
- Neural family errors average checkpoint losses per row; they do not average predictions.
- `all_seeds_reliable` combines 95% coverage and each checkpoint prediction gate. It is not a coverage-only field.
- Common hard-invalid and ambiguity flags are saved inputs. Their input-level derivation cannot be checked without spectra.
- Raw-support flags, fallback masks, accepted-only metrics, and complete-row metrics are independently checked.
- Secondary-condition error and flag summaries are checked. Their bootstrap intervals and per-seed gates are outside scope.
- Quantization input/endpoint counts cannot be recovered from magnitude prediction arrays and are outside scope.
- Conditional likelihood intervals remain uncalibrated. The verifier does not open or assess those arrays.
- Custody still owns label provenance, source-to-payload binding, and Freeze 1 membership.

The original source and frozen artifacts remain untouched.
The only numerical write outside this report folder was the required shared compute-ledger append.
No validation rerun, final generation, retired-test access, training, or calibration occurred.
No tuning is proposed after the result.

## Files

- `verify_saved_validation.py`: independent verifier, definition commit `c6229d52279af38792023de48ec0747d93d720bb`.
- `validation-verification.json`: full checks and recomputed primary comparisons.
- `compute-receipt-compact.json`: short compute receipt and report/verifier hashes.
- `validation-verification.stdout.jsonl`: verifier output and full wrapper receipt.
- `validation-verification.stderr.txt`: empty standard-error log.
- `executed-command.txt`: exact wrapped command already executed with the shared lock and both ledgers.

Do not rerun that command automatically. Its report path refuses overwrite.
