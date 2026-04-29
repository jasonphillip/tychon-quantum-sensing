# Log Archaeology Findings — `MPFS_ICICLE_Vectorblox` Silent-Load Crash

**Branch**: decision-2-option-c
**Investigation date**: 2026-04-29
**Status**: Phase A complete — root cause identified, pristine recovery vector available
**Working plan**: `~/.claude/plans/you-are-working-in-sequential-lobster.md`

---

## Bottom line (TL;DR)

The 2026-04-28 12:00:41 failed-PnR save event **truncated multiple project
files mid-write** — the prjx ends inside an unfinished `SUBBLOCK` declaration,
and `tooldata/MPFS_ICICLE_Vectorblox.msg` was cut from 1,069,254 bytes to 211
bytes (99.98% lost). Libero's open-project routine silently terminates while
trying to consume the truncated structures, with the crash position fixed at
file-iteration index 627 by the deterministic file-iteration loop hitting the
broken metadata.

**A pristine recovery is available**: 4 VSS shadow copies dated 2026-04-27
12:34–12:36 contain the project files in their pre-corruption April 2 baseline
state. Recovery path is described in `LOAD_CRASH_FIX_PLAN.md`.

This rules out:
- File-content corruption (every `hdl/*.v` is pristine ASCII, `mtime 2026-04-02`)
- B1 prjx surgery as the fix (the `nv_pid_top` absolute-path entry is benign;
  removing it doesn't address the actual truncation)
- B2 designer-state cleanup as the fix (the corruption is in the prjx + .msg,
  not in `designer/MPFS_ICICLE_KIT_BASE_DESIGN/`)
- B5 project-clone diagnosis (B5 carried the corruption with it because it
  copied the truncated files)

---

## Targeted lead (entering Phase A)

The stdout truncation in every load attempt happens **mid-write of a
"Reading file..." line** that immediately follows `hdl/miv_ihcc.v`. Cross-
referencing the working overlay session log (`libero/reports/2026-04-28/
overlay_session.log`):

```
overlay_session.log line 626: Reading file '...\hdl\miv_ihcc.v'.        ← last line in crash log
overlay_session.log line 627: Reading file '...\hdl\miv_ihcc_ctrl.v'.   ← truncated mid-write
```

Confidence going in: medium. The fault could be in the file content OR in
parser context around iteration position 627. Phase A's job: figure out which.

---

## Phase A side action — WerFault local crash dumps  ✅ DONE

Set in `HKCU` (libero.exe runs as user `jason`):

```
HKEY_CURRENT_USER\Software\Microsoft\Windows\Windows Error Reporting\LocalDumps
    DumpFolder    REG_EXPAND_SZ    C:\CrashDumps
    DumpType      REG_DWORD        0x2  (full dump)
    DumpCount     REG_DWORD        0xa
```

`C:\CrashDumps` directory created. Future silent libero.exe crashes will
deposit `.dmp` files here automatically.

**Note for future sessions**: `MSYS_NO_PATHCONV=1` must be set before
`reg add` from MINGW64 Bash, else MSYS mangles registry-path backslashes.

Pre-existing key `HKLM\...\LocalDumps\EffectsServer_Service.exe` was untouched.

---

## A0 — Targeted lead verification  ✅ DONE

### A0.0 — GUI dialog test  ⚠️ Pending user

User must run File → Open Project on the prjx in Libero GUI and report any
modal dialog text. Read-only — cancel without modifying state. Important
because the CLI silently dismisses dialogs that the GUI surfaces.

### A0.1 — `hdl/` mtime audit  ✅

ALL 9 files in `hdl/` have mtime `2026-04-02 10:45:05–06`. **None modified
during the 2026-04-28 12:00:41 incident.** The directory itself wasn't
touched either; only the parent `..` (project root) shows a `2026-04-28
16:42:55` mtime from later session activity.

### A0.2 — `miv_ihcc_ctrl.v` structure  ✅

```
File:    hdl/miv_ihcc_ctrl.v
Size:    14,312 bytes
Lines:   412
Encoding: ASCII text (per `file`)
Head:    standard Microchip 2021 copyright comment
Tail:    `endmodule`  ← clean termination
```

No truncation, no NUL bytes, no UTF-16 BOM. Structurally identical to its
siblings.

### A0.3 — Binary anomaly scan  ✅

`file miv_ihcc_ctrl.v miv_ihcc.v miv_ihcc_mem.v miv_ihcc_irqs.v` →
all `ASCII text`. No anomalies.

### A0.4–A0.5 — Pristine reference  (skipped, superseded)

Skipped: A0.1 + A0.3 already proved file pristine; pristine-reference diff
would only confirm what's already known. Time saved redirected to A1+A6.

### A0.6 — Stdout truncation tail  ✅

Pulled all 9 load-attempt logs from Beelink `(~/dev/projects/polarfire-hybrid-
control/libero/reports/)`:

| Log | Bytes | Lines | Tail |
|---|---:|---:|---|
| `_loadonly.log`     | 139,890 | 626 | `...miv_ihcc.v'.\nRea` |
| `_loadonly2.log`    | 139,890 | 626 | (same) |
| `_loadonly3.log`    | 139,890 | 626 | (same) |
| `_pdc_rerun.log`    | 139,890 | 626 | (same) |
| `_inline.log`       | 139,890 | 626 | (same) |
| `_pipeline.log`     | 139,890 | 626 | (same) |
| `_smoke.log`        | 139,891 | 627 | `...miv_ihcc_ctrl.v'.\nRe` |
| `_buftest.log`      |     74  |   1 | (test failure, not a load) |
| `_jobrestore.log`   |    167  |   4 | (B3 .job restore attempt — empty error) |

`_smoke.log` (executed `open + import_files (fp_pdc) + save`) flushes one
more buffered "Reading file" line than the bare `open + close` of `_loadonly.log`.
Same crash signature; different stdout buffer flush amounts. The crash is
during the file-iteration loop's *transition* between entries, not on a
specific file's read.

**Reframing from A0**: file content is irrelevant — the crash is in
parser-iteration / metadata-consumption logic that runs DURING file iteration.

---

## A1 — Project-internal logs  ✅ DONE

### tooldata/

| File | Bytes | mtime | Notes |
|---|---:|---|---|
| `MPFS_ICICLE_Vectorblox.msg` | **211** | 2026-04-28 12:00:41.123 | **TRUNCATED — see below** |
| `MPFS_ICICLE_KIT_BASE_DESIGN_tools.xml` | 216,558 | 2026-04-28 12:00:41.162 | Single-line XML, ends well-formed at `</toolSetting>`; missing 5,893 bytes vs shadow |
| `MPFS_ICICLE_Vectorblox.log` | 542 | 2026-04-02 11:53:42 | Pristine; project info, MPFS250T-FCVG484E confirmed |

### designer/MPFS_ICICLE_KIT_BASE_DESIGN/

Files modified at 12:00:32–12:00:41 (failed-PnR layout state):
- `.afl` (23.9 MB), `.loc` (3.5 MB), `.seg` (1.4 MB), `.dtf/`
- `_iterate_seed.txt`, `_iterate_seedindex.txt` (4 bytes each)
- 20 timing seed reports `_timing_r2_s2..s21.rpt` all 15 bytes (= placement-failure empty content)

B2 already tested removing all this (renamed `MPFS_ICICLE_KIT_BASE_DESIGN/`
aside, same crash). **Designer state is NOT the cause.**

### synthesis/

All from 11:46–11:52 (morning overlay synthesis — successful). Untouched by
the 12:00 failed-PnR save event:
- `.srr` 2.3 MB, `.vm` 36.5 MB, `.fse`, `.htm`, etc.
- `.recordref` 0 bytes (mtime 11:47:19)

Synthesis state predates the corruption. Not a contributor.

---

## A6 — prjx hash and structural diff  ✅ DONE

### Hashes (current state on Beelink)

| File | Bytes | mtime | SHA-256 |
|---|---:|---|---|
| `MPFS_ICICLE_Vectorblox.prjx` | 178,303 | 2026-04-28 16:57:27 | `3ecca6aa49…` |
| `prjx.bak-b1` | 178,303 | 2026-04-28 12:00:41 | `3ecca6aa49…` |
| `prjx.bak-pre-loadtest-20260428-163808` | 178,303 | 2026-04-28 16:38:08 | `3ecca6aa49…` |

**All three byte-identical.** The end-of-session rollback to
`bak-pre-loadtest` was complete; B1's surgical edit (purportedly removing 5
lines for the absolute-path entry) was either reverted or never persisted —
the live prjx still contains the `nv_pid_top` absolute-path entry at line
2656. The mtime differences (12:00:41 / 16:38:08 / 16:57:27) reflect copy
preservation of source mtimes, not actual content differences.

### Structural anomaly: prjx ends mid-line

```
last line of live prjx:
SUBBLOCK "caxi4interconnect_DownConverter::work","component\Actel\
DirectCore\COREAXI4INTERCONNECT\2.9.100\rtl\vlog\core\Axi4Convertors\
DownConverter.v",
                          ↑ trailing comma; no closing "FALSE","FALSE",
                            no trailing newline
```

This is a **textbook partial-write corruption**. The 2026-04-28 12:00:41 save
was cut off mid-write of a `SUBBLOCK` declaration in the `NewModulesInfo`
section.

### Live prjx scan for absolute-path / cross-repo references

```
2656: VALUE "~\dev\projects\tychon-polarfire-control\hls\
            hls_output\rtl\nv_pid_top_nv_pid_top.v,hdl"
        STATE="utd"  TIME="1777390997"  SIZE="257368"
```

Single occurrence of `nv_pid_top`. The referenced absolute-path file
**exists** on Beelink (verified: `~/dev/projects/tychon-polarfire-
control/hls/hls_output/rtl/nv_pid_top_nv_pid_top.v`, 257,368 bytes,
mtime Apr 28 11:43). TIME=1777390997 in the prjx matches that mtime exactly.
**The entry is internally consistent.** It points at the OLD repo (before the
Apr 4 rename to `polarfire-hybrid-control`), but the file is present and
parseable. The morning April 28 overlay session read this file at log line
631 with no error.

### Live prjx FileManager structure (lines 68–2661)

- 542 VALUE entries total, broken down by type:
  - 194 `hdl`
  - 177 `tb_hdl`
  - 77 `actgen_cxf`
  - 47 `sim`
  - 23 `do`
  - 15 `io_pdc`
  - 5 `sdc`
  - 1 each: `syn_vm`, `syn_sdc`, `so`, `prj`, `log`, `fp_pdc`
- Lines 2492–2512: the 5 `<project>\hdl\miv_ihcc*` entries are structurally
  identical to neighbors (VALUE / STATE="utd" / TIME / SIZE / ENDFILE).
  Each SIZE matches the on-disk file size. Internally consistent.
- Line 2656: the absolute-path `nv_pid_top` entry (above), the LAST entry in
  the FileManager list before `ENDLIST`.

The FileManager LIST itself parses correctly. The truncation is **further
into the prjx**, in the `NewModulesInfo` section. But Libero's open_project
must read the entire file to validate it; encountering the partial SUBBLOCK
mid-line at EOF is what kills it.

---

## A5 — VSS shadow copies  🎯 PRISTINE RECOVERY AVAILABLE

```
vssadmin list shadows  →  4 shadow copies, all from 2026-04-27 12:34–12:36 PM
                          (the day BEFORE the failed PnR)
  HarddiskVolumeShadowCopy1  4/27/2026 12:34:42 PM
  HarddiskVolumeShadowCopy2  4/27/2026 12:35:20 PM
  HarddiskVolumeShadowCopy3  4/27/2026 12:35:56 PM
  HarddiskVolumeShadowCopy4  4/27/2026 12:36:33 PM
```

All 4 shadows hold IDENTICAL pristine state (file mtimes preserved from
2026-04-02, indicating the project was untouched between the Apr 2 baseline
and the April 27 snapshot):

| File | Live (broken) | Shadow (pristine) | Δ |
|---|---:|---:|---:|
| `MPFS_ICICLE_Vectorblox.prjx` | 178,303 | 363,261 | **−51%** |
| `MPFS_ICICLE_KIT_BASE_DESIGN_tools.xml` | 216,558 | 222,451 | −3% |
| **`MPFS_ICICLE_Vectorblox.msg`** | **211** | **1,069,254** | **−99.98%** |

### .msg truncation deep-dive

The current `.msg` is NOT a byte-prefix of the shadow — they diverge at
byte 184. But their structures show what the format is supposed to look like:

**Live (211 bytes, 2 lines):**
```
HelpInfo,C:\Microchip\Libero_SoC_2025.2\...\assistant
Implementation;Place and Route;RootName:                         ← header only,
                                                                   no body
```

**Shadow (1,069,254 bytes, 2,108 lines):**
```
HelpInfo,C:\Microchip\Libero_SoC_2025.2\...\assistant
Implementation;Synthesis||CD140||@N: Using the VHDL 2008 Standard …
   …2106 more tool-message lines…
Implementation;Place and Route||(null)||Please refer to the log file for
   details about 25 Info(s)||MPFS_ICICLE_KIT_BASE_DESIGN_layout_log.log;
   liberoaction://open_report/file/MPFS_ICICLE_KIT_BASE_DESIGN_layout_log.log||
   (null);(null)
```

The `.msg` file is the **Libero implementation message catalog** —
synthesis/PnR tool messages indexed for the Reports view, with hyperlinks
into log files. The live version has only the prefix line and a partial
"RootName:" header, with NO message body. This is direct evidence of an
aborted save mid-`.msg` rewrite.

---

## A7 — Already-on-Spark1 evidence  ✅

`libero/reports/2026-04-28/overlay_session.log` (319,910 bytes) gave us:
- The successful Phase-1 file iteration (lines 1–631 of "Reading file…")
- The transition point ("The MPFS_ICICLE_Vectorblox project was opened.")
- Phase-2 reads starting at line 633 with `CLK_DIV.v`
- Confirmation that the absolute-path `nv_pid_top` entry was successfully
  read at line 631 in the working session

`libero/reports/2026-04-28/MPFS_ICICLE_KIT_BASE_DESIGN_*.{rpt,csv,txt}` — 9
files, all from 2026-04-28 12:02. Synthesis-stage outputs (compile_netlist,
cdc, dsp, ram, fanout, iteration_summary). Useful for resource accounting in
the Phase I report; nothing relevant to the load-crash investigation.

---

## A2/A3/A4 — broader log sweep  Skipped

Smoking gun was definitive after A1 + A5 + A6. AppData / install logs /
Windows event sources would not improve the recovery plan and would only
extend the investigation past its time budget. Skipped per the plan's
`A→B→C transition` decision criterion.

---

## Smoking gun summary

### What broke

The **2026-04-28 12:00:41 failed-PnR save event was a non-graceful Libero
process termination during the cleanup save**. It left two project-metadata
files truncated mid-write:

1. **`MPFS_ICICLE_Vectorblox.prjx`** (363 KB → 178 KB, **51% lost**) —
   ends mid-`SUBBLOCK` declaration with no closing tokens or newline.
2. **`tooldata/MPFS_ICICLE_Vectorblox.msg`** (1,069 KB → 211 bytes,
   **99.98% lost**) — only the `HelpInfo` line and a partial section header
   remain.
3. *Marginally:* `tools.xml` is 5,893 bytes shorter than shadow but ends in
   a well-formed XML closing tag, so it's likely just a session-state delta
   rather than truncation. Still worth replacing with the pristine version.

### Why every load crashes deterministically at index 627

`open_project` reads the entire prjx for validation. The truncated
`SUBBLOCK` line in the `NewModulesInfo` section is malformed structure that
Libero's parser cannot accept; it either calls `terminate()` on an unhandled
parser exception, hits a heap fast-fail, or aborts via `__fastfail` —
producing no Application Error event log entry and no WerFault dump (until
the side-action HKCU LocalDumps registry edit, which is now in place for
future sessions).

Why position 627 specifically: by that point Libero has logged 626
"Reading file…" lines via stdio. Process death flushes whatever's in the
buffer; the next "Reading file…" line either gets partial-flushed ("Rea") or
fully-flushed-plus-partial-next-line ("Reading file…\nRe") depending on
script-driven timing. **Position 627 isn't where the parser fails — it's
where the stdio buffer is when the parser-side failure-handler aborts.**

### Why prior surgical attempts failed

- **B1 (remove the 5-line absolute-path entry)** was operating on the wrong
  hypothesis. The absolute-path entry is internally consistent and was read
  cleanly by the morning overlay. Removing it doesn't fix the truncated
  SUBBLOCK at the file's end. Either way the rollback at end-of-session
  reverted any B1 effect (current prjx === bak-b1 byte-for-byte).
- **B2 (rename designer/MPFS_ICICLE_KIT_BASE_DESIGN/ aside)** addressed
  PnR layout state, which isn't on the open_project read path.
- **B3 (.job file restore)** — `.job` is a programmer/bitstream archive, not
  a project archive. Correctly identified as not applicable.
- **B4 (fresh-project from MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl)** — separate
  install bug (ES-targeted ICICLE_MSS.cxf). Independent of the load crash.
- **B5 (project clone)** — copies the corrupt prjx + .msg into the clone.
  Travels with the files, as expected.

### Why this wasn't caught earlier

The morning overlay session log file `_*.log` is in stdout and never
includes a "save complete" marker because the failed-PnR save aborted the
process before the marker could be written. Any subsequent diagnostic that
relied on the prjx as the source of truth would inherit the truncation
without any obvious flag.

---

## Recommended next step

See `LOAD_CRASH_FIX_PLAN.md` for the recovery plan. Headline: restore from
VSS HarddiskVolumeShadowCopy4 (any of the 4 work — they're identical), re-
apply the decision-2-c overlay (committed in git), re-run pipeline. The PDC
fix (`decision-2-option-c.pdc` with `set_location -fixed true` for
`XCVR_REF_CLK`) is committed and ready, so PRPF_009 should not recur.
