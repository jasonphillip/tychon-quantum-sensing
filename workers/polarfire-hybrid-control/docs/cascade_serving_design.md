# Cascade Serving Design — P3-11B (Tier 1, single-slot sequential)

This doc locks the Phase II forcing path for the hierarchical INT8 cascade (P3-11B in the May 1 2026 fix list). Two .vnnx accelerators (coarse + fine residual) are served sequentially through a single CoreVectorBlox slot, with composition arithmetic done in MSS firmware (or a software harness pre-firmware) and a single composite `u_AI` value fed to the existing `nv_pid_top` axi_target. The on-FPGA safety pipeline (sector clamp + slew limiter + bumpless transfer + watchdog) remains bit-equivalent and untouched.

## Why Tier 1 (single-slot sequential), not Tier 2 (two-slot canvas)

| Dimension | Tier 1 — sequential, single slot | Tier 2 — two-slot canvas |
|---|---|---|
| HDL changes | None (`nv_pid_top` and the existing CoreVectorBlox instantiation are reused) | New CoreAXI4Interconnect (1 master + 2 AXI4-Lite slaves), promoted observability wires, new netlist |
| P&R cost | Zero re-runs forced. r6_s25 closure preserved. | Full P&R + new dated closure subdir. r6_s25 closure remains canonical baseline; new closure costs one budget cycle. |
| BRAM cost | One model resident; reload between coarse and fine. ~2× weight load latency per inference. | Both models resident in separate slots. Lowest latency, highest BRAM. |
| Firmware complexity | MSS firmware orchestrates: load coarse weights → invoke → store INT8 output → load fine weights → invoke → compose → write composite to `nv_pid_top` axi_target. | Firmware writes both inputs and reads both outputs in parallel; composition still required. |
| Validation surface | Existing testbench surface + new `tb_cascade.cpp` covers composition + safety pipeline. | Adds netlist-level verification (write-then-readback proof per the existing two-slot canvas runbook). |
| Phase II evidence value | Strongest near-term: closes P3-11B with bit-exact CI vs. silicon (post-HIL). | Architecturally cleaner, but heavier. Deferred to Phase II+1. |

User confirmed Tier 1 only. The existing testbench-validated runbook at `docs/smartdesign_two_slot_canvas_runbook.md` stays in-repo as the design reference for the eventual netlist refresh; no commits in this Phase II promote it.

## Data-flow contract

Composition is upstream of the safety pipeline. The existing `nv_pid_top` (`hls/src/nv_pid.cpp`) takes a single scalar `u_AI_in` of type `out_t` (`hls::ap_fixpt<32, 16>`, Q16.16) and applies sector clamp, slew limit, bumpless transfer, and watchdog cooldown downstream. No HDL change is required.

```
   ┌──────────────────────┐                        ┌──────────────────────────────┐
   │  CoreVectorBlox slot │                        │       MSS firmware           │
   │  (single instance)   │                        │  (or pre-firmware harness)   │
   │                      │                        │                              │
   │  load coarse.vnnx ──►│  → coarse_int8 (1×N) ──┤                              │
   │  invoke              │                        │  compose_int8(coarse, fine,  │
   │  load fine.vnnx ────►│  → fine_int8   (1×N) ──┤    manifest) → composite_int8│
   │  invoke              │                        │                              │
   └──────────────────────┘                        │  composite_int8 → out_t      │
                                                   │    via output_quant.scale ×  │
                                                   │    (composite_int8 - z_comp) │
                                                   │                              │
                                                   │  AXI write @ 0x4000_0xxx     │
                                                   │    (nv_pid_top.u_AI_in port) │
                                                   └──────────┬───────────────────┘
                                                              │
                                                              ▼
                                              ┌────────────────────────────┐
                                              │  nv_pid_top (existing HLS) │
                                              │  - sector clamp ±4.5%      │
                                              │  - slew limiter 0.001 V/cyc│
                                              │  - bumpless transfer       │
                                              │  - watchdog (1 ms, 200 MHz)│
                                              │  → actuator_out (Q16.16)   │
                                              └────────────────────────────┘
```

The `compose_int8` arithmetic is the canonical form from `tychon_shared_data.cascade.cascade_ref:compose_int8`:

```
accum = (coarse_int8 - z_coarse) * (s_coarse / s_comp)
      + (fine_int8   - z_fine)   * (s_fine   / s_comp)
y_int8 = round_per_manifest(accum) + z_comp
if composition.saturate_int8:
    y_int8 = clip(y_int8, -128, 127)
```

`round_per_manifest` is one of `round_half_to_even`, `round_half_up`, or `round_half_away_from_zero`. The PolarFire VectorBlox FPGA path's actual rounding mode is the forcing function for HW-05 (Track 3 in the Phase II plan); resolution feeds the `manifest.composition.rounding_mode` field. Pre-resolution, CI runs against a synthetic manifest that pins the rounding mode to a chosen default (see `tests/cascade/fixtures/`).

The composite-to-`out_t` conversion (in firmware) is:

```
u_AI_q16_16 = (composite_int8 - z_comp) * s_comp   # float-equivalent
            // rounded to Q16.16 quantum 2^-16
```

The Q16.16 representation is what the existing `nv_pid_top.u_AI_in` simple-wire input expects.

## Safety pipeline invariant

The cascade composition happens **upstream** of all safety mechanisms. Concretely:

- The sector clamp (`hls/src/safety_clamps.cpp::apply_sector_clamp_gated`) bounds the actuator output to ±OUTER_SECTOR_CLAMP_FRACTION (4.5%) of the actuator range, regardless of how `u_AI_in` was computed. A composition that misbehaves (e.g. fine model emits out-of-distribution residuals) cannot exceed this bound.
- The slew limiter (`apply_slew_limit`) bounds per-cycle changes by `MAX_SLEW_PER_CYCLE` (0.001 V/cycle).
- Bumpless transfer (`NVPID::bumpless_transfer` in `nv_pid.hpp`) absorbs any current `u_AI_old` into the integrator on watchdog trip, so a stuck/slow cascade evaluation simply triggers timeout and graceful PID-only operation.
- The watchdog (`watchdog.cpp::watchdog_check`) timeouts at 200,000 cycles (1 ms) without a fresh AI heartbeat. Sequential cascade serving roughly doubles inference latency vs. single-model — this must remain comfortably under 1 ms.

The Lur'e/Circle-Criterion sector-bounded NN claim in `docs/safety_architecture.md` is unaffected: it argues the AI output is sector-bounded, and `u_AI_in` is exactly that output regardless of how many models contributed to it.

## Test scaffolding

### C++ side (`hls/tb/tb_cascade.cpp` + `hls/tb/stimulus/cascade_synthetic_v1/`)

The new testbench injects a synthetic INT8 pair and verifies:

1. **Composition arithmetic match** — C++ port of `compose_int8` produces the same output as the numpy reference for the same input pair + manifest.
2. **Identity check** — when `fine_int8 = z_fine` (all-zero residual at the fine model's zero-point), the composed output equals the coarse-only path bit-exactly. This proves the residual head is non-disruptive when it predicts zero.
3. **Safety pipeline survival** — feeding the composite into `nv_pid_top` still passes the existing sector-clamp accept/reject, slew-limit, bumpless-transfer, and watchdog-cooldown tests.

The existing `tb_bumpless.cpp` is not modified — preserving the r6_s25-equivalent test surface so `make verify-strict` continues to gate on the canonical baseline.

Build target: `make hls-test-cascade-local`, mirroring `hls-test-local`. Both wire into `verify-local` and `verify-strict`.

### Python CI scaffold (`tests/cascade/`)

`tests/cascade/test_verify_bit_exact_ci.py` imports the canonical reference:

```python
from tychon_shared_data.cascade import compose_int8, verify_bit_exact, CascadeManifest
```

Two pytest modes via a `--mode={sim,hil}` flag:

- **`--mode=sim`** (default, available immediately): asserts bit-exact equality between the numpy `compose_int8` output and the JSON-dumped C++ `tb_cascade` output for the synthetic fixture. Pre-Track-0, this is the only mode that runs green; it proves software/numerical agreement but not silicon agreement.
- **`--mode=hil`** (post-Track-0): asserts bit-exact equality between numpy `compose_int8` and an FPGA capture (UART0 console dump or SmartDebug readback) for the same input set. This is the strongest possible Phase II evidence — closes the loop from numpy reference → C++ testbench → FPGA silicon with bit-exact equality.

Pin `tychon-shared-data` to whatever release replaces the `ROUNDING_MODE_TBD` placeholder (Track 3 dependency). Pre-resolution, the synthetic fixture in `tests/cascade/fixtures/` carries an explicit rounding mode chosen for the placeholder run; post-resolution, the manifest fixture is regenerated.

## JTAG-side debug capture path

The FPGA needs to emit its INT8 output (composite-into-clamps, post-clamp, integrator state, etc.) over a debug interface so `verify_bit_exact` in `--mode=hil` has something to compare against. Phase I produced no `.job`/`.stp`/`.bit` artifacts, so we are starting from scratch. Three options, ranked by integration cost:

### Primary — MSS UART0 console (post-HW-03)

Firmware reads `pid_csr_block` taps over AXI4-Lite (slot 1 at `0x4001_0040`..`0x4001_005C` per the existing CSR map), formats as ASCII (`hex` for compactness), and prints over MSS UART0. Bandwidth ~115200 baud is tiny relative to a 200 MHz fabric clock, so high-rate activity capture is impossible — but exact for fixed-input-set `verify_bit_exact` comparisons:

1. Host pushes a known input set (N samples of `coarse_int8`, `fine_int8`) over the same UART (or via a pre-flashed firmware blob).
2. Firmware loops: write composite → read post-clamp output → emit on UART.
3. Host parses the ASCII stream into an `np.int8` array and runs `verify_bit_exact`.

Requires HW-03 (CP210x driver) for console visibility. Lowest-friction once HW-03 closes.

### Secondary — Libero SmartDebug (immediate after HW-04)

SmartDebug is Libero's GUI/Tcl tool that does live readback of any AXI register over JTAG. No firmware required. Available immediately after JTAG enumerates (HW-04 closure) — does not depend on HW-03.

Use case: register-state inspection during host-driven test sequences. Drive `pid_csr_block` writes from a host script that talks to FPExpress/SmartDebug over the JTAG transport, read back state per-register, dump to file, run `verify_bit_exact`.

Bandwidth is JTAG-clock-limited (~10-50 MHz JTAG TCK on FlashPro6). Adequate for fixed-input-set verification.

### Deferred — Signal-tap / on-chip ELA

Captures live signals into BRAM and dumps via JTAG. Highest fidelity, but consumes BRAM resources, may reroute critical paths in P&R, and re-triggers a full P&R cycle if added late. Document only — not added unless Primary + Secondary prove insufficient.

## Files added by Track 1

| File | Rationale |
|---|---|
| `hls/tb/tb_cascade.cpp` | Cascade testbench: synthetic INT8 pair + composition arithmetic + identity check + safety pipeline survival |
| `hls/tb/stimulus/cascade_synthetic_v1/` | Synthetic INT8 input + expected composed output + manifest fixture |
| `Makefile` (target `hls-test-cascade-local`) | Build target + wire into `verify-local`/`verify-strict` |
| `tests/cascade/test_verify_bit_exact_ci.py` | Python CI scaffold (`--mode=sim` + `--mode=hil`) |
| `tests/cascade/fixtures/` | Synthetic INT8 pair + reference manifest for pytest |
| `firmware/cascade_compose.c` (stub) | MSS-side composition layer — body deferred until SmartDesign memory map is locked per CLAUDE.md "Do NOT" |

## Open dependency on Track 3 (HW-05)

The numpy `compose_int8` reference rounds per `manifest.composition.rounding_mode`, which is one of three legal values (`round_half_to_even`, `round_half_up`, `round_half_away_from_zero`). The actual VectorBlox FPGA path's rounding mode is the resolution target of HW-05 — see `docs/vectorblox_rounding_resolution.md`.

Resolved 2026-05-02 via T3.2 SDK source inspection: the synthetic fixture pins `composition.rounding_mode = "round_half_up"`. The cross-repo `tychon-shared-data` manifest emitter (in odmr-edge-ml's training pipeline) must be updated to write `"round_half_up"` in place of `ROUNDING_MODE_TBD` so the placeholder no longer reaches CI.

`--mode=sim` is bit-exact under whichever mode is in the fixture (currently `round_half_up`). `--mode=hil` will agree post-Track-0 if the silicon implements the resolved mode (highly expected). A silicon-side mismatch would manifest as `verify_bit_exact` reporting `n_mismatch > 0` with `max_abs_diff_int8 == 1` on the .5-tie elements; in the synthetic fixture, indices 1, 6, 12, 13, 15 are the canaries that flip if the silicon uses round_half_to_even instead.
