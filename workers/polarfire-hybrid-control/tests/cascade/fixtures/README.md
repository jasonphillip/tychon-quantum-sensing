# tests/cascade/fixtures/

Fixtures for `tests/cascade/test_verify_bit_exact_ci.py`.

## sim mode

The `--mode=sim` (default) tests load the synthetic fixture **shared with the C++ testbench** at:

```
hls/tb/stimulus/cascade_synthetic_v1/
  manifest.json
  coarse_int8.csv
  fine_int8.csv
  expected_int8.csv
```

This is the canonical single source of truth for cross-language agreement. Do NOT duplicate it under `tests/cascade/fixtures/`.

## hil mode

The `--mode=hil` tests look for FPGA captures under `tests/cascade/fixtures/hil/<capture_name>/`. Each capture directory must contain:

| File | Description |
|---|---|
| `manifest.json` | Cascade manifest used for the capture (rounding_mode locked to silicon's actual mode after HW-05 closes) |
| `coarse_int8.csv` | Coarse model's FPGA INT8 output for the test input set |
| `fine_int8.csv` | Fine model's FPGA INT8 output |
| `fpga_int8.csv` | FPGA's composed output (silicon-side reference; must agree with numpy `compose_int8` bit-exactly) |

Captures are produced by the Track 0 debug capture path (MSS UART0 console dump or Libero SmartDebug readback over JTAG) — see `docs/cascade_serving_design.md` for the capture chain.

If `fixtures/hil/` is empty, `--mode=hil` tests skip cleanly rather than fail. This is the expected pre-Track-0 state.

## Adding a HIL capture

1. Run the FPGA test fixture against the synthetic input set used by `cascade_synthetic_v1`.
2. Capture the three INT8 streams (coarse, fine, fpga) over UART0 or SmartDebug.
3. Save as CSV under `tests/cascade/fixtures/hil/<capture_name>/`.
4. Copy the manifest used for the capture into the same directory.
5. Run `pytest tests/cascade/ --mode=hil`.
