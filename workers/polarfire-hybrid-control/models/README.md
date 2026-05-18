# Models — VectorBlox VNNX Artifacts

This directory holds compiled `.vnnx` model binaries. `.vnnx` files are
gitignored (`.gitignore:18`); this README is the provenance record for
each artifact so a future session can reproduce them deterministically.

## Compilation

Compile INT8-quantized TFLite models with VectorBlox SDK v2.0.3:

```
vnnx_compile -c V250 -t <model>_integer_quant.tflite -o <model>.vnnx
```

## Constraints

- VectorBlox SDK **v2.0.3** (NOT v3.0) — must match CoreVectorBlox IP v2.0.1.
- Compile with `-c V250` flag (matches the CoreVectorBlox instance).
- `.vnnx` files are not committed to git (large binaries, excluded by `.gitignore`).

## Artifact inventory

### `fcnn_v2_residual_dataset_a.vnnx`

| Field | Value |
|---|---|
| Size | 12,832 bytes (~12.5 KB) — matches Final Report load-bearing claim |
| SHA-256 | `6c5cd21ae9d4ce9793f8bc143c2c53d564140bde3df1fda1ec08a5a1602512eb` |
| Built | 2026-05-17 (DLOG-048) |
| Source TFLite | `~/projects/odmr-edge-ml/exports/fcnn_v2_residual_dataset_a_int8.tflite` on spark1 (7,656 bytes, INT8) |
| Source ONNX | `~/projects/odmr-edge-ml/exports/fcnn_v2_residual_dataset_a.onnx` on spark1 (reference; not the build input) |

**Build commands (reproducible):**

```bash
# 1. Copy TFLite from spark1 to Beelink Windows side
scp ~/projects/odmr-edge-ml/exports/fcnn_v2_residual_dataset_a_int8.tflite \
    bee:~/fcnn_v2_residual_dataset_a_int8.tflite

# 2. Compile in Beelink WSL Ubuntu via the pre-existing VectorBlox venv
ssh bee "wsl -d Ubuntu -u jason -- bash -c '
    cp /mnt~/fcnn_v2_residual_dataset_a_int8.tflite /tmp/ &&
    source ~/vbx-env/bin/activate &&
    cd /tmp &&
    vnnx_compile -c V250 -t fcnn_v2_residual_dataset_a_int8.tflite \
                       -o fcnn_v2_residual_dataset_a.vnnx &&
    cp fcnn_v2_residual_dataset_a.vnnx /mnt~/
'"

# 3. Pull back to Spark
scp 'bee:~/fcnn_v2_residual_dataset_a.vnnx' \
    ~/projects/polarfire-hybrid-control/models/

# 4. Verify
ls -la models/fcnn_v2_residual_dataset_a.vnnx       # 12832 bytes
sha256sum models/fcnn_v2_residual_dataset_a.vnnx    # 6c5cd21a...
```

**Toolchain note.** CLAUDE.md (global Beelink & FPGA Toolchain section)
references `source /c/Microchip/VectorBlox-SDK/setup_vars.sh` for SDK
activation. In practice that script fails inside Beelink's MINGW64
because Python 3.10/3.11 is not in PATH, and inside WSL the script
errors on CRLF line endings. The working path is the pre-existing WSL
venv at `~/vbx-env/` (Python 3.10) from the original SDK install — same
SDK content, accessed via `wsl -d Ubuntu -u jason -- bash -c '...'`. The
`vnnx_compile` binary lives at `~/vbx-env/bin/vnnx_compile`
inside WSL Ubuntu. Use the WSL venv path until either (a) Python 3.10
is installed in MINGW64 or (b) setup_vars.sh is dos2unix-converted and
the WSL python path is wired through it.

## Rebuilding deterministically

1. Locate the source TFLite per the inventory above.
2. Re-run the documented build commands on Beelink WSL.
3. Verify size + SHA-256 match. Mismatches indicate one of:
   - VectorBlox SDK version drift (`pip show vbx` inside the venv —
     expect 2.0.3).
   - TFLite source file changes (compare upstream sha256 on spark1).
   - Compile-time flag changes (`vnnx_compile` defaults vary by SDK
     rev — pin to `-c V250`).

## Follow-On Hardware Handoff

For follow-on HIL bring-up, .vnnx artifacts get loaded onto the Icicle
Kit via the MSS bare-metal firmware. The firmware locates the .vnnx in
the on-board flash partition reserved for AI models (memory map TBD —
see `docs/seed_7_register_map_2026-05-04.md` and the empty `firmware/`
placeholder; per CLAUDE.md, do NOT write `firmware/main.c` until the
SmartDesign memory map is locked).
