# Audit 002 vs 003 — Verdict Diff

audit-002 = with r1_s1 baseline AND r6_s25 (versioning conflict)
audit-003 = r1_s1 archived, r6_s25 hier CSV + closure timing reports added

## Summary

- Claims: 97  Unchanged: 92  Shifted: 5
  - Improved: 1  Worsened: 1  Lateral: 3

## Improved (1)

- **c0057** qwen: `CONTRADICTED -> SUPPORTED` | nemo: `ERROR -> SUPPORTED`
  - Claim: "The worst slack across the design is **+0.728 ns** on the FIC_0 PLL OUT0 (125 MHz / 8 ns) domain, on a path **internal to the integrated PID compute datapath** (nv_pid_top_0/\.../nv_pid_top_pid_integr"
  - audit-003 doc top: ["report/Tychon_Phase_I_Final_Report_2026-04-30.md", "spark1_r6_s25_closure/MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max_r6_s25.txt", "spark1_r6_s25_closure/MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max_r6_s25.txt"]
  - audit-003 qwen rationale: Evidence confirms +0.728 ns slack on FIC_0 PLL OUT0 domain and specifies internal PID datapath path delay.

## Worsened (1)

- **c0033** qwen: `SUPPORTED -> CONTRADICTED` | nemo: `SUPPORTED -> SUPPORTED`
  - Claim: "On the FIC_0 clock domain at 125 MHz, the PID achieves a worst-case path delay of 5.893 ns with +2.107 ns positive slack."
  - audit-003 doc top: ["report/Tychon_Phase_I_Final_Report_2026-04-30.md", "spark1_r6_s25_closure/MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max_r6_s25.txt", "spark1_r6_s25_closure/MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max_r6_s25.txt"]
  - audit-003 qwen rationale: Timing analysis shows worst-case delays exceed 5.893 ns and slack is negative, contradicting the claim.

## Lateral (3)

- **c0031** qwen: `SUPPORTED -> SUPPORTED` | nemo: `ERROR -> SUPPORTED`
  - Claim: "The April 2 baseline numbers (+0.165 ns worst slack across the design, 24.72% LUT, 2,664 mW) and the April 29 r3_s22 paper-shell numbers (+1.215 ns worst slack, 24.71% LUT, 2,672 mW) are not directly "
  - audit-003 doc top: ["phase1_planning/tychon_phase1_decision_log_v1.1_2026-04-30.md", "phase1_planning/phase1_closeout_findings_2026-04-30.md", "closure/CLOSURE_DELIVERABLE.md"]
  - audit-003 qwen rationale: Evidence confirms r6_s25 reflects integrated design, not paper-shell, with verified PID datapath and post-P&R numbers.

- **c0043** qwen: `SUPPORTED -> SUPPORTED` | nemo: `SUPPORTED -> ERROR`
  - Claim: "------------------------------------------------------------------------------ **Resource**   **Used**       **Available**   **Utilization**   **Note** -------------- -------------- --------------- --"
  - audit-003 doc top: ["beelink_final_report_data/resource_utilization.md", "beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.txt", "closure/closure_resources_summary.md"]
  - audit-003 qwen rationale: Chunk 0 explicitly reports 4LUT usage as 62,837, close to the claimed 65,834.

- **c0045** qwen: `SUPPORTED -> SUPPORTED` | nemo: `ERROR -> SUPPORTED`
  - Claim: "---------------------------------------------------------------------------- **Per-instance         **4LUT**          **DFF**           **MACC (18×18)** hierarchy (rollup)** ---------------------- ---"
  - audit-003 doc top: ["web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md", "report/Tychon_Phase_I_Final_Report_2026-04-30.md", "refs/tychon_microchip_toolchain_reference_2026-03-20.md"]
  - audit-003 qwen rationale: Chunks 0 and 1 explicitly list nv_pid_top_0 with 25 MACC blocks, matching the claim.

