# Tychon PolarFire Control

**Repo 3** of the Tychon AI three-repo architecture for AFWERX SBIR Phase I (FX255-PCS02-0044).

| Repo | Purpose |
|------|---------|
| [tychon-nv-sim](https://github.com/your-org/tychon-nv-sim) | NV-center physics simulation and synthetic ODMR data generation |
| [tychon-odmr-ml](https://github.com/your-org/tychon-odmr-ml) | ML training, quantization, and VectorBlox export pipeline |
| **tychon-polarfire-control** | FPGA PID+AI hybrid control loop on PolarFire SoC |

## What This Repo Does

- SmartHLS C++ PID controller with bumpless AI→PID transfer
- Sector saturation clamps (±5%) and slew-rate limiting on AI feedforward
- Hardware watchdog (200 MHz, 1 ms timeout)
- Libero SoC project targeting MPFS250T with CoreVectorBlox V250
- Static timing (SmartTime) and power estimation (SmartPower) for deliverables

## Make Targets

```
make hls-test   # Run SmartHLS C++ software testbench (Beelink x86 only)
make clean       # Remove all build artifacts
make help        # Show available targets
```

## Cross-Machine Workflow

Source is edited on **DGX Spark** (ARM64) and pushed to GitHub.
**Beelink** (x86, Windows) pulls, runs SmartHLS compilation and Libero synthesis,
then pushes reports back. See `docs/cross_machine_workflow.md` for details.

**Never edit source on Beelink** — it is a build machine only.

## Key Constraints

- SmartHLS type: `hls::ap_fixpt<W,I>` (NOT `ap_fixed` — that's Xilinx)
- VectorBlox SDK **v2.0.3** (NOT v3.0) — matches CoreVectorBlox IP v2.0.1
- `.vnnx` compiled with `-s V250` flag; NOT committed to git
- Silver license → MPFS250T (fallback MPFS460T); RT PolarFire is Phase II only
- Bare-metal C on RISC-V MSS — no Linux (jitter violates <150 µs guarantee)

## Context for Claude Code

See [CLAUDE.md](CLAUDE.md) for project constraints and conventions when using Claude Code.
