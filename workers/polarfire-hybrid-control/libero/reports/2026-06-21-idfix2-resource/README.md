# idfix2 Resource Evidence - 2026-06-21

## Source

Copied from bee without modifying the Libero database:

- `~/libero_seedsweep/seed7_vbx201_v250/designer/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt`
- `~/libero_seedsweep/seed7_vbx201_v250/synthesis/synlog/report/MPFS_ICICLE_KIT_BASE_DESIGN_fpga_mapper_resourceusage.rpt`

Local artifact hashes:

```text
494efb308c1d7d41431c8dfef43c5db5e04dd18ca4b73e4662fd76c35119a6dc  MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt
9adec7a6b7e66c8b61532bc14ce212b4c70c1b1c19b25f172d329e919f5847c9  MPFS_ICICLE_KIT_BASE_DESIGN_fpga_mapper_resourceusage.rpt
```

## Device / Package

CONFIRMED from `MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt`:

- Family: PolarFireSoC
- Device: MPFS250T
- Package: FCVG484
- Speed grade: STD
- Part range: EXT

This corrects stale FCVG1152 wording in older mapper summaries. Treat the `fpga_mapper_resourceusage.rpt` part label `mpfs250tfcg1152std` as stale/risky for package naming; the Libero compile report above is the package source used here.

## Resource Table

| Type | Used | Total | Percentage |
|---|---:|---:|---:|
| 4LUT | 67,811 | 254,196 | 26.68% |
| DFF | 66,473 | 254,196 | 26.15% |
| User I/O | 65 | 144 | 45.14% |
| uSRAM | 419 | 2,352 | 17.81% |
| LSRAM | 113 | 812 | 13.92% |
| Math | 109 | 784 | 13.90% |
| H-Chip Global | 13 | 48 | 27.08% |
| PLL | 2 | 8 | 25.00% |
| MSS | 1 | 1 | 100.00% |

## Job Hashes / Rollback Anchors

From bee:

```text
a5550f9e486e19f127aad78e97e06e0839d359c91028d4bcd21bb32b98f5b367  polarfire_hybrid_control_two_slot_demo.job
7907a83f9fc6e99ca25ebc3c389c802d6d07e42b71403767ee644103783dff6e  polarfire_hybrid_control_two_slot_idfix.job
39c8bcf2665ce8b79bcc2abb552ddd2b7b703729d50876744c2cb63c82ca230b  polarfire_hybrid_control_two_slot_idfix2.job
4e3323e8590e0e87aeae2874ff363ed8843966fd4123d502b280ad0ccfb4af8e  polarfire_hybrid_control_vbx201_v250.job
```

Do not program anything until FlashPro/scan-chain visibility and the exact rollback command are recorded.
