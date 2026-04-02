# Phase I Findings

## Libero Synthesis & Place-and-Route Results (April 2, 2026)

Target: MPFS250T (PolarFireSoC Icicle Kit), VectorBlox V1000 (PRESET:1) + SmartHLS PID at top level.
Reference design: MPFS_ICICLE_KIT_REFERENCE_DESIGN with VECTORBLOX MSS_BAREMETAL flags.
Tool: Libero SoC 2025.2, Synplify Pro W-2025.03M-SP1-1.

| Resource | Used | Available | Utilization |
|----------|------|-----------|-------------|
| 4LUT | 62,837 | 254,196 | 25% |
| DSP/Math | 164 | 784 | 21% |
| uSRAM | 434 | — | ~18% |
| LSRAM | 96 | — | combined |

Timing: PASS — worst slack +0.165 ns at 100 MHz (first seed, no multi-pass needed)
Clock domains: FIC_0_CLK (100 MHz) for both VBX control and PID, VBX clk_2x at 200 MHz
PLL jitter: 0.135 ns peak-to-peak
System jitter: 0.052 ns (worst aggressor: REF_CLK_50MHz)

Key finding: VectorBlox V1000 + SmartHLS PID both fit on MPFS250T with 75% LUT headroom. Phase II can add additional IP (gradiometer processing, telemetry) without resource pressure. The PID's II=1 pipeline at 100 MHz gives ~10 ns per cycle — well within the 150 us latency budget (15,000x margin).

Reports archived at: libero/reports/
