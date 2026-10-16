# Public vector saved-output reproduction

Dated: 2026-10-15. This package does not train, generate spectra, run inference, or access hardware.
It exports exact bytes and recomputes saved P1 and baseline-challenge decisions.
Only Python standard-library, NumPy, and SciPy are required for verification.
The byte exporter uses Python standard-library only.

## Commands

Set absolute paths for `PYTHON`, `SOURCE`, `ORIGINAL`, `BUNDLE`, `CONFIG`, and `OUTPUT`.
`CONFIG` points to the unchanged `experiments/vector_direct_screen/config.json`.
Both output directories must be new and outside the entire enclosing Git checkout.
The boundary is the nearest ancestor containing a `.git` directory or worktree pointer file.
A source copy without any enclosing `.git` uses its source root as the documented fallback boundary.
Use `p1` or `challenge` for `KIND`. Use the independently recorded original manifest hash.

```sh
"$PYTHON" "$SOURCE/scripts/vector_public_saved/export_bundle.py" --input "$ORIGINAL" --out "$BUNDLE" --kind "$KIND" --config "$CONFIG" --expected-original-manifest-sha256 "$ORIGINAL_SHA"
"$PYTHON" "$SOURCE/scripts/vector_public_saved/verify_p1_saved.py" --bundle "$BUNDLE" --expected-manifest-sha256 "$PUBLIC_SHA" --config "$CONFIG" --out "$OUTPUT"
"$PYTHON" "$SOURCE/scripts/vector_public_saved/verify_challenge_saved.py" --bundle "$BUNDLE" --expected-manifest-sha256 "$PUBLIC_SHA" --config "$CONFIG" --out "$OUTPUT"
```

Choose the checker matching the bundle. Do not run Python with `-O`; assertion checks must remain enabled.
Root executes these commands under campaign accounting before publication.
A fresh public checkout needs no private approval, supervisor, original data directory, Torch, or CUDA.
The checker reads the published shards directly. It never writes reconstructed large files inside the checkout.
Exit 0 means integrity and saved decision reproduction succeeded. A false scientific continuation decision is a valid reproduced result.
No success output implies practical adoption or confirmation.

## Byte schema and provenance

`PUBLIC-MANIFEST.json` schema 1 identifies the bundle kind and binds each public checker source file.
It binds configuration bytes, original verifier identity, frozen producer commit, and original source pins.
`ORIGINAL-MANIFEST.json` retains exact original bytes and is provenance, not a complete public inventory.
Each `payloads` key is an original logical filename.
Its record contains original `sha256`, `size_bytes`, and ordered `parts` with relative `file`, `sha256`, and `size_bytes`.
The parts concatenate to the exact original compressed file bytes. No arrays or values are converted.
The exporter emits 6 MiB parts. The checker rejects any part larger than 10 MiB, wrong size, unsafe path, or hash mismatch.
The reader verifies both every part and the full logical file before NumPy reads it.

Every original artifact is included except P1's documented `checkpoint-progress.pt` omission.
All eight P1 training-count files remain included. Feature means/std and train/validation identity separation are recomputed.
Every prediction, flag, proposal diagnostic, timing repetition, and failed continuation result remains included.
Original source modules remain unchanged. The new checkers import no experiment package or private runtime.
`PORTABILITY.json` records original source hashes and the exact portability edits.

## Verification boundaries

The metric, Poisson-guard, timing-consistency, normalization, and decision arithmetic retain original tolerances.
Recorded times are recomputed into throughput ratios. The checkers do not repeat timing experiments.
Forward-model provenance binds saved fitted rates. The checkers do not regenerate those rates or labels.
The final checkpoint remains an opaque hash-checked byte artifact.
The original independent verifier inspected tensor shapes, dtype, and finiteness with Torch.
That tensor inspection is recorded provenance and is not repeated by this NumPy/SciPy public checker.
All other original numerical checks, including training normalization, remain present.
No raw manifest is sanitized or silently rewritten by this exporter.
If publication review finds sensitive text, stop and document a separate explicit projection before publication.
