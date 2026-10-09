# audit-005 — FPGA Package Correction (MPFS250T-FCVG484E)

**Date:** 2026-05-03
**Trigger:** User confirmed physical silkscreen reading: `MPFS250T-FCVG484E`, date code `2241`.
**Scope:** Correct the package designator across the project ground truth and seed a new variant-specific corpus.

## Findings

| ID | Severity | Status | Description |
|---|---|---|---|
| F-018 | CRITICAL | RESOLVED | `01_scaffold_proj.tcl` declared `DEVICE_PACKAGE "FCSG536"` but physical silicon is `MPFS250T-FCVG484E`. Reference design PDC bundle would never validate against the wrong package. **Closed by polarfire-hybrid-control@8d794e5 (2026-05-03).** |
| F-019 | MAJOR | RESOLVED | `PACKAGE_AUDIT.md` (HW-04b) documented 120 pins as `MAP_TBD` based on incorrect HW-01 finding (FCSG536e). With FCVG484E confirmed, all 120 collapse to `MAP_OK`. **Closed by polarfire-hybrid-control@8d794e5.** |
| F-020 | MINOR | RESOLVED | `tychon_microchip_toolchain_reference_2026-03-20.md` line 282 stated "Package \| Commercial (FCSG536 on Icicle Kit)" — incorrect. Canonical doc edited 2026-05-03; corpus chunk re-ingest pending (F-024). |
| F-021 | MAJOR | RESOLVED | Acquisition + indexing complete (skills session, 2026-05-03 ~20:00 UTC). 10/10 sources acquired, **279 chunks across 9 sources** in `~/.corpus/tychon-fpga-mpfs250t-fcvg484e/processed/chunks.db`. Pin Descriptions UG (DS60001692) is the top hit for FCVG484 ball-matrix queries. |
| F-022 | MAJOR | UNBLOCKED | Datasheet DS00004248 indexed (66 chunks). F-001 re-validation can now proceed against STD-grade FCVG484E switching characteristics tables. Tracked as a follow-up audit, not a finding of audit-005. |
| F-023 | MINOR | RESOLVED | Errata 80001031 indexed (4 chunks; small doc). Silicon revision identification: **silkscreen `MPFS250T-FCVG484E` + date-code 2241 → Production silicon Rev 0** per Errata 80001031 §1.2 "Production Validation Status". Applicable Production Rev 0 errata: MSS DDR max-density caveat (DS00005474A), PCIe SECDED defeatured, MSS I²C fabric-mode (requires MSS Configurator v2022.2+), GEM Undersize Frame Counter, External VERIFY_DIGEST + POR Digest deprecated. Citation policy: cite Errata rev C (12/2022) as the contemporaneous rev for date-code 2241; rev F (08/2025, in corpus) is acceptable as a superset — skills session confirmed no errata were removed between revs C and F. |
| F-024 | MINOR | RESOLVED | `~/.corpus/tychon-docs/` raw copy synced from canonical and re-ingested 2026-05-03 (2.3s, 5 chunks replaced, DB stays at 525 total). Verified: corrected line ("FCVG484 on canonical Icicle Kit; trailing `E` = Extended Commercial temperature grade. *Correction 2026-05-03...*") is searchable in chunks.db. Log: `tvw/audits/audit-005-tychon-docs-rerun.log`. |
| F-025 | MINOR | RESOLVED | Dispatch prompt contained two DS-number errors. Skills session caught and corrected: (a) the SoC pin descriptions doc is **DS60001692** (PolarFire SoC FPGA Packaging and Pin Descriptions UG, latest rev E 05/2025; rev C 09/2022 is the date-code-2241 contemporary rev — skills session audited C→D→E for breaking changes to FCVG484 bank locations and pin assignments and found none, so rev E is appropriate ground truth). UG0726 is the non-SoC PolarFire board design guide and was captured anyway as a breadcrumb so future searches that quote the wrong UG number still hit relevant content. (b) The PolarFire SoC datasheet is **DS00004248** (rev E, 05/2025), not DS60001702 — DS60001702 is the MSS Technical Reference Manual (≡ old UG0880); both are correctly cited as separate documents in this corpus. |
| F-026 | INFO | NOTED | Skills session flagged a cosmetic bug in `finalize_acquisition.py`: the global `files_acquired` count (19 = 9 .md + 9 .pdf + 1 .xlsm) is attributed to every source individually rather than per-source. chunks.db count and file ledger are correct; only the per-source manifest field is misleading. Follow-up to file against the corpus pipeline, not a TVW issue. |

## Corrections applied (this session)

1. `~/projects/polarfire-hybrid-control/libero/scripts/01_scaffold_proj.tcl`
   — `set DEVICE_PACKAGE "FCSG536"` → `"FCVG484"`, with provenance comment
   citing silkscreen + Beelink log.
2. `~/projects/polarfire-hybrid-control/libero/constraints/icicle_reference/PACKAGE_AUDIT.md`
   — `SUPERSEDED 2026-05-03` banner added; all 120 pins reclassified `MAP_OK`.
3. `~/projects/polarfire-hybrid-control/libero/constraints/icicle_reference/README.md`
   — "Package mismatch" decision branch closed (RESOLVED, not open question).
4. `~/Desktop/Shared/tychon-nv-sim-repos/07_technical_references/tychon_microchip_toolchain_reference_2026-03-20.md`
   — line 282 corrected with inline `Correction 2026-05-03` marker.
5. `~/.corpus/tychon-fpga-mpfs250t-fcvg484e/` — new corpus skeleton
   created (`raw/`, `processed/`, `meta/`, `CONTEXT.md`, `manifest.json`).

## External acquisition (dispatched)

External document fetch (UG0726, datasheet, errata, etc.) is **out of
scope for TVW** under the air-gap rule. Dispatched to a separate
web-enabled Claude session in `~/projects/skills/`. The acquisition
prompt is in `tvw/audits/dispatch-005-fcvg484e-acquire.md`.

## Follow-up tasks

1. **Re-ingest `tychon-docs`** to refresh the toolchain reference chunk
   after the F-020 correction (resolves F-024).
2. **Re-run audit-001 F-001 timing claim** against STD-grade FCVG484E
   tables in datasheet DS00004248 (Tables 5-37 GPIO buffer speed and
   the AC switching tables, per skills-session callout). Tracks as
   audit-006 / fix-list amendment, not a residual F-022.
3. **Cite policy for Appendix C closeout:** use Errata 80001031 rev C
   (12/2022) as the contemporaneous citation for date-code 2241
   silicon. Rev F (08/2025) in corpus is acceptable as superset.

## Acquisition + indexing log (skills session, 2026-05-03)

10 sources requested, 10 acquired (9 PDF/.md + 1 binary `.xlsm`).
Total processing time 82.4 s (chunk + embed + index). Embedding model
Qwen3-Embedding-4B @ Spark 2 (2560-d). DB at
`~/.corpus/tychon-fpga-mpfs250t-fcvg484e/processed/chunks.db`.

| Source | Chunks |
|---|---:|
| polarfire_soc_fpga_mss_technical_reference_manual_VC_DS60001702.md | 105 |
| polarfire_soc_fpga_datasheet_DS00004248.md | 66 |
| polarfire_soc_product_overview_60001656_revK.md | 33 |
| polarfire_soc_fpga_board_design_guidelines_ug0901_vb.md | 21 |
| polarfire_fpga_board_design_user_guide_ug0726_v11.md | 20 |
| polarfire_soc_packaging_and_pin_descriptions_ug_vb_DS60001692.md | 15 |
| polarfire_soc_fpga_icicle_kit_user_guide_vb.md | 12 |
| polarfire_soc_fpga_devices_errata_80001031.md | 4 |
| polarfire_soc_icicle_kit_quickstart_guide_50003930.md | 3 |
| polarfire_power_estimator_v2025-2.xlsm | n/a (binary, passthrough) |
| **Total** | **279** |

### Verification queries — 4/4 PASS

| # | Query | Top hit | Verdict |
|---|---|---|---|
| 1 | `FCVG484 ball matrix V19 U18` | DS60001692 (3 of top-3) | PASS |
| 2 | `STD speed grade switching characteristics MPFS250T` | DS00004248 | PASS — datasheet, not generic family |
| 3 | `Extended Commercial Tj operating temperature` | DS00004248 | PASS — exact "0–100 °C TJ" definition surfaced |
| 4 | `PolarFire SoC errata 2022` | 80001031 (rank 1, 3) | PASS |

### P1 source revisions (for Appendix C citations)

| Doc | Microchip ID | Latest acquired rev | Contemporaneous-to-2241 rev |
|---|---|---|---|
| Pin Descriptions UG | DS60001692 | rev E, 05/2025 | rev C, 09/2022 (audited C→E, no breaking changes to FCVG484 bank/pin tables) |
| Datasheet | DS00004248 | rev E, 05/2025 | initial rebrand at rev A, 10/2022 |
| Errata | 80001031 | rev F, 08/2025 | rev C, 12/2022 (rev F is superset; no errata removed between C and F) |

### P3 nice-to-have not obtained

- Security User Guide — `www.microchip.com/content/dam/...` returns 403 (DAM gating). Workaround: pull from ww1.microchip.com mirror in a future refresh if needed.
- Date-code decoder bulletin — Microchip publishes "Package Marking Information" inline in each datasheet rather than as a standalone bulletin. The `YYWW` convention is documented in DS00004248 itself and in onlinedocs.microchip.com. **Date-code 2241 = 2022 ISO week 41 (Oct 10–16, 2022)** is fully sourced from docs already in the corpus.

## Decision-log impact

This finding does **not** invalidate the v3.1 report's resource numbers
(those came from actual MPFS250T compile runs, not package-derived
estimates) but does affect any timing/power claim that referenced
package-specific tables. Cross-check after audit-005 ingest completes.
