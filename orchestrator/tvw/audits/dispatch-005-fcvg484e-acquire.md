# Dispatch prompt — Acquire FCVG484E ground truth (paste into ~/projects/skills/ Claude session)

The block below is self-contained: paste it as a single message into the
web-enabled Claude session running in `~/projects/skills/`. That session
has the `research-topic`, `acquire-corpus`, and `process-corpus` skills
plus internet access.

---

```
Context: I have a Tychon Phase I PolarFire SoC Icicle Kit board.
Physical silkscreen reading (verified by user 2026-05-03):

  Base part:   MPFS250T
  Package/grade/version: FCVG484E
  Date code:   2241  (ISO week 41 of 2022)
  Full code:   MPFS250T-FCVG484E

Decoded: MPFS250T die, 484-ball flip-chip BGA package, STD speed grade
(no `-1` prefix), Extended Commercial temperature grade (trailing `E`).

A new corpus skeleton already exists at:

  ~/.corpus/tychon-fpga-mpfs250t-fcvg484e/
    ├── CONTEXT.md       (scope + target source list)
    ├── manifest.json    (empty sources array)
    ├── raw/             (download target)
    ├── processed/       (chunks.db lives here after process-corpus)
    └── meta/            (acquisition.log target)

Pre-flight: confirm the embedding service is healthy before any ingest:
  curl -sf http://spark2:8000/health

TASK — three phases:

PHASE 1: Build a scored source manifest with the `research-topic` skill.
  Topic: "Microchip PolarFire SoC MPFS250T-FCVG484E datasheet UG0726
          pin descriptions errata extended commercial speed grade"
  Required documents (priority 1):
    - UG0726 — PolarFire SoC FPGA and PolarFire SoC FPGA Pin Descriptions
      (this is the MUST-HAVE — confirmed missing from
       ~/.corpus/polarfire-control-corpus/ during prior corpus searches)
    - PolarFire SoC FPGA Datasheet (DS60001702, latest revision letter)
      with FCVG484E-specific switching characteristics, DDR4/transceiver
      tables, Tj operating ranges
    - PolarFire SoC FPGA Errata (ER-document) — capture the rev that
      applies to silicon shipped in late 2022 (date code 2241)

  Useful (priority 2):
    - Microchip Power Estimator .xlsm (v2025.2 PolarFire SoC release):
      https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/power-estimator/3-06-00024__polarfire_power_estimator.xlsm
    - UG0880 — PolarFire SoC FPGA MSS Reference Manual
    - PolarFire SoC FPGA Product Brief (DS60001656 — corpus has rev K;
      verify whether a newer rev exists)
    - Icicle Kit User Guide / Hardware Reference Manual (Microchip page,
      not the github reference design — the HW reference doc)

  Nice-to-have (priority 3):
    - Microchip silicon date-code decoder bulletin / app note
      (to map date-code 2241 to silicon revision letter)
    - PolarFire SoC FPGA Security User Guide

  For each captured source, record: URL, retrieved checksum (SHA-256),
  Microchip publication revision letter, publication date.

PHASE 2: Acquire the manifest with the `acquire-corpus` skill.
  Target directory: ~/.corpus/tychon-fpga-mpfs250t-fcvg484e/raw/
  Expected: PDFs (most), one .xlsm (Power Estimator), some HTML refs.
  PDF→markdown conversion via pandoc/pdftotext per the standard
  acquire-corpus pipeline.
  Redaction: no project secrets are involved here (these are public
  Microchip docs), but still run the standard redactor pass — never
  ingest any local file that wasn't fetched from microchip.com /
  ww1.microchip.com / onlinedocs.microchip.com / github.com/polarfire-soc.

PHASE 3: Process the corpus with `process-corpus`.
  Corpus name: tychon-fpga-mpfs250t-fcvg484e
  Embedding service: http://spark2:8000  (Qwen3-Embedding-4B, 2560-d)
  Output: ~/.corpus/tychon-fpga-mpfs250t-fcvg484e/processed/chunks.db
  Update manifest.json with the final `sources` array.

VERIFICATION QUERIES (run after Phase 3 to confirm coverage):
  1. /search-corpus tychon-fpga-mpfs250t-fcvg484e "FCVG484 ball matrix V19 U18"
     → expect UG0726 hit
  2. /search-corpus tychon-fpga-mpfs250t-fcvg484e "STD speed grade switching characteristics MPFS250T"
     → expect datasheet hit, NOT generic PolarFire SoC family doc
  3. /search-corpus tychon-fpga-mpfs250t-fcvg484e "Extended Commercial Tj operating temperature"
     → expect datasheet/product-brief hit defining the `E` suffix range
  4. /search-corpus tychon-fpga-mpfs250t-fcvg484e "PolarFire SoC errata 2022"
     → expect errata sheet hit

REPORT BACK with:
  - Total chunks ingested + source count
  - Pass/fail on the four verification queries
  - Any P1 documents that could not be obtained (dead links, paywall,
    requires Microchip portal login, etc.)
  - The exact UG0726 revision letter + publication date so the TVW
    audit-005 entry can cite it for Appendix C closeout

CONSTRAINT: this is acquisition only. Do NOT modify any files in
  ~/projects/tychon-verification-workbench/   (TVW is a separate session)
  ~/projects/polarfire-hybrid-control/        (TVW already applied repo corrections)
  ~/Desktop/Shared/tychon-nv-sim-repos/       (TVW maintains the SBIR shared folder)
Only writes go to ~/.corpus/tychon-fpga-mpfs250t-fcvg484e/ and standard
acquire-corpus / process-corpus state directories.
```

---

## After it returns

Bring the report back to the TVW session. We then:

1. Update `audit-005-fpga-package-correction.md` with the realized source list.
2. Re-run the F-001 timing claim through the critic loop using the
   FCVG484E-specific datasheet as evidence.
3. Re-ingest `tychon-docs` to refresh the corrected toolchain reference
   chunk (resolves F-024).
