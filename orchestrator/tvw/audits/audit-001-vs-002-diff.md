# Audit 001 vs 002 — Verdict Diff

Source: same 97 claims, different evidence corpora.
- audit-001: tychon-docs without Beelink/Microchip artifacts (424 chunks)
- audit-002: tychon-docs after ingesting tychon-artifacts/ (498 chunks)

## Summary

- Total claims: 97
- Verdicts unchanged (both critics): 88
- Verdicts shifted: 9
  - Improved (UNSUPPORTED/WEAK -> SUPPORTED): 1
  - Worsened (SUPPORTED -> WEAK/UNSUPPORTED/CONTRADICTED): 3
  - Lateral (often nemotron ERROR flips): 5

## Improved verdicts (1)

- **c0049** qwen3-coder: `UNSUPPORTED -> SUPPORTED` | nemotron-mini: `SUPPORTED -> SUPPORTED`
  - Claim: "Per-rail breakdown: Rail VDD (1.050 V): 2,244.9 mW (2,138 mA)."
  - audit-002 doc top: ["beelink_final_report_data/smartpower_refdesign.txt", "beelink_final_report_data/smartpower_refdesign.txt", "report/Tychon_Phase_I_Final_Report_2026-04-30.md"]
  - audit-002 qwen rationale: Chunks 0 and 1 explicitly list Rail VDD (1.050 V) at 2,244.9 mW and 2,138 mA.

## Worsened verdicts (3)

- **c0020** qwen3-coder: `SUPPORTED -> UNSUPPORTED` | nemotron-mini: `SUPPORTED -> SUPPORTED`
  - Claim: "The placed netlist confirms the instance survives synthesis: watchdog_timer_0/Primitives consumes 26 LUTs and 20 DFFs per MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_hier_resources.csv."
  - audit-002 doc top: ["beelink_final_report_data/resource_utilization.md", "closure/closure_resources_summary.md", "beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.txt"]
  - audit-001 doc top (for context): ["closure/closure_resources_summary.md", "research_inputs/Tychon_AI_Project_Analysis_and_Evaluation_2026-04-30.md", "phase1_planning/dlog_028_retraction_and_029_closure_2026-04-29.md"]
  - audit-002 qwen rationale: No watchdog_timer_0/Primitives instance found in the provided CSV resource summary.

- **c0039** qwen3-coder: `SUPPORTED -> UNSUPPORTED` | nemotron-mini: `SUPPORTED -> SUPPORTED`
  - Claim: "PLL OUT3        50 MHz          20.000 ns      +1.177 ns      5.9% (PF_CCC_C0_0)"
  - audit-002 doc top: ["beelink_final_report_data/smartpower_refdesign.txt", "report/Tychon_Phase_I_Final_Report_2026-04-30.md", "beelink_final_report_data/smartpower_refdesign.txt"]
  - audit-001 doc top (for context): ["report/Tychon_Phase_I_Final_Report_2026-04-30.md", "web_export/sbir-fasttrack/docs/place-and-route-jitter-report.md", "web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md"]
  - audit-002 qwen rationale: No evidence found for PLL OUT3 at 50 MHz with specified jitter and margin.

- **c0057** qwen3-coder: `SUPPORTED -> CONTRADICTED` | nemotron-mini: `ERROR -> ERROR`
  - Claim: "The worst slack across the design is **+0.728 ns** on the FIC_0 PLL OUT0 (125 MHz / 8 ns) domain, on a path **internal to the integrated PID compute datapath** (nv_pid_top_0/\.../nv_pid_top_pid_integr"
  - audit-002 doc top: ["report/Tychon_Phase_I_Final_Report_2026-04-30.md", "beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r1_s1.txt", "web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md"]
  - audit-001 doc top (for context): ["report/Tychon_Phase_I_Final_Report_2026-04-30.md", "web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md", "closure/CLOSURE_DELIVERABLE.md"]
  - audit-002 qwen rationale: Claim states +0.728 ns slack, but evidence shows +2.107 ns slack on same clock domain.

## Lateral verdicts (5)

- **c0008** qwen3-coder: `SUPPORTED -> SUPPORTED` | nemotron-mini: `ERROR -> SUPPORTED`
  - Claim: "4              Total Power    \<12 W         \~5.2 W        PASS"
  - audit-002 doc top: ["phase1_planning/tychon_phase1_closeout_plan_v3_2026-04-27.md", "web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md", "beelink_final_report_data/smartpower_refdesign.txt"]
  - audit-001 doc top (for context): ["phase1_planning/tychon_phase1_closeout_plan_v3_2026-04-27.md", "web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md", "report/Tychon_Phase_I_Final_Report_2026-04-30.md"]
  - audit-002 qwen rationale: Chunk 0 confirms 5.2 W is FPGA power, and chunk 3 shows total FPGA power is 2,663.9 mW (2.66 W), supporting the claim's power assertion.

- **c0030** qwen3-coder: `SUPPORTED -> SUPPORTED` | nemotron-mini: `SUPPORTED -> ERROR`
  - Claim: "*Proposal Task 3, Days 45--90 \| All data from Libero SoC 2025.2, MPFS250T (FCVG484, STD, 1.05V)*"
  - audit-002 doc top: ["web_export/sbir-fasttrack/docs/tychon-microchip-toolchain-reference.md", "beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.txt", "web_export/sbir-fasttrack/docs/tychon-microchip-toolchain-reference.md"]
  - audit-001 doc top (for context): ["web_export/sbir-fasttrack/docs/tychon-microchip-toolchain-reference.md", "web_export/sbir-fasttrack/docs/tychon-microchip-toolchain-reference.md", "refs/tychon_microchip_toolchain_reference_2026-03-20.md"]
  - audit-002 qwen rationale: Chunk 1 explicitly confirms Libero SoC 2025.2, MPFS250T (FCVG484, STD, 1.05V) match.

- **c0031** qwen3-coder: `SUPPORTED -> SUPPORTED` | nemotron-mini: `SUPPORTED -> ERROR`
  - Claim: "The April 2 baseline numbers (+0.165 ns worst slack across the design, 24.72% LUT, 2,664 mW) and the April 29 r3_s22 paper-shell numbers (+1.215 ns worst slack, 24.71% LUT, 2,672 mW) are not directly "
  - audit-002 doc top: ["beelink_final_report_data/README.md", "phase1_planning/tychon_phase1_decision_log_v1.1_2026-04-30.md", "phase1_planning/phase1_closeout_findings_2026-04-30.md"]
  - audit-001 doc top (for context): ["phase1_planning/tychon_phase1_decision_log_v1.1_2026-04-30.md", "phase1_planning/phase1_closeout_findings_2026-04-30.md", "closure/CLOSURE_DELIVERABLE.md"]
  - audit-002 qwen rationale: Evidence confirms r6_s25 represents integrated design, not paper-shell, with proper timing and resource usage.

- **c0045** qwen3-coder: `SUPPORTED -> SUPPORTED` | nemotron-mini: `SUPPORTED -> ERROR`
  - Claim: "---------------------------------------------------------------------------- **Per-instance         **4LUT**          **DFF**           **MACC (18×18)** hierarchy (rollup)** ---------------------- ---"
  - audit-002 doc top: ["web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md", "report/Tychon_Phase_I_Final_Report_2026-04-30.md", "beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r1_s1.txt"]
  - audit-001 doc top (for context): ["web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md", "report/Tychon_Phase_I_Final_Report_2026-04-30.md", "refs/tychon_microchip_toolchain_reference_2026-03-20.md"]
  - audit-002 qwen rationale: Chunks 0 and 1 explicitly list MSC_i_37 with 2,818 4LUTs, and chunk 4 confirms MACC usage in PID hierarchy.

- **c0093** qwen3-coder: `SUPPORTED -> SUPPORTED` | nemotron-mini: `ERROR -> SUPPORTED`
  - Claim: "Three Phase I markers carry a deferred status (Section 8.6 KPP scorecard): on-board AI inference latency, on-board PID classical latency, and total payload power."
  - audit-002 doc top: ["beelink_apr2/tychon_final_report_v3.md", "web_export/sbir-fasttrack/docs/status.md", "web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md"]
  - audit-001 doc top (for context): ["web_export/sbir-fasttrack/docs/status.md", "phase1_planning/tychon_phase1_closeout_plan_v3_2026-04-27.md", "status/STATUS.md"]
  - audit-002 qwen rationale: Chunk 0 shows AI inference latency is on track, chunk 3 confirms latency markers are split inconsistently, and chunk 4 shows watchdog timeout threshold is 1 ms.

