# Models — VectorBlox VNNX Artifacts

This directory holds compiled `.vnnx` model binaries from Repo 2 (tychon-odmr-ml).

## Transfer Protocol
1. Repo 2 exports INT8 quantized TFLite models
2. On Beelink, compile with VectorBlox SDK v2.0.3:
   ```
   vnnx_compile -c V250 -t <model>_integer_quant.tflite -o <model>.vnnx
   ```
3. Copy compiled `.vnnx` to `~/projects/tychon-shared-data/models/` (shared filesystem)
4. On Spark or Beelink, copy from shared data into this directory as needed

## Critical Constraints
- VectorBlox SDK **v2.0.3** (NOT v3.0) — must match CoreVectorBlox IP v2.0.1
- Compile with `-c V250` flag (V250 preset matches the CoreVectorBlox instance)
- Do NOT commit `.vnnx` files to git — they are large binaries excluded by `.gitignore`
- Bit-accuracy verification (TFLite vs VNNX simulator, max abs error ≤1 bit) runs in Repo 2
