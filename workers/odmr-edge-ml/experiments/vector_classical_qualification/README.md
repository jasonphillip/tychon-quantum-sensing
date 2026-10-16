# Classical chunk qualification and fresh-population draft

Status: preparation only. No new job, test, data generation, or training has run.

This additive package imports the frozen eight-line Hamiltonian and solver.
It exposes only the outer chunk size: 256, 1024, or 4096 spectra.
It never modifies the frozen configuration or earlier results.

`matrix.json` declares 15 sequential GPU jobs, at most 300 GPU/wall seconds total.
`protocol.md` separates timing qualification from future accuracy and practical adoption.
`test_contracts.py` contains manufactured tests prepared for a registered CPU fixture job.
`qualify_chunks.py` requires the original source pins, additive source pins, a root approval, and a held supervisor lock.

Configure absolute paths for `$PYTHON`, `$SOURCE`, `$GATE`, and `$OUT`.
The supervisor must supply the reservation context. Direct unsupervised use fails closed.

```sh
"$PYTHON" "$SOURCE/experiments/vector_classical_qualification/qualify_chunks.py" \
  --gate "$GATE" --approval-sha256 "$GATE_SHA256" --out "$OUT" \
  --phase fixtures --variant affine --dtype float64 --chunk 256
```

One GPU condition uses the same command with `--phase chunk_profile`, its approved dtype, variant, and chunk.
The root-owned accounting adapter launches each command. Inert private draft specifications are listed in the Shared handoff.

The current residual guard is a goodness-of-fit test. It does not guarantee field accuracy.
The original repeated affine fixtures had 100% acceptance and no fallback, despite large post-hoc field errors.
No neural model is implemented or proposed for training by this package.
