# seed_7 Bitstream — Register Map for Demo Firmware

**Captured 2026-05-04** for the demo bring-up (Part 1 closure).

This document is the load-bearing reference for the Part 3 firmware
authored against the seed_7-derived bitstream. The bring-up plan
originally targeted `pid_csr_block.v` (the not-yet-netlist-validated
Phase II two-slot canvas design); the demo is instead being driven
off the audit-006 `seed_7` netlist closure, which exposes a
**different** register surface. TVW will overwrite Plan Part 3
register references against this document. Don't fork the plan.

## Bitstream identification

| Property | Value |
|---|---|
| Artifact path (Beelink) | `~/dev/projects/polarfire-hybrid-control/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job` |
| Size | 12,125,964 bytes (~11.5 MB) |
| sha256 (file) | `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a` |
| Libero design name | `MPFS_ICICLE_KIT_BASE_DESIGN` |
| Libero design checksum | `9F8A` |
| Fabric component digest | `07691012481460800402377c4342df4936432271e80c03e3248f9d3a06c03df8` |
| sNVM component digest | `ebf80ede6776e1b3c053fa31a33f8414e61e9f4d01778bebbc2bd8f363d32507` |
| Entire bitstream digest | `cf719213dda68a3887e0cc8e28b451a213becccd7a32cde847f2f1452cf46460` |
| Source project | `~\libero_seedsweep\seed_7\MPFS_ICICLE_Vectorblox.prjx` |
| Closure lineage | audit-006 r6_s25 P&R, +0.728 ns slack on 125 MHz FIC CCC PLL OUT0 user clock at slow_lv_ht; FCVG484 STD-grade Production silicon |
| Target device | MPFS250T-FCVG484E |
| Export script | `libero/scripts/04b_export_only.tcl` (commit on `bringup/part-1-bitstream`) |

`.job` is gitignored intentionally (`.gitignore:17` blocks `*.job`).
The `.sha256` sidecar and `_job.digest` file from Libero are
committed alongside this doc.

## Top-level architecture (from seed_7 netlist)

The MSS reaches two fabric slaves through the FIC_0 bus
(`FIC_0_PERIPHERALS_1_AXI4mslave0`):

```
                ┌───────────────────────────────────────────┐
                │          MPFS250T MSS                      │
                │                                            │
                │  RISC-V U54 cores                          │
                │   ↕                                        │
                │  FIC_0 master  →→→  FIC_0_PERIPHERALS_1    │
                └─────────────────────────┬──────────────────┘
                                          │ AXI4 (snooped)
                                          ▼
        ┌──────────────────────────┬─────────────────────────┐
        │  nv_pid_top_top          │  pid_io_block           │
        │  (proper AXI4 slave —    │  (eavesdropper —        │
        │   responds with RDATA)   │   master signals tied)  │
        └──────────────────────────┴─────────────────────────┘
                  ↓ datapath                ↓ register I/O
        actuator_out_write_data        error[63:0]
        actuator_out_write_en          u_AI_in[31:0]
                  ↓                          ↑
                  └──────── nv_pid_top_top consumes ──────────┘
        pid_io_block.actuator_capture ← nv_pid_top output strobe
```

`nv_pid_top_top` is the SmartHLS-generated wrapper around the
hand-written PID datapath. It is the **only** AXI slave that
responds back to the MSS through proper AW/W/B/AR/R handshakes —
its `axi4target` bus interface (HDL+ core in
`seed_7/component/User/Private/nv_pid_top_top/1.0/nv_pid_top_top.xml`)
is wired to `FIC_0_PERIPHERALS_1_AXI4mslave0`.

`pid_io_block` is wired in parallel as an eavesdropper: it taps the
master's AW/W/AR signals to update its internal registers but its
own response signals (`AWREADY`, `WREADY`, `BVALID`, `RDATA`,
`RVALID`, etc.) are tied to scratch wires that go nowhere except an
LED0 observability OR-tap. **The MSS cannot read pid_io_block's
state through AXI** — the read response comes from
`nv_pid_top_top`, not from `pid_io_block`. However, the MSS
**can** drive `pid_io_block`'s register update logic by writing to
the bus (since it eavesdrops AWADDR/WDATA), and `pid_io_block`'s
register outputs (`error_out`, `u_ai_out`) feed `nv_pid_top_top`'s
real-time inputs.

## FIC_0 master base address — **TBD pre-firmware**

The FIC_0_PERIPHERALS_1 sub-bus base address was not captured into
this doc at export time. Default for PolarFire SoC FIC_0 master is
`0x2000_0000` per Microchip MSS Configurator presets, but the
`FIC_0_PERIPHERALS_1` *sub-bus* offset within that depends on the
interconnect address allocation in seed_7's
`MPFS_ICICLE_KIT_BASE_DESIGN` SmartDesign.

To resolve before firmware authoring:

1. Open the address editor in seed_7 SmartDesign (Libero GUI →
   Tools → Address Editor → MPFS_ICICLE_KIT_BASE_DESIGN), OR
2. Grep the seed_7 SmartDesign export Tcl for the
   `sd_modify_address_map` entries on `FIC_0_PERIPHERALS_1`, OR
3. Empirically: program the kit, hit known offsets via JTAG-debug
   (SoftConsole) and observe responses.

Until that's resolved, treat the offsets below as *relative to
some `FIC_0_PERIPHERALS_1_BASE`*. Firmware should `#define`
`FIC_0_PERIPHERALS_1_BASE` and use it as the prefix.

## Register surface 1 — `pid_io_block` (write-side useful, read-side severed)

Source: `~/dev/projects/polarfire-hybrid-control/libero/hdl/pid_io_block.v`
(in this repo; the seed_7 build uses an instance of the same RTL).

**Window:** 0x20 bytes (5 registers, 32-bit aligned). Address decode
uses `S_AXI_AWADDR[4:2]` / `S_AXI_ARADDR[4:2]`; bits above [4] are
ignored. Slot the base at any `0x20`-byte-aligned offset within
FIC_0_PERIPHERALS_1.

**MSS-readable: NO.** Read-channel response wires are tied to the
LED0 OR-tap, not to the master. Reads from offsets in this window
return `nv_pid_top_top`'s response (Register surface 2 below).

| Offset | Name | Direction (HW) | MSS visibility | Meaning |
|---|---|---|---|---|
| `+0x00` | `actuator_out_capture` | RO from MSS view, but unreachable | **invisible** | Sticky-captured `nv_pid_top.actuator_out_write_data` (Q16.16, sign-extended to 32b). Reading clears the valid bit (in the slave's internal state, but MSS read goes to `nv_pid_top_top` — the clear strobe doesn't fire) |
| `+0x04` | `actuator_out_status` | RO | **invisible** | `bit[0] = capture_valid` (sticky, would be cleared by reading 0x00 if the read landed on this slave) |
| `+0x08` | `error_input_low` | RW | **write reaches** | Low 32 bits of `nv_pid_top.error[63:0]`; drives PID input directly. **Reads return nv_pid_top's response, not this register's stored value.** |
| `+0x0C` | `error_input_high` | RW | **write reaches** | High 32 bits of `nv_pid_top.error[63:0]` |
| `+0x10` | `u_ai_input` | RW | **write reaches** | `nv_pid_top.u_AI_in[31:0]` (Q16.16) — feed-forward AI input |

**Demo implication:** writing to `+0x08`/`+0x0C`/`+0x10` from MSS
firmware drives PID input values directly. The PID's response can
be observed via:
- `nv_pid_top_top.axi4target` reads (Register surface 2 below)
- LED0 toggling (via the observability OR-tap)
- The `nv_pid_top_0_actuator_out_write_data` wire is exposed in the
  SmartDesign netlist; if a future iteration promotes it to a top
  port, it can be probed via GPIO

The Plan Part 3 Option A demo flow that "writes Kp" doesn't map
directly here — Kp/Ki/Kd live in `nv_pid_top_top`'s axi4target
window, not in `pid_io_block`. Use this surface for **driving PID
inputs** (error, u_AI_in), not for **configuring gains**.

## Register surface 2 — `nv_pid_top_top.axi4target` (proper AXI4 slave)

Source: HDL+ core registration at
`seed_7/component/User/Private/nv_pid_top_top/1.0/nv_pid_top_top.xml`.
The bus interface is named `axi4target`; the slave bus has a
**6-bit address** (`axi4target_araddr[5:0]`) → **64-byte window**
(16 32-bit registers max, exact register count and naming
determined by SmartHLS-emitted Verilog).

This is where the SmartHLS function arguments become AXI registers.
Looking at the C++ signature in `hls/src/nv_pid.cpp`:

```cpp
void nv_pid_top(
    freq_t error,                  // 64-bit input  (Q34.30)   — simple wire
    out_t u_AI_in,                 // 32-bit input  (Q16.16)   — simple wire
    bool ai_watchdog_timeout,      //                          — simple wire
    gain_t Kp, Ki, Kd,             // 32-bit  (Q16.16)         — AXI target
    out_t out_min, out_max,        // 32-bit  (Q16.16)         — AXI target
    out_t &actuator_out            // 32-bit (Q16.16)          — simple wire
)
```

Args tagged `#pragma HLS interface s_axi` (or whichever pragma maps
them to the AXI slave) become registers in `axi4target`.
**Per-arg offsets and the precise register naming** must be
extracted from the actual Verilog SmartHLS produced for the seed_7
build (NOT the freshly-generated `hls/hls_output/rtl/...v` from
2026-05-04, which is from a different SmartHLS run and may have
different register packing).

To extract from seed_7:

```bash
# The SmartHLS-generated nv_pid_top RTL is registered as an HDL+ core,
# not a plain HDL file. Its source is referenced by the XML at
# seed_7/component/User/Private/nv_pid_top_top/1.0/nv_pid_top_top.xml.
# That XML lists the file path of the actual .v in seed_7's hdl tree
# or its component tree.

ssh bee 'grep -A2 "<spirit:fileSet" ~/libero_seedsweep/seed_7/component/User/Private/nv_pid_top_top/1.0/nv_pid_top_top.xml'

# Then read that .v and look for the AXI register-decode case
# statement (axi4target_awaddr[5:2] case dispatch). The cases reveal
# the per-register offsets and which Verilog register each maps to.
```

**Until that extraction lands, treat the axi4target offsets as
unknown.** Firmware development can proceed against `pid_io_block`
(write side) for the first demo milestone (Option A: "PID input
written from terminal, observe LED0 and capture register"), and
the axi4target reads can be filled in once offsets are extracted.

## Recommended demo Part 3 reframe

The original Plan Part 3 Option A relied on `pid_csr_block`'s 18
named registers with stable offsets `0x000` (axi_write_count,
liveness counter), `0x004` (csr_version `= 0x00010000`), through
`0x05C` (ai_active_flag). **None of those registers exist on this
bitstream.**

Reframe Part 3 Option A as:

1. **Liveness check** — read at any offset in
   `nv_pid_top_top.axi4target`'s 64-byte window (e.g., `0x00` or
   `0x04`); a non-bus-error response confirms the AXI path is
   alive end to end. The exact value depends on SmartHLS register
   packing.
2. **Write-input demo** — write a known Q16.16 value to
   `pid_io_block`'s `+0x10` (`u_ai_input`), then drive a stimulus
   on `error_input_low/high` (`+0x08`/`+0x0C`); observe LED0
   toggle rate change as `nv_pid_top_top` recomputes. This is
   visceral and reviewer-credible.
3. **Read-back demo** — read `nv_pid_top_top.axi4target`'s
   gain/output registers (whichever offsets resolve once
   extraction is done); demonstrate gain values are consistent
   with a previous write.

Step 1 is unconditional (works without any further extraction).
Steps 2-3 depend on `FIC_0_PERIPHERALS_1_BASE` being known; step 3
additionally depends on axi4target offset extraction.

## Open items before firmware authoring

- [ ] Resolve `FIC_0_PERIPHERALS_1_BASE` (address editor or grep
  seed_7 SmartDesign export Tcl).
- [ ] Extract `nv_pid_top_top.axi4target` register offsets from
  the SmartHLS Verilog actually used in the seed_7 build.
- [ ] Verify the `pid_io_block` instance is at offset `0x000`
  within FIC_0_PERIPHERALS_1 (or whatever the SmartDesign
  allocation chose). The pid_io_block decodes addr bits [4:2]
  only; if the SmartDesign places it at a non-zero offset, the
  base accumulates.
- [ ] Confirm `nv_pid_top_top` doesn't sit at the same FIC_0
  sub-bus address as `pid_io_block` (the eavesdropper pattern
  works because they don't compete for response, but if the
  SmartDesign placed both at the same base, MSS reads would land
  on `nv_pid_top_top` while writes would also fan to
  `pid_io_block`'s registers — that's the intended behavior).

## Provenance for verification

Every claim in this doc traces back to one of:
- `libero/hdl/pid_io_block.v` (RTL source, in this repo)
- `seed_7/component/work/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN.v`
  (SmartDesign netlist, on Beelink — lines 869-922 for pid_io_block
  wiring; line 1884 for `nv_pid_top_top nv_pid_top_0` instance)
- `seed_7/component/User/Private/nv_pid_top_top/1.0/nv_pid_top_top.xml`
  (HDL+ core registration with axi4target signals, on Beelink)
- `04b_export_only.tcl` run log 2026-05-04 (`/tmp/04b_run.log` on
  Beelink; archived in this commit's git log via the bitstream
  digest)

If something here turns out wrong post-program, the trace says
where to re-check.
