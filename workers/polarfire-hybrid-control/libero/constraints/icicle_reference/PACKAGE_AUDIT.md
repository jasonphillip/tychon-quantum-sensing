# Package-Cross-Mapping Audit — FCVG484 → FCSG536e (HW-04b)

This audit documents every pin assignment in the staged `icicle_reference/` PDC bundle and flags how each must be handled when integrated into `libero/constraints/pinout.pdc` for the FCSG536e silicon (engineering-sample variant). The reference bundle is FCVG484-keyed; HW-01 confirmed silicon is FCSG536e (not FCVG484), so each pin name needs verification against the FCSG536e ball matrix.

## Summary

| Metric | Count |
|---|---|
| Source PDCs | 17 (15 with `set_io` declarations; `DRI_CCC_DEMO.pdc` and `NW_PLL.pdc` use only `set_iobank`) |
| Total `set_io` declarations | 120 |
| Distinct ball names referenced (FCVG484) | 87 |
| Total ports | 117 (3 ports appear in two mutually-exclusive PDCs, see "Pin conflicts" below) |
| Source: polarfire-soc/icicle-kit-reference-design commit `fd0aebb` |

## Verdict tags

Per the audit's verdict scheme:

| Tag | Meaning |
|---|---|
| `MAP_OK` | Same ball on both packages, or 1:1 mapping documented |
| `MAP_REROUTE` | Different ball on FCSG536e but same I/O bank, equivalent pad type — rewrite the `-pin_name` |
| `MAP_DROP` | No equivalent on FCSG536e — drop and surface in design doc which top-level I/O loses physical pinning |
| `MAP_TBD` | Manual review required (default until ball-matrix data available) |

**Current verdict for all 120 pins:** `MAP_TBD`. Resolution requires:

1. **UG0726 — PolarFire SoC Pin Descriptions** (Microchip portal). Ball-matrix data for FCVG484 AND FCSG536e packages, including pad-to-ball routing tables. Was NOT found in `~/.corpus/polarfire-control-corpus/` during T3.1 corpus search. Must be fetched from the Microchip portal during HW-04b execution; capture revision letter + pub date for the Appendix C citation closeout (separate from C-19/C-20).
2. **Libero device-DB runtime introspection** (alternative). When `01_scaffold_proj.tcl` runs against Libero 2025.2, log the resolved device entry — if Libero exposes ES-specific pin-description data for FCSG536e (the engineering-sample variant), prefer it over UG0726's production-die entries.

## Pin conflicts (intra-bundle)

Several balls appear in multiple PDCs because the PDCs are mutually-exclusive variants:

| Ball | Used by | Resolution |
|---|---|---|
| `C9` | `mBUS_I2C_SCL` (ICICLE_I2C_LOOPBACK), `QSPI_DATA_2` (ICICLE_RPi), `RPi_GPIO20` (ICICLE_RPi_MICRON_QSPI) | Pick one; ICICLE_I2C_LOOPBACK conflicts with both RPi variants |
| `B5` | `mBUS_I2C_SDA` (ICICLE_I2C_LOOPBACK), `RPi_GPIO19` (RPi + RPi_MICRON_QSPI) | Pick one |
| `B4` | `I2C1_SDA` (ICICLE_I2C_LOOPBACK), `RPi_GPIO26` (RPi + RPi_MICRON_QSPI) | Pick one |
| `C5` | `RPi_GPIO20` (ICICLE_RPi), `QSPI_DATA_2` (ICICLE_RPi_MICRON_QSPI) | Pick one variant |
| `D13` | `SPI_0_DI` (ICICLE_SPI_LOOPBACK), `QSPI_DATA_0` (RPi + RPi_MICRON_QSPI) | Pick one |
| `G12` | `QSPI_DATA_1` (RPi + RPi_MICRON_QSPI), `SPI_0_DO` (ICICLE_SPI_LOOPBACK) | Pick one |
| `C10` | `QSPI_CLK` (RPi + RPi_MICRON_QSPI), `SPI_0_CLK_PAD` (ICICLE_SPI_LOOPBACK) | Pick one |
| `H12` | `QSPI_SEL` (RPi + RPi_MICRON_QSPI), `SPI_0_SS` (ICICLE_SPI_LOOPBACK) | Pick one |

For HW-04c integration, the recommended subset (no intra-conflicts, covers the MPFS_ICICLE_KIT_BASE_DESIGN top-level I/O surface):

```
ICICLE.pdc                  (master: SW1-4, LED0-3, REF_CLK_50MHz)
ICICLE_PCIE.pdc             (PCIe lanes + REF_CLK_PAD)
decision-2-option-c.pdc     (XCVR REF_CLK explicit lock; layered AFTER ICICLE_PCIE)
ICICLE_MMUART0.pdc          (MSS UART0 console)
ICICLE_MMUART1.pdc          (optional)
ICICLE_MMUART2.pdc          (optional)
ICICLE_MMUART3.pdc          (optional)
ICICLE_MAC.pdc              (VSC8662 PHY config)
ICICLE_USB.pdc              (USB_ULPI_RESET)
ICICLE_SDIO.pdc             (SDIO_SW switching)
ICICLE_CAN0.pdc             (CAN_0 RXD/TXD/EBL)
ICICLE_RPi_MICRON_QSPI.pdc  (RPi GPIO + Micron QSPI; preferred over ICICLE_RPi.pdc)
ICICLE_MIKROBUS.pdc         (mikroBUS — verify no overlap with chosen RPi variant)
DRI_CCC_DEMO.pdc            (CCC demo — set_iobank only, no pin conflicts)
NW_PLL.pdc                  (NW PLL — set_iobank only, no pin conflicts)
```

`ICICLE_I2C_LOOPBACK.pdc` and `ICICLE_SPI_LOOPBACK.pdc` are excluded from the recommended subset because they conflict with the QSPI/RPi variants. Add only if the design needs the loopback overlay AND the QSPI/RPi pins are not used.

## Per-PDC port → pin table

All 120 pin assignments, grouped by PDC. Direction and IO_Std preserved for the FCSG536e remap. Verdict column is `MAP_TBD` for every row pending UG0726 / Libero DB resolution.

### ICICLE.pdc (master — switches, LEDs, 50 MHz reference clock)

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| SW1 | V19 | INPUT |  | MAP_TBD |
| SW2 | U18 | INPUT |  | MAP_TBD |
| SW3 | W19 | INPUT |  | MAP_TBD |
| SW4 | W18 | INPUT |  | MAP_TBD |
| LED0 | V14 | OUTPUT |  | MAP_TBD |
| LED1 | U13 | OUTPUT |  | MAP_TBD |
| LED2 | T12 | OUTPUT |  | MAP_TBD |
| LED3 | AB19 | OUTPUT |  | MAP_TBD |
| REF_CLK_50MHz | W12 | INPUT |  | MAP_TBD |

### ICICLE_PCIE.pdc (PCIe RX/TX lanes + REF_CLK_PAD)

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| PCIE_1_PERST_N | D19 | OUTPUT | LVCMOS33 | MAP_TBD |
| PCIESS_LANE_RXD0_N | G19 | INPUT |  | MAP_TBD |
| PCIESS_LANE_RXD0_P | G20 | INPUT |  | MAP_TBD |
| PCIESS_LANE_RXD1_N | K21 | INPUT |  | MAP_TBD |
| PCIESS_LANE_RXD1_P | K22 | INPUT |  | MAP_TBD |
| PCIESS_LANE_RXD2_N | M21 | INPUT |  | MAP_TBD |
| PCIESS_LANE_RXD2_P | M22 | INPUT |  | MAP_TBD |
| PCIESS_LANE_RXD3_N | R19 | INPUT |  | MAP_TBD |
| PCIESS_LANE_RXD3_P | R20 | INPUT |  | MAP_TBD |
| PCIESS_LANE_TXD0_N | F21 | OUTPUT |  | MAP_TBD |
| PCIESS_LANE_TXD0_P | F22 | OUTPUT |  | MAP_TBD |
| PCIESS_LANE_TXD1_N | H21 | OUTPUT |  | MAP_TBD |
| PCIESS_LANE_TXD1_P | H22 | OUTPUT |  | MAP_TBD |
| PCIESS_LANE_TXD2_N | P21 | OUTPUT |  | MAP_TBD |
| PCIESS_LANE_TXD2_P | P22 | OUTPUT |  | MAP_TBD |
| PCIESS_LANE_TXD3_N | T21 | OUTPUT |  | MAP_TBD |
| PCIESS_LANE_TXD3_P | T22 | OUTPUT |  | MAP_TBD |
| REF_CLK_PAD_P | L19 | INPUT |  | MAP_TBD |
| REF_CLK_PAD_N | L20 | INPUT |  | MAP_TBD |

### ICICLE_MMUART0.pdc (MSS UART0 — required for HW-03 console)

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| MMUART_0_TXD_M2F | B14 | OUTPUT | LVCMOS33 | MAP_TBD |
| MMUART_0_RXD_F2M | F15 | INPUT | LVCMOS33 | MAP_TBD |

### ICICLE_MMUART1.pdc

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| MMUART_1_TXD_M2F | E13 | OUTPUT | LVCMOS33 | MAP_TBD |
| MMUART_1_RXD_F2M | G13 | INPUT | LVCMOS33 | MAP_TBD |

### ICICLE_MMUART2.pdc

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| MMUART_2_TXD_M2F | B22 | OUTPUT | LVCMOS33 | MAP_TBD |
| MMUART_2_RXD_F2M | C22 | INPUT | LVCMOS33 | MAP_TBD |

### ICICLE_MMUART3.pdc

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| MMUART_3_TXD_M2F | D21 | OUTPUT | LVCMOS33 | MAP_TBD |
| MMUART_3_RXD_F2M | B21 | INPUT | LVCMOS33 | MAP_TBD |

### ICICLE_MAC.pdc (VSC8662 PHY config)

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| VSC_8662_CMODE3 | D18 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_CMODE4 | A18 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_CMODE5 | B18 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_CMODE6 | A12 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_CMODE7 | B12 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_OSCEN | E18 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_PLLMODE | D12 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_RESETN | C12 | OUTPUT | LVCMOS33 | MAP_TBD |
| VSC_8662_SRESET | D16 | OUTPUT | LVCMOS33 | MAP_TBD |

### ICICLE_USB.pdc

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| USB_ULPI_RESET | A5 | OUTPUT | LVCMOS33 | MAP_TBD |

### ICICLE_SDIO.pdc

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| SDIO_SW_SEL0 | D7 | OUTPUT | LVCMOS33 | MAP_TBD |
| SDIO_SW_SEL1 | C7 | OUTPUT | LVCMOS33 | MAP_TBD |
| SDIO_SW_EN_N | B7 | OUTPUT | LVCMOS33 | MAP_TBD |

### ICICLE_CAN0.pdc

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| CAN_0_TXBUS_M2F | B13 | OUTPUT | LVCMOS33 | MAP_TBD |
| CAN_0_TX_EBL_M2F | A17 | OUTPUT | LVCMOS33 | MAP_TBD |
| CAN_0_RXBUS_F2M | A16 | INPUT | LVCMOS33 | MAP_TBD |

### ICICLE_RPi_MICRON_QSPI.pdc (RPi GPIO + Micron QSPI; preferred RPi variant)

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| RPi_ID_SC | F10 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_ID_SD | B9 | INOUT | LVCMOS33 | MAP_TBD |
| COREI2C_C0_SCL | B8 | INOUT | LVCMOS33 | MAP_TBD |
| COREI2C_C0_SDA | A8 | INOUT | LVCMOS33 | MAP_TBD |
| COREUART_RX | H15 | INPUT | LVCMOS33 | MAP_TBD |
| COREUART_TX | A7 | OUTPUT | LVCMOS33 | MAP_TBD |
| QSPI_CLK | C10 | INOUT | LVCMOS33 | MAP_TBD |
| QSPI_DATA_0 | D13 | INOUT | LVCMOS33 | MAP_TBD |
| QSPI_DATA_1 | G12 | INOUT | LVCMOS33 | MAP_TBD |
| QSPI_DATA_2 | C5 | INOUT | LVCMOS33 | MAP_TBD |
| QSPI_DATA_3 | G15 | INOUT | LVCMOS33 | MAP_TBD |
| QSPI_SEL | H12 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO12 | D9 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO13 | D6 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO16 | C6 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO17 | H17 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO19 | B5 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO20 | C9 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO21 | C4 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO22 | F11 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO23 | F16 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO24 | D14 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO25 | E14 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO26 | B4 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO27 | G17 | INOUT | LVCMOS33 | MAP_TBD |
| RPi_GPIO7_SPI_CE1_N | H13 | INOUT | LVCMOS33 | MAP_TBD |

### ICICLE_MIKROBUS.pdc

| Port | Pin (FCVG484) | Direction | IO_Std | FCSG536e Verdict |
|---|---|---|---|---|
| mBUS_PWM | E11 | OUTPUT | LVCMOS33 | MAP_TBD |
| mBUS_I2C_SCL | F12 | INOUT | LVCMOS33 | MAP_TBD |
| mBUS_I2C_SDA | F13 | INOUT | LVCMOS33 | MAP_TBD |
| mBUS_UART_RX | A21 | INPUT | LVCMOS33 | MAP_TBD |
| mBUS_UART_TX | B20 | OUTPUT | LVCMOS33 | MAP_TBD |
| mBUS_INT | A20 | INPUT | LVCMOS33 | MAP_TBD |
| GPIO_2_M2F_20_AN | D11 | OUTPUT | LVCMOS33 | MAP_TBD |
| GPIO_2_M2F_21_RST | E10 | OUTPUT | LVCMOS33 | MAP_TBD |

### Excluded from recommended subset (conflicts with chosen RPi/QSPI variant)

`ICICLE_I2C_LOOPBACK.pdc` (4 pins): mBUS_I2C_SCL/C9, mBUS_I2C_SDA/B5, I2C1_SCL/D8, I2C1_SDA/B4. Conflicts with ICICLE_RPi_MICRON_QSPI on C9, B5, B4.

`ICICLE_SPI_LOOPBACK.pdc` (4 pins): SPI_0_CLK_PAD/C10, SPI_0_DO/G12, SPI_0_DI/D13, SPI_0_SS/H12. Conflicts with ICICLE_RPi_MICRON_QSPI on all four pins.

`ICICLE_RPi.pdc` (26 pins): Older RPi variant; not recommended (use ICICLE_RPi_MICRON_QSPI for the production board). Differs from ICICLE_RPi_MICRON_QSPI on QSPI_DATA_2 (C9 vs C5) and RPi_GPIO20 (C5 vs C9) — i.e. they swap two balls.

## Resolution path

For each `MAP_TBD` row above, after fetching UG0726:

1. Look up the FCVG484 ball coordinate.
2. Look up whether the same physical pad is exposed on FCSG536e and at which ball.
3. Tag accordingly (`MAP_OK` if same coordinate, `MAP_REROUTE` if different coordinate, `MAP_DROP` if not exposed).
4. Update HW-04c (`libero/constraints/pinout.pdc`) to apply the audit verdicts.

Alternative resolution path (preferred if Libero exposes ES-specific data):

1. Run `01_scaffold_proj.tcl` against Libero 2025.2 in a scratch project targeting `MPFS250T-FCSG536e`.
2. Use Libero's Pin View / Pin Description tool to inspect the FCSG536e ball matrix directly.
3. Cross-reference each FCVG484 ball above with the FCSG536e ball that exposes the same pad (Libero's pin descriptions include pad names that are package-independent).
4. Tag accordingly.

## Decision log

| Date | Phase | Outcome |
|---|---|---|
| 2026-05-02 | HW-04a sync | 18 files (17 PDCs + README) imported from Beelink to spark1 |
| 2026-05-02 | HW-04b partial audit | 120 set_io declarations parsed; intra-bundle conflicts identified; recommended PDC subset selected; all rows tagged MAP_TBD pending UG0726 / Libero DB resolution |
| (TBD) | HW-04b full audit | Complete MAP_OK/REROUTE/DROP verdicts after fetching ball-matrix data |
| (TBD) | HW-04c | Populate `libero/constraints/pinout.pdc` from audited bundle (re-triggers P&R) |
