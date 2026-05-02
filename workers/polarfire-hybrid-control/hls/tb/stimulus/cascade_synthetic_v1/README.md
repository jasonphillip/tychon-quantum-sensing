# cascade_synthetic_v1 — synthetic fixture for tb_cascade.cpp + Python verify_bit_exact CI

A 16-element synthetic INT8 cascade fixture. Used by both `hls/tb/tb_cascade.cpp` (C++ side) and `tests/cascade/test_verify_bit_exact_ci.py` (Python side) so the two implementations agree against the same canonical input/output pairs.

## Files

- `coarse_int8.csv` — 16 INT8 values; the simulated `coarse_int8` output of an imaginary coarse model on synthetic input.
- `fine_int8.csv` — 16 INT8 values; the simulated `fine_int8` residual output of an imaginary fine model.
- `expected_int8.csv` — 16 INT8 values; the expected `composite_int8` after running `compose_int8(coarse, fine, manifest)`.
- `manifest.json` — the cascade manifest with `composition.rounding_mode = "round_half_up"` (placeholder per `docs/vectorblox_rounding_resolution.md`).

## Composition arithmetic for this fixture

With the manifest's scales/zero_points (z_coarse=z_fine=z_comp=0; s_coarse=0.01, s_fine=0.005, s_comp=0.01):

```
accum[i] = (coarse[i] - 0) * (0.01 / 0.01)
         + (fine[i]   - 0) * (0.005 / 0.01)
       = coarse[i] + 0.5 * fine[i]
y_int8[i] = round_half_up(accum[i]) + 0    (z_comp = 0)
y_int8[i] = clip(y_int8[i], -128, 127)          (saturate_int8 = true)
```

The fixture is deliberately picked to exercise:
- Negative and positive values across most of the INT8 range
- Both positive and negative ties (e.g. -9.5, -0.5, 51.5, 98.5, -74.5, 6.5, 14.5, 35.5, 74.5) to verify `round_half_up` semantics
- Both upper and lower saturation (i=7: accum=129 → +127, i=8: accum=-129 → -128)

## Identity check (independent of the differential test)

When `fine_int8 = z_fine = 0` for all elements, `accum = coarse + 0 = coarse`, and rounding/clipping is the identity (since `coarse` is already an integer-valued INT8). So `compose_int8(coarse, [0]*16, manifest) == coarse` element-wise.

This is the strongest invariant the cascade arithmetic must hold: a residual model that predicts zero residual must not perturb the coarse output bit-for-bit.

## Why placeholder tflite_path / sha256

`cascade_ref.compose_int8` accepts injected runners via `coarse_runner=` and `fine_runner=`. When runners are passed explicitly, no `.tflite` files are touched. The smoke test injects identity callables that return the CSV-loaded INT8 arrays directly. `manifest.validate()` only checks `tflite_path` existence and `sha256` if `manifest.root is not None` — load via `CascadeManifest.from_dict(json_data, root=None)` to skip the file-system check.

## HW-05 status

Resolved 2026-05-02: VectorBlox uses **round_half_up** for INT8 requantization, per `vnnx_tflite.py:MultiplyByQuantizedMultiplier` in VectorBlox-SDK@4186f9a (the bit-accurate Python mirror of the FPGA path). See `docs/vectorblox_rounding_resolution.md`. The fixture below is computed under that mode.

## Regenerating the fixture (if SDK rounding ever changes)

1. Update `manifest.json:composition.rounding_mode` to the resolved value.
2. Recompute `expected_int8.csv` by running the numpy reference under the new mode (only the 9 tie elements may flip):

```bash
python -c "
import numpy as np, json
from tychon_shared_data.cascade.manifest import CascadeManifest
from tychon_shared_data.cascade.cascade_ref import compose_int8
with open('manifest.json') as f: m = CascadeManifest.from_dict(json.load(f))
coarse = np.loadtxt('coarse_int8.csv', delimiter=',', dtype=np.int8)
fine   = np.loadtxt('fine_int8.csv',   delimiter=',', dtype=np.int8)
out = compose_int8(coarse, m,
    coarse_runner=lambda x: coarse,
    fine_runner=lambda x: fine)
np.savetxt('expected_int8.csv', out.reshape(1, -1), fmt='%d', delimiter=',')
"
```

3. Re-run `make hls-test-cascade-local` and `pytest tests/cascade/ --mode=sim` to confirm bit-exact agreement under the resolved mode.
