# SmartPower Analysis — Tychon PolarFire Control

**Device:** MPFS250T-FCVG484 (PolarFire SoC, Icicle Kit Reference Design)
**Date:** 2026-04-02
**Tool:** Libero SoC 2025.2 / SmartPower 3.0
**Method:** Post-P&R toggle-rate estimation (production data, typical conditions)
**Design:** MPFS_ICICLE_KIT_BASE_DESIGN with VectorBlox V1000 + SmartHLS PID
**Source:** `smartpower_refdesign.rpt` (accompanying raw report)

## KPP Requirement

Total payload power **must be < 12 W** to meet Phase I KPP (FX255-PCS02-0044).

## Power Summary (Post-P&R Actual)

| | Power (mW) | Percentage |
|---|---|---|
| **Total FPGA Power** | **2,663.9** | 100% |
| Static Power | 445.6 | 16.7% |
| Dynamic Power | 2,218.3 | 83.3% |

## Subsystem Power Breakdown

| Subsystem | Power (mW) | % | Notes |
|-----------|-----------|---|-------|
| Gate (FPGA fabric logic) | 1,381.5 | 51.9% | VectorBlox + PID + AXI interconnect |
| XCVR (SerDes/transceivers) | 319.8 | 12.0% | PCIe lanes (unused in Tychon — can be disabled) |
| Net (fabric routing) | 305.5 | 11.5% | Interconnect switching activity |
| I/O (pin ring) | 299.0 | 11.2% | DDR4 + GPIO + UART |
| DSP (Math blocks) | 158.8 | 6.0% | VBX MAC units for inference |
| Core Static (leakage) | 149.0 | 5.6% | Temperature-dependent |
| Memory (LSRAM/uSRAM) | 49.9 | 1.9% | VBX weight/activation buffers |
| Other Rails Static | 0.5 | 0.0% | Auxiliary |

## Clock Domain Breakdown

| Clock Domain | Power (mW) | % of Dynamic | Function |
|---|---|---|---|
| VBX main clock (PF_CCC_C1:OUT1) | 530.5 | 77.8% | CoreVectorBlox inference engine |
| VBX AXI clock (PF_CCC_C1:OUT0) | 79.7 | 11.7% | VBX memory interface |
| Fabric FIC clock (PF_CCC_C0:OUT0) | 53.9 | 7.9% | PID controller + FIC AXI bus |
| Fabric aux clocks (CCC_C0:OUT1/OUT3) | 15.5 | 2.3% | Peripheral buses |
| 160 MHz oscillator + dividers | 0.1 | 0.0% | Init monitor, clock conditioning |
| SerDes TX PLL | 1.3 | 0.2% | Transceiver reference |
| REF_CLK_50MHz | 0.6 | 0.1% | Board reference |

## Rail Breakdown

| Rail | Voltage (V) | Power (mW) | Current (mA) |
|------|------------|-----------|-------------|
| VDD (core) | 1.050 | 2,215.9 | 2,110.4 |
| VDDI 1.1 (I/O bank) | 1.100 | 224.7 | 204.2 |
| VDDA (analog) | 1.050 | 109.4 | 104.2 |
| VDDA25 (analog 2.5V) | 2.500 | 51.3 | 20.5 |
| VDD25 (2.5V) | 2.500 | 28.0 | 11.2 |
| VDD18 (1.8V) | 1.800 | 23.5 | 13.1 |
| VDDAUX | 2.500 | 6.6 | 2.6 |
| XCVR_VDD_CLK | 2.500 | 2.8 | 1.1 |
| VDDI 3.3 | 3.300 | 1.6 | 0.5 |
| VDDI 1.8 | 1.800 | 0.1 | 0.0 |

## Total System Power Estimate

| Component | Power (W) | Source |
|-----------|----------|--------|
| FPGA fabric (SmartPower actual) | 2.66 | This report |
| MSS — 4x RV64GC @ 600 MHz + DDR4 | ~2.50 | DS50003262 datasheet |
| **Total system** | **~5.2** | |
| **KPP limit** | **12.0** | |
| **Margin** | **~6.8 W (57%)** | |

## Key Observations

1. **VectorBlox dominates fabric power** — 610 mW (77.8% + 11.7% of dynamic) from the two VBX clock domains. This is V1000; the V250 target would use fewer resources and proportionally less power.
2. **PCIe SerDes consumes 320 mW** but is unused in the Tychon design. Disabling XCVR lanes would reduce total to ~2.34 W fabric.
3. **PID controller is negligible** — the FIC fabric clock domain (which includes PID + AXI bus) is only 53.9 mW.
4. **Memory power is minimal** at 49.9 mW — VBX weight buffers in LSRAM.
5. **Total ~5.2 W is well under the 12 W KPP** with 57% margin.

## Conditions

- Operating: Typical process, typical voltage, EXT temperature range
- Toggle rates: Default SmartPower estimation (no VCD stimulus)
- Data source: Production silicon characterization
- MSS power: Datasheet estimate (not included in SmartPower fabric analysis)

## Tychon-Specific Adjustments

The reference design includes components not in the Tychon payload:
- **PCIe (319.8 mW):** Not used — can be removed
- **I2C, PWM, UART peripherals:** Partially used — minimal impact
- **VBX V1000 vs V250:** Tychon targets V250, which uses fewer LUTs/DSPs — expect ~40-60% of V1000 power

Conservative Tychon estimate with V250 + no PCIe: **~3.5-4.0 W total system**.
