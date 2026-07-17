# File Structure, Build/Test, Safety Summary, Known Gotchas

> Moved verbatim from CLAUDE.md during the 2026-07-17 progressive-disclosure restructure.

## File Structure
```
hls/
  src/nv_pid.cpp          — Top-level PID function (II=1 pipeline, AXI target + simple wires)
  src/nv_pid.hpp          — NVPID class with bumpless transfer and anti-windup
  src/safety_clamps.cpp   — Sector saturation clamp and slew-rate limiter
  src/watchdog.cpp        — Hardware watchdog timer RTL / safety-spec timeout infrastructure
  include/fp_types.hpp    — Fixed-point typedefs: freq_t (Q34.30), gain_t/out_t (Q16.16)
  include/rta_config.hpp  — Safety constants: clamp fraction, max slew, watchdog cycles
  tb/tb_bumpless.cpp      — Bumpless transfer testbench
  tb/stimulus/            — Drop-in directory for ODMR CSV test vectors
  Makefile                — SmartHLS build config (NAME, SRCS, flags)

libero/
  scripts/01_scaffold_proj.tcl  — Initialize Libero project (MPFS250T, constraints)
  scripts/02_import_ip.tcl      — Import SmartHLS PID + CoreVectorBlox + CCC + InitMon
  scripts/03_smartdesign.tcl    — Wire MSS FIC ports, clock, reset, AXI interconnect
  scripts/04_synth_pnr.tcl      — Synthesis, P&R, SmartTime, SmartPower, report extraction
  constraints/timing_200mhz.sdc — 200 MHz (5 ns) clock constraint
  constraints/pinout.pdc         — Board-specific I/O (placeholder for Icicle Kit)
  reports/                       — Tool-generated synthesis and timing reports

	firmware/    — RISC-V MSS code. Per 2026-06-15 decision: Linux userspace tools
	               cross-built with riscv64-*-linux-gnu-gcc, NOT bare-metal.
	               Current idfix2 PID map is 0x60040000..0x60040fff; V250 is
	               0x60030000; never poke 0x60001000.
	               Current helper for kit-side V250->PID loop: v250_pid_loop.c.
models/      — Compiled .vnnx model binaries (not committed, excluded by .gitignore)
```

## Build and Test

SmartHLS and Libero require an x86 host with Microchip tools installed.

```bash
make hls-test    # Run SmartHLS C++ software testbench (verifies bumpless transfer)
make clean       # Remove build artifacts
```

Libero Tcl scripts run sequentially in the Libero Tcl console:
```
source libero/scripts/01_scaffold_proj.tcl   # Creates project, imports constraints
source libero/scripts/02_import_ip.tcl       # Imports PID RTL + CoreVectorBlox + clock/reset
source libero/scripts/03_smartdesign.tcl     # Wires AXI interconnect, promotes datapath ports
source libero/scripts/04_synth_pnr.tcl       # Runs synthesis, P&R, extracts reports
```

The `hls-test` testbench verifies:
- PID output tracks frequency error with correct gain application
- Bumpless transfer absorbs AI output into integrator without voltage discontinuity
- PASS/FAIL printed to stdout based on delta at transition vs expected natural step

## Safety Architecture (Summary)
- **Sector clamp**: AI output bounded to +-4.5% of actuator range (guarantees +-5% after Q16.16 rounding)
- **Slew limiter**: Per-cycle AI output change bounded by `MAX_SLEW_PER_CYCLE`
- **Watchdog**: current programmed demo image is 250,000 cycles at 125 MHz = 2 ms; report raw state plus the user-facing safe-fallback / AI-assist state
- Formal basis: Lur'e/Circle Criterion absolute stability — AI treated as sector-bounded nonlinearity

## Known Gotchas
- SmartHLS 2025.2 may generate different output directory names — check `hls/hls_output/` vs `hls/output/` after `shls hw`
- SmartHLS may mangle port names (e.g. `_V` suffix for std_logic_vector) — verify generated Verilog
- CoreVectorBlox VLNV string may vary by Libero version (vendor field: Actel vs Microsemi vs Microchip)
- The Tcl scripts contain `VERIFY_AFTER_SHLS_HW` comments marking values that depend on actual tool output
- VectorBlox SDK tools require x86-64 Linux — `.so` libraries won't load on ARM64 or native Windows
- Python 3.10 required for VectorBlox SDK venv (not 3.11/3.12 — ABI mismatch)
- `flatc` must be v23.5.26 (not apt default) for VectorBlox FlatBuffer compatibility
