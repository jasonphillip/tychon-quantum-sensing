# FIC_0 Address Map — seed_7 Bitstream (2026-05-18 Extraction)

This document is the load-bearing address-map reference for the rung-E AXI register loopback firmware. It resolves the "TBD pre-flight" gap from `docs/seed_7_register_map_2026-05-04.md` by extracting `FIC_0_PERIPHERALS_1` base address and `nv_pid_top_top.axi4target` per-register offsets directly from the seed_7 P&R project on Beelink — **without** opening Libero's Address Editor GUI.

## Result summary

| Window | Base address | Size | Sub-blocks |
|---|---|---|---|
| FIC_0_PERIPHERALS_1.AXI4mslave0 (PID slot) | **`0x60001000`** | 4 KB | `pid_io_block_0` (eavesdropper) + `nv_pid_top_0.axi4target` (proper AXI slave) |
| FIC_0_PERIPHERALS_1.AXIM_SLAVE0 (V250 NPU master path) | n/a | (VBX_AXIM is master-out, not MSS-visible window) | CoreVectorBlox V250 |

The MSS RISC-V cores write/read the PID block via FIC_0 master at MSS-side address `0x60001000` (4 KB window).

## Extraction methodology (corpus + repo evidence — no GUI session)

**Three methods attempted, two productive:**

### Method 1 — grep SmartDesign export Tcl for `sd_modify_address_map`
**Result: empty.** Seed_7 has 31 `.tcl` files under `component/`, but none contain `sd_modify_address_map` or `FIC_0_PERIPHERALS_1` keywords. The address-editor state isn't persisted as Tcl in this project tree; it's stored inside the CoreAXI4Interconnect component parameters (Method 3 below).

### Method 2 — find post-synth memory/address map report
**Result: empty.** No `*memory_map*.{html,txt}` or `*address_map*` report files present in seed_7's `synthesis/` or `designer/` directories. (Microchip Libero 2025.2 doesn't auto-generate one without specific Tcl trigger.)

### Method 3 — CoreAXI4Interconnect component parameters (PRODUCTIVE)
**Result: address map fully resolved.** The instance `FIC0_INITIATOR_inst_0` at line 1143 of `component/work/FIC_0_PERIPHERALS/FIC_0_PERIPHERALS.v` is a `Actel:DirectCore:COREAXI4INTERCONNECT:2.9.100` 1-master × 10-slave crossbar. Its slave start/end addresses are baked into the component definition at `component/work/FIC0_INITIATOR/FIC0_INITIATOR.v` lines 1153–1247:

```
"SLAVE0_START_ADDR:0x60001000"   "SLAVE0_END_ADDR:0x60001fff"    # PID slot (AXI4mslave0)
"SLAVE1_START_ADDR:0x60000000"   "SLAVE1_END_ADDR:0x60000fff"    # 4-KB window (assignment TBD)
"SLAVE2_START_ADDR:0x60030000"   "SLAVE2_END_ADDR:0x60030fff"    # 4-KB window
"SLAVE3_START_ADDR:0x60040000"   "SLAVE3_END_ADDR:0x60040fff"    # 4-KB window
"SLAVE4_START_ADDR:0x20000000"   "SLAVE4_END_ADDR:0x27ffffff"    # 128 MB MSS window
"SLAVE5_START_ADDR:0x28000000"   "SLAVE5_END_ADDR:0x2fffffff"    # 128 MB MSS window
"SLAVE6_START_ADDR:0x30000000"   "SLAVE6_END_ADDR:0x37ffffff"    # 128 MB MSS window
"SLAVE7_START_ADDR:0x38000000"   "SLAVE7_END_ADDR:0x3fffffff"    # 128 MB MSS window
"SLAVE8_START_ADDR:0x40000000"   "SLAVE8_END_ADDR:0x47ffffff"    # 128 MB MSS window
"SLAVE9_START_ADDR:0x48000000"   "SLAVE9_END_ADDR:0x4fffffff"    # 128 MB MSS window
```

The `FIC_0_PERIPHERALS.v` parent module connects `FIC0_INITIATOR_inst_0.SLAVE0_*` ports directly to its own `AXI4mslave0_*` ports (line 1233+ of `FIC_0_PERIPHERALS.v`), so `FIC_0_PERIPHERALS_1.AXI4mslave0` ≡ FIC0_INITIATOR SLAVE0 ≡ `0x60001000–0x60001fff` (4 KB).

## nv_pid_top_top.axi4target per-register offsets

Extracted from the bitstream-version SmartHLS driver at:
```
~/dev/projects/tychon-polarfire-control/hls/hls_output/accelerator_drivers/nv_pid_top_accelerator_driver.cpp
```
(IMPORTANT: this is the **Apr 28 2026** build referenced by `seed_7/component/User/Private/nv_pid_top_top/1.0/nv_pid_top_top.xml`. The newer May-17 RPO-4 rebuild at `polarfire-hybrid-control/hls/hls_output/` is NOT the bitstream version — do not use it for register-map purposes.)

| Offset | Register | Direction | Q-format | Function |
|---|---|---|---|---|
| `0x00` | (reserved) | — | — | not decoded by SmartHLS slave |
| `0x04` | (reserved) | — | — | not decoded by SmartHLS slave |
| `0x08` | `acc_start` | RW | uint32 | Write `1` = start; read `0` = idle, `1` = running |
| `0x0C` | `Kp` | RW | Q16.16 | Proportional gain |
| `0x10` | `Ki` | RW | Q16.16 | Integral gain |
| `0x14` | `Kd` | RW | Q16.16 | Derivative gain |
| `0x18` | `out_min` | RW | Q16.16 | Actuator output lower clamp |
| `0x1C` | `out_max` | RW | Q16.16 | Actuator output upper clamp |

Span: 32 bytes (per `nv_pid_top_memory_map.h: NV_PID_TOP_SPAN_ADDR 0x20`). Window occupies `0x60001000–0x6000101F` of the 4 KB FIC_0 PID slot.

## Eavesdropper architecture — write-collision map

`docs/seed_7_register_map_2026-05-04.md` documents that the seed_7 top-level Verilog wires the same `FIC_0_PERIPHERALS_1_AXI4mslave0_*` bus to **two** consumers in parallel: `pid_io_block_0` (write-side useful, read-severed — drives `nv_pid_top_0.error` + `u_AI_in` constant inputs) and `nv_pid_top_0.axi4target` (SmartHLS-generated proper AXI slave, but most input ports tied to constant nets — only AWVALID/WVALID/awaddr[lsbs] are connected).

Consequence: writes to certain addresses hit BOTH blocks. The full overlap map for the 4 KB window:

| Absolute address | pid_io_block effect | nv_pid_top_top.axi4target effect | Notes |
|---|---|---|---|
| `0x60001000` | `actuator_out_capture` (RO; read-severed) | — | Reads return nv_pid_top's response (which is unmapped), not pid_io_block's value |
| `0x60001004` | `actuator_out_status` (RO; read-severed) | — | |
| `0x60001008` | `error_input_low` (RW; write reaches) | `acc_start` (RW) | **OVERLAP**: writing here both stimulates error_low AND toggles SmartHLS start/idle |
| `0x6000100C` | `error_input_high` (RW; write reaches) | `Kp` (RW Q16.16) | **OVERLAP**: writing Kp also drives error[63:32] |
| `0x60001010` | `u_ai_input` (RW; write reaches) | `Ki` (RW Q16.16) | **OVERLAP**: writing Ki also drives u_AI_in |
| `0x60001014` | (not decoded by pid_io_block) | `Kd` (RW Q16.16) | Clean |
| `0x60001018` | (not decoded by pid_io_block) | `out_min` (RW Q16.16) | Clean |
| `0x6000101C` | (not decoded by pid_io_block) | `out_max` (RW Q16.16) | Clean |

**Firmware implication for rung E (AXI register loopback):**

1. Write/read sequence on `Kd` / `out_min` / `out_max` (the three clean addresses) is the most useful "AXI loopback" verifier — no eavesdropper interaction, just nv_pid_top's proper slave responding.
2. Setting `Kp` / `Ki` also writes `error_high` / `u_ai_input` (stimulus) — accept this dual-write as a known feature; the controller will see canonical gains plus a fixed startup stimulus drawn from the gain values. Initialise Kp/Ki/Kd to their final values once at boot, then drive `error_low` (0x60001008) cleanly for run-time stimulus — but note this ALSO toggles `acc_start`, so loopback test must be designed around the SmartHLS pipeline timing.
3. Setting `acc_start = 1` at 0x60001008 also writes a value to `pid_io_block.error_input_low` — both effects expected.
4. **Reads at 0x60001000–0x60001007** return nv_pid_top's bus response (likely 0 or bus-error since those offsets aren't decoded by SmartHLS); the eavesdropper's "actuator_out_capture" register is not MSS-readable in this fabric.

The cleanest rung-E sequence:
- (1) Write Kd = 0x00001000 (Q16.16: 0.0625), read Kd, compare → confirms AXI path
- (2) Write out_min = 0x10000 (1.0), read out_min, compare
- (3) Write Kp = 0x10000, observe LED tap (which mirrors actuator_out_write_en) for activity
- (4) Drive `acc_start` = 1 at 0x60001008, poll until is_idle = 0 → 1 transition

## Verification of result

Three corroborating facts from independent files all point to `0x60001000`:

1. `component/work/FIC0_INITIATOR/FIC0_INITIATOR.v:1156` — Tcl param string `SLAVE0_START_ADDR:0x60001000`
2. `component/work/FIC0_INITIATOR/FIC0_INITIATOR.v:4890` — Verilog defparam `.SLAVE0_START_ADDR('h60001000)`
3. `component/work/FIC_0_PERIPHERALS/FIC_0_PERIPHERALS.v:1233+` — wires SLAVE0_AWADDR/ARADDR of FIC0_INITIATOR_inst_0 to FIC_0_PERIPHERALS module's AXI4mslave0 ports

DRC report confirms the AXI slave bus is connected: `component/work/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN_DRC.xml` carries a Warning about `FIC_0_PERIPHERALS_1:AXI4mslave0:AXI4mslave0_SLAVE0_AWID[0-8]` bus-interface ID width mismatch with `MSS_WRAPPER_1:FIC_0_AXI4_TARGET` — confirms the MSS-to-fabric AXI4 connection is live but flagged for the ID-width difference (8 bits fabric, 4 bits MSS — handled by the interconnect).

## File-and-path reference (Beelink-only paths)

- seed_7 project root: `~/libero_seedsweep/seed_7/`
- CoreAXI4Interconnect instance: `~/libero_seedsweep/seed_7/component/work/FIC0_INITIATOR/FIC0_INITIATOR.v`
- Parent FIC_0_PERIPHERALS module: `~/libero_seedsweep/seed_7/component/work/FIC_0_PERIPHERALS/FIC_0_PERIPHERALS.v`
- Top-level design: `~/libero_seedsweep/seed_7/component/work/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN.v`
- nv_pid_top XML pointer: `~/libero_seedsweep/seed_7/component/User/Private/nv_pid_top_top/1.0/nv_pid_top_top.xml`
- nv_pid_top SmartHLS Verilog (bitstream version, Apr 28 2026, 257,368 bytes): `~/dev/projects/tychon-polarfire-control/hls/hls_output/rtl/nv_pid_top_nv_pid_top.v`
- nv_pid_top SmartHLS driver (bitstream version): `~/dev/projects/tychon-polarfire-control/hls/hls_output/accelerator_drivers/nv_pid_top_accelerator_driver.cpp`

## Note on the May-17 fresh HLS rebuild

A newer SmartHLS rebuild exists at `~/dev/projects/polarfire-hybrid-control/hls/hls_output/` on bee (May 17 2026, 272,227 bytes). It is the post-RPO-4-derivative-filter version of `nv_pid_top_nv_pid_top.v` — **not** the bitstream version. Register packing may differ. Do NOT use the May-17 rebuild's driver to author firmware against the seed_7 bitstream; use only the Apr-28 `tychon-polarfire-control/` driver until a fresh bitstream is exported from the May-17 RTL.
