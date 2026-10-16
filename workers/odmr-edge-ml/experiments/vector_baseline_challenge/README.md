# Vector baseline challenge

This package prepares a finite challenge to the closed P1 development comparison.
Its protocol is not an execution approval.

Read [protocol.md](protocol.md) before any run. Root owns source freeze, fresh seeds, and numerical reservations.
No earlier source, model, or consumed case may change.

Configure absolute paths for `$PYTHON`, `$SOURCE`, `$GATE`, `$OUTPUT`, and `$INPUT`.
Only the campaign supervisor may execute these entry points:

```sh
"$PYTHON" "$SOURCE/experiments/vector_baseline_challenge/run.py" --gate "$GATE" --approval-sha256 "$GATE_SHA" --out "$OUTPUT" --phase challenge_fixtures
"$PYTHON" "$SOURCE/experiments/vector_baseline_challenge/run.py" --gate "$GATE" --approval-sha256 "$GATE_SHA" --out "$OUTPUT" --phase challenge_development
"$PYTHON" "$SOURCE/experiments/vector_baseline_challenge/verify_saved.py" --gate "$GATE" --approval-sha256 "$GATE_SHA" --input "$INPUT" --out "$OUTPUT"
```

The verifier performs saved-output arithmetic without training or inference.
A completed challenge can still fail every continuation gate. Such failures remain evidence.
The benchmark supports synthetic computational conclusions only, with no hardware or practical adoption claim.
