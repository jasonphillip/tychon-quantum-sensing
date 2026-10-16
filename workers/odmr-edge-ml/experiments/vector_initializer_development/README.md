# Fixed P1 vector initializer development

This package is prepared only. No development execution or performance result is asserted.
Read `protocol.md` for the exact model, classical controls, noise law, budgets, and stopping rules.
The old packages remain unchanged. New numerical work requires root-approved source hashes and the current supervisor context.

Use configured absolute paths. The supervisor launches Python directly, with no child interpreter.

```sh
"$PYTHON" "$SOURCE/experiments/vector_initializer_development/run.py" --gate "$GATE" --approval-sha256 "$GATE_SHA" --out "$OUT" --phase p1_fixtures
"$PYTHON" "$SOURCE/experiments/vector_initializer_development/run.py" --gate "$GATE" --approval-sha256 "$GATE_SHA" --out "$OUT" --phase p1_development
"$PYTHON" "$SOURCE/experiments/vector_initializer_development/verify_saved.py" --gate "$GATE" --approval-sha256 "$GATE_SHA" --input "$INPUT" --out "$OUT"
```

Launch those commands only through the campaign accounting specification. Direct execution fails without the held supervisor context.
The first command runs manufactured fixtures in-process. No commands have yet run for this package.
The development package saves counts, labels, checkpoint/scaling, all predictions, flags, timings, source pins, and manifests.
The final command checks saved outputs only. Practical adoption and the tied12 comparison remain separate prerequisites.
