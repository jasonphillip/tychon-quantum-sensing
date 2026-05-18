# VectorBlox INT8 Rounding-Mode Resolution (HW-05)

This doc captures the resolution path for the placeholder
`composition.rounding_mode = "TBD_AFTER_VECTORBLOX_DOC_CHECK"` in the
`tychon_shared_data.cascade.CascadeManifest` schema. The placeholder is
rejected at validation time (`tychon_shared_data/cascade/manifest.py:139`)
specifically to force this document-lookup before bit-exact CI runs against
the FPGA path. HW-05 is on the May 1 2026 fix list as a hardware-bringup item;
it is also the forcing function for P3-11B (hierarchical INT8 cascade CI).

## Verdict (RESOLVED 2026-05-02)

**`composition.rounding_mode = "round_half_up"`** — confidence HIGH.

VectorBlox INT8 requantization rounds half toward +infinity, both for
positive and negative values. Concretely, the .5 tie at +0.5 maps to +1 and
the .5 tie at −0.5 maps to 0 (not −1).

This is the value pinned in:
- `hls/tb/stimulus/cascade_synthetic_v1/manifest.json` — fixture for `make hls-test-cascade-local` and `pytest tests/cascade/`
- `hls/tb/tb_cascade.cpp` — C++ port of `compose_int8` uses `round_half_up`
- The cross-repo manifest emitter in `~/projects/odmr-edge-ml/` MUST be updated to write `"round_half_up"` in place of `ROUNDING_MODE_TBD` (T3.3 below).

## T3.1 — Corpus phase (2026-05-02): INCONCLUSIVE

The local corpus at `~/.corpus/polarfire-control-corpus/` was searched
exhaustively across the three primary VectorBlox documents. None of them
explicitly specifies the INT8 rounding mode for accumulator-to-INT8
conversion or requantization.

Documents read with no explicit rounding-mode statement:
- HB0919 (CoreVectorBlox IP Handbook, Rev 2.0, November 2020)
- VectorBloxPG (Programmer's Guide, Rev 1, November 2020)
- DS60001646D-1 (VectorBlox Video Kit Demo Guide, Rev D, August 2021)

Adjacent evidence (insufficient on its own):
- Microchip HLS documentation lists `AP_RND_CONV` (round-to-nearest-even) among five rounding modes — but for `ap_fixpt`, not VectorBlox.
- Synthesis notes mention "1-bit tolerance for MXP hardware accumulator rounding" — consistent with any nearest-rounding scheme.

Working hypothesis at end of T3.1: **`round_half_to_even`** (banker's rounding), based on AP_RND_CONV being the documented HLS convention. This was the placeholder choice for the fixture during T3.2.

## T3.2 — SDK source confirmation (2026-05-02): RESOLVED to round_half_up

Inspected the VectorBlox SDK at `C:\Microchip\VectorBlox-SDK\`, commit
`4186f9a` (matches the follow-on deployment brief). The closed-source firmware blob
(`fw/firmware.bin`, `fw/firmware.hex`) and bit-accurate simulator
(`lib/libvbx_cnn_sim.so`) ship as compiled binaries — but the Python
companion `python/vbx/vbx/generate/vnnx_tflite.py` contains the
bit-accurate Python mirror of the FPGA path.

### Critical excerpt (vnnx_tflite.py:416-422)

```python
def MultiplyByQuantizedMultiplier(x, quantized_multiplier, shift):
    total_shift = QMULT - shift
    round = 2 ** (total_shift - 1)
    result = int(x * quantized_multiplier + round)
    result = result // (2**total_shift)
    return int(result)
```

This is the canonical TFLite requantization function name and pattern
(matches `tensorflow/lite/kernels/internal/common.h::MultiplyByQuantizedMultiplier`
verbatim). The `int(x * QM + half) // 2**shift` sequence implements
**round_half_up**:

| Input | After +0.5 | After int() (truncate-toward-zero) | After //2 | Verdict |
|---|---|---|---|---|
| 0.5 | 1.0 | 1 | (already integer) | +1 ✓ |
| −0.5 | 0.0 | 0 | (already integer) | 0 ✓ |
| −1.5 | −1.0 | −1 | (already integer) | −1 ✓ |

For larger arguments (where the +half-LSB is not 0.5 directly but
2**(shift-1)), the same arithmetic yields .5-tie-toward-+infinity behavior
across both positive and negative ranges. This is round_half_up.

### Other rounding modes also exist in the SDK — but not on the inference path

The same file also implements:
- `TfLiteRound` (line 444-446): uses `round_half_up(abs(n))` with `copysign` → **round_half_away_from_zero**.
- Lines 4647-4653: Python's built-in `round()` → **round_half_to_even** (banker's).

These are used in *separate* code paths (calibration helpers, activation-bound
calculations). The accumulator → INT8 inference path uses
`MultiplyByQuantizedMultiplier`. Confidence that this is the FPGA-side
behavior derives from the function naming (canonical TFLite reference) and
its location in the SDK's bit-accurate simulator companion.

### Where the firmware confirmation would land (not strictly needed)

The `fw/firmware.bin` blob is what actually runs on the FPGA. It is binary-
only; disassembly is the only way to confirm the Python mirror matches
firmware behavior bit-for-bit. Given that:
- the function name is the canonical TFLite reference name,
- the pattern is the canonical TFLite reference implementation,
- it lives alongside `libvbx_cnn_sim.so` in the same SDK package,

we treat the Python mirror as authoritative for HW-05 resolution. If
post-Track-0 HIL captures show `verify_bit_exact` mismatches concentrated on
.5 tie elements (indices 1, 6, 12, 13, 15 in the synthetic fixture), revisit
this conclusion.

## T3.3 — Cross-repo manifest update (open, out of this repo's scope)

In `~/projects/odmr-edge-ml/` (the training pipeline that emits
`cascade_manifest.json`):

1. Update the manifest emitter to write `"round_half_up"` in place of
   `ROUNDING_MODE_TBD`. Do NOT change
   `tychon_shared_data/cascade/manifest.py:LEGAL_ROUNDING_MODES` — it
   already enumerates the three candidates correctly.
2. Ship a new `tychon-shared-data` release with a fixture manifest using
   `"round_half_up"`.
3. In `polarfire-hybrid-control/`: bump the pin in `tests/cascade/`
   requirements (or `pyproject.toml`) to that release.
4. Re-run `make hls-test-cascade-local` and `pytest tests/cascade/ --mode=sim`
   to confirm bit-exact agreement.

This repo's fixture is already set to `"round_half_up"` and bit-exact
verification passes locally as of 2026-05-02; the cross-repo step is the
only remaining T3.3 work.

## Appendix C citation captures (P1A-9 hook)

Per user 2026-05-02 evening, Appendix C second-pass status: 21 of 25 entries
resolved. T3.1/T3.2 doc-reading captured publication metadata for the four
VectorBlox documents:

| Citation | Doc | Revision | Pub date | Source path |
|---|---|---|---|---|
| **C-19** | VectorBloxPG (Programmer's Guide) | Revision 1 | November 2020 | `~/.corpus/polarfire-control-corpus/raw/download-soc.microsemi.com/fpgaoutgoingvectorbloxvectorblox-launch-collateral-v10vectorbloxpgpdf.md` |
| **C-20** | HB0919 (CoreVectorBlox IP Handbook) | Revision 2.0 | November 2020 | `~/.corpus/polarfire-control-corpus/raw/download-soc.microsemi.com/fpgaoutgoingvectorbloxvectorblox-launch-collateral-v10microsemi-corevectorblox-i.md` |
| (related) | DS60001646D-1 (VectorBlox Video Kit Demo Guide) | Revision D | August 2021 | `~/.corpus/polarfire-control-corpus/raw/download-soc.microsemi.com/fpgaoutgoingvectorbloxds60001646d-1pdf.md` |
| (related) | VectorBlox SDK | commit 4186f9a | (Apr 2026 install) | `C:\Microchip\VectorBlox-SDK\` on Beelink |

UG0726 (PolarFire SoC Pin Descriptions) was NOT found in the corpus during
T3.1; it is referenced in the PolarFire SoC datasheet but the document
itself is not present locally. The HW-04b package-cross-mapping audit will
need to fetch UG0726 from the Microchip portal — capture its revision letter
and pub date at fetch time. That closes a separate Appendix C entry.

## Decision log

| Date | Phase | Outcome |
|---|---|---|
| 2026-05-02 | T3.1 corpus phase | INCONCLUSIVE. Working hypothesis: `round_half_to_even`. |
| 2026-05-02 | T3.2 SDK source review | RESOLVED to `round_half_up` via VectorBlox-SDK@4186f9a `vnnx_tflite.py:MultiplyByQuantizedMultiplier`. Confidence HIGH. |
| (TBD) | T3.3 cross-repo manifest update | Open — odmr-edge-ml emitter to write `round_half_up` in place of `ROUNDING_MODE_TBD`. |
