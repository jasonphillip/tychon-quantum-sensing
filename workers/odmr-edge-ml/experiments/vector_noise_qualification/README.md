# P0 fresh-noise qualification

Preparation only. No data, test, inference, or training ran during implementation.
This additive package preserves both previous vector packages and their results.
It prepares exactly 64 fresh latent spectra with two Poisson replicas each.
The result is diagnostic accuracy, identifiability, and cost; it cannot select an adopter.

Read protocol.md for custody, fixed baselines, diagnostic meanings, and caps.
Root must issue fresh seed custody and approve exact source hashes before execution.
All executable entry points require the existing accounting supervisor and its held lock.

Configure absolute $PYTHON, $SOURCE, $GATE, and $OUT paths.

```sh
"$PYTHON" "$SOURCE/experiments/vector_noise_qualification/run.py" \
  --gate "$GATE" --approval-sha256 "$GATE_SHA256" --out "$OUT" --phase fixtures
```

The P0 command replaces fixtures with p0. Its gate binds the fresh certificate path/hash.
Saved-output verification uses a separate root-approved gate:

```sh
"$PYTHON" "$SOURCE/experiments/vector_noise_qualification/verify_saved.py" \
  --gate "$VERIFY_GATE" --approval-sha256 "$VERIFY_GATE_SHA256" \
  --input "$P0_OUTPUT" --out "$VERIFY_OUTPUT"
```

The verifier uses saved predictions and diagnostics, without simulation or inference.
Exact inactive accounting specifications live in the private campaign directory named by the Shared handoff.
