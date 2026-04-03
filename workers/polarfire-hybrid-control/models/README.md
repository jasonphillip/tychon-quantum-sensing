# Models — VectorBlox VNNX Artifacts

This directory holds compiled `.vnnx` model binaries.

## Compilation

Compile INT8 quantized TFLite models with VectorBlox SDK v2.0.3:
```
vnnx_compile -c V250 -t <model>_integer_quant.tflite -o <model>.vnnx
```

## Constraints

- VectorBlox SDK **v2.0.3** (NOT v3.0) — must match CoreVectorBlox IP v2.0.1
- Compile with `-c V250` flag (matches the CoreVectorBlox instance)
- `.vnnx` files are not committed to git (large binaries, excluded by `.gitignore`)
