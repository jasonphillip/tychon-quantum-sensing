# Truncation Forensics — `MPFS_ICICLE_Vectorblox` Project File Corruption

**Captured**: 2026-04-29 (before any restore)
**Sources**:
- Live: `C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\Icicle_SoC\ref_design\MPFS_ICICLE_Vectorblox\…`
- Shadow: VSS `\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy4` (snapshot 2026-04-27 12:36:33), file mtimes from 2026-04-02

This document is the durable byte-level evidence of the 2026-04-28 12:00:41 save corruption. It exists so that future readers (any of: us, future collaborators, Microchip support) can verify the diagnosis from the bytes themselves rather than relying on the deduction in `LOG_ARCHAEOLOGY_FINDINGS.md`.

---

## Summary

| File | Live size | Shadow size | Delta | Truncated? |
|---|---:|---:|---:|---|
| `MPFS_ICICLE_Vectorblox.prjx` | 178,303 | 363,261 | −184,958 (−51%) | **YES — ends mid-line** |
| `tooldata/MPFS_ICICLE_Vectorblox.msg` | 211 | 1,069,254 | −1,069,043 (−99.98%) | **YES — header only** |
| `tooldata/MPFS_ICICLE_KIT_BASE_DESIGN_tools.xml` | 216,558 | 222,451 | −5,893 (−3%) | NO — both well-formed |

**`tools.xml` is NOT truncated** — both live and shadow end with `</toolSetting>` (identical 128-byte tail; see hex dump below). The 5,893-byte delta is legitimate session-state evolution between the 2026-04-27 shadow and the 2026-04-28 morning overlay session. Restoring it is **optional**; we omit it from the recovery to preserve any valid tool-config changes the overlay session made.

---

## prjx — TRUNCATED MID-LINE

### Live prjx final 256 bytes

The file ends abruptly with a comma after `DownConverter.v"` — no closing `,"FALSE","FALSE"`, no `\r\n`, no further sections. No EOF marker, no `ENDLIST`.

```
0002B77F: 65 63 74 43 6F 72 65 5C 43 4F 52 45 41 58 49 34    |ectCore\COREAXI4|
0002B78F: 49 4E 54 45 52 43 4F 4E 4E 45 43 54 5C 32 2E 39    |INTERCONNECT\2.9|
0002B79F: 2E 31 30 30 5C 72 74 6C 5C 76 6C 6F 67 5C 63 6F    |.100\rtl\vlog\co|
0002B7AF: 72 65 5C 41 78 69 34 43 6F 6E 76 65 72 74 6F 72    |re\Axi4Convertor|
0002B7BF: 73 5C 4D 73 74 72 44 61 74 61 57 69 64 74 68 43    |s\MstrDataWidthC|
0002B7CF: 6F 6E 76 2E 76 22 2C 22 46 41 4C 53 45 22 2C 22    |onv.v","FALSE","|
0002B7DF: 46 41 4C 53 45 22 0D 0A 53 55 42 42 4C 4F 43 4B    |FALSE"..SUBBLOCK|
0002B7EF: 20 22 63 61 78 69 34 69 6E 74 65 72 63 6F 6E 6E    | "caxi4interconn|
0002B7FF: 65 63 74 5F 44 6F 77 6E 43 6F 6E 76 65 72 74 65    |ect_DownConverte|
0002B80F: 72 3A 3A 77 6F 72 6B 22 2C 22 63 6F 6D 70 6F 6E    |r::work","compon|
0002B81F: 65 6E 74 5C 41 63 74 65 6C 5C 44 69 72 65 63 74    |ent\Actel\Direct|
0002B82F: 43 6F 72 65 5C 43 4F 52 45 41 58 49 34 49 4E 54    |Core\COREAXI4INT|
0002B83F: 45 52 43 4F 4E 4E 45 43 54 5C 32 2E 39 2E 31 30    |ERCONNECT\2.9.10|
0002B84F: 30 5C 72 74 6C 5C 76 6C 6F 67 5C 63 6F 72 65 5C    |0\rtl\vlog\core\|
0002B85F: 41 78 69 34 43 6F 6E 76 65 72 74 6F 72 73 5C 44    |Axi4Convertors\D|
0002B86F: 6F 77 6E 43 6F 6E 76 65 72 74 65 72 2E 76 22 2C    |ownConverter.v",|   ← EOF (no continuation)
```

The final byte (`,`) is at offset `0x2B87E` (= 178,302 decimal); the file is 178,303 bytes total.

### Shadow prjx at the same byte offset (showing the proper continuation)

The shadow shows what should follow: `,"FALSE","FALSE"\r\n` then more `SUBBLOCK` entries:

```
0002B83F: 6C 5C 44 69 72 65 63 74 43 6F 72 65 5C 43 4F 52    |l\DirectCore\COR|
…
0002B89F: 22 2C 22 46 41 4C 53 45 22 2C 22 46 41 4C 53 45    |","FALSE","FALSE|
0002B8AF: 22 0D 0A 53 55 42 42 4C 4F 43 4B 20 22 63 61 78    |"..SUBBLOCK "cax|
0002B8BF: 69 34 69 6E 74 65 72 63 6F 6E 6E 65 63 74 5F 43    |i4interconnect_C|
0002B8CF: 44 43 5F 46 49 46 4F 3A 3A 77 6F 72 6B 22 2C 22    |DC_FIFO::work","|
…
```

So mid-write, Libero was emitting an `Axi4Convertors\DownConverter.v` SUBBLOCK reference. The next ~185 KB of content (more SUBBLOCK entries plus final list-closing structure) was lost.

### Shadow prjx final 256 bytes (proper closing structure)

```
00058A1D: 22 0D 0A 45 4E 44 4C 49 53 54 0D 0A 4C 49 53 54    |"..ENDLIST..LIST|
00058A2D: 20 54 69 6D 69 6E 67 54 61 62 4C 69 73 74 0D 0A    | TimingTabList..|
00058A3D: 56 41 4C 55 45 20 22 63 6F 6E 73 74 72 61 69 6E    |VALUE "constrain|
00058A4D: 74 5C 4D 50 46 53 5F 49 43 49 43 4C 45 5F 4B 49    |t\MPFS_ICICLE_KI|
00058A5D: 54 5F 42 41 53 45 5F 44 45 53 49 47 4E 5F 64 65    |T_BASE_DESIGN_de|
00058A6D: 72 69 76 65 64 5F 63 6F 6E 73 74 72 61 69 6E 74    |rived_constraint|
00058A7D: 73 2E 73 64 63 22 0D 0A 56 41 4C 55 45 20 22 63    |s.sdc"..VALUE "c|
00058A8D: 6F 6D 70 6F 6E 65 6E 74 5C 77 6F 72 6B 5C 49 43    |omponent\work\IC|
00058A9D: 49 43 4C 45 5F 4D 53 53 5C 49 43 49 43 4C 45 5F    |ICLE_MSS\ICICLE_|
00058AAD: 4D 53 53 2E 73 64 63 22 0D 0A 56 41 4C 55 45 20    |MSS.sdc"..VALUE |
00058ABD: 22 63 6F 6E 73 74 72 61 69 6E 74 5C 66 69 63 5F    |"constraint\fic_|
00058ACD: 63 6C 6F 63 6B 73 2E 73 64 63 22 0D 0A 45 4E 44    |clocks.sdc"..END|
00058ADD: 4C 49 53 54 0D 0A 4C 49 53 54 20 46 44 43 54 61    |LIST..LIST FDCTa|
00058AED: 62 4C 69 73 74 0D 0A 45 4E 44 4C 49 53 54 0D 0A    |bList..ENDLIST..|
```

The shadow ends with proper `ENDLIST` and `\r\n` after `LIST FDCTabList`. Live has none of this.

---

## .msg — TRUNCATED, ONLY HEADER REMAINS

### Live `.msg` full content (all 211 bytes)

```
00000000: 48 65 6C 70 49 6E 66 6F 2C 43 3A 5C 4D 69 63 72    |HelpInfo,C:\Micr|
00000010: 6F 63 68 69 70 5C 4C 69 62 65 72 6F 5F 53 6F 43    |ochip\Libero_SoC|
00000020: 5F 32 30 32 35 2E 32 5C 4C 69 62 65 72 6F 5F 53    |_2025.2\Libero_S|
00000030: 6F 43 5C 53 79 6E 70 6C 69 66 79 5F 50 72 6F 5C    |oC\Synplify_Pro\|
00000040: 6C 69 62 5C 68 74 6D 6C 2C 66 70 67 61 68 65 6C    |lib\html,fpgahel|
00000050: 70 2E 71 68 63 2C 73 79 6E 65 72 72 6D 73 67 2E    |p.qhc,synerrmsg.|
00000060: 6D 70 2C 43 3A 5C 4D 69 63 72 6F 63 68 69 70 5C    |mp,C:\Microchip\|
00000070: 4C 69 62 65 72 6F 5F 53 6F 43 5F 32 30 32 35 2E    |Libero_SoC_2025.|
00000080: 32 5C 4C 69 62 65 72 6F 5F 53 6F 43 5C 53 79 6E    |2\Libero_SoC\Syn|
00000090: 70 6C 69 66 79 5F 50 72 6F 5C 62 69 6E 5C 61 73    |plify_Pro\bin\as|
000000A0: 73 69 73 74 61 6E 74 0D 0A 49 6D 70 6C 65 6D 65    |sistant..Impleme|
000000B0: 6E 74 61 74 69 6F 6E 3B 50 6C 61 63 65 20 61 6E    |ntation;Place an|
000000C0: 64 20 52 6F 75 74 65 3B 52 6F 6F 74 4E 61 6D 65    |d Route;RootName|
000000D0: 3A 0D 0A                                           |:..|
```

Live ends at offset `0xD3` with `RootName:\r\n` — the literal text "RootName:" followed by an empty value. There are no tool messages, no implementation entries, nothing.

### Shadow `.msg` first 256 bytes (proper format)

The first 167 bytes (offset 0x00–0xA8 = `HelpInfo,...assistant\r\n`) match live byte-for-byte. The divergence is at offset `0xB8`: where live has `;Place and Route;RootName:`, shadow has the actual implementation message catalog beginning with `;Synthesis||CD140||@N: Using the VHDL 2008 Standard for file '…`.

```
000000B0: 6E 74 61 74 69 6F 6E 3B 53 79 6E 74 68 65 73 69    |ntation;Synthesi|
000000C0: 73 7C 7C 43 44 31 34 30 7C 7C 40 4E 3A 20 20 55    |s||CD140||@N:  U|
000000D0: 73 69 6E 67 20 74 68 65 20 56 48 44 4C 20 32 30    |sing the VHDL 20|
000000E0: 30 38 20 53 74 61 6E 64 61 72 64 20 66 6F 72 20    |08 Standard for |
000000F0: 66 69 6C 65 20 27 43 3A 5C 4D 69 63 72 6F 63 68    |file 'C:\Microch|
```

The shadow file has 2,108 lines of these structured tool-message records.

### Shadow `.msg` final 256 bytes

```
00104FE6: 61 74 69 6F 6E 3B 50 6C 61 63 65 20 61 6E 64 20    |ation;Place and |
00104FF6: 52 6F 75 74 65 7C 7C 28 6E 75 6C 6C 29 7C 7C 50    |Route||(null)||P|
00105006: 6C 65 61 73 65 20 72 65 66 65 72 20 74 6F 20 74    |lease refer to t|
00105016: 68 65 20 6C 6F 67 20 66 69 6C 65 20 66 6F 72 20    |he log file for |
00105026: 64 65 74 61 69 6C 73 20 61 62 6F 75 74 20 32 35    |details about 25|
00105036: 20 49 6E 66 6F 28 73 29 7C 7C 4D 50 46 53 5F 49    | Info(s)||MPFS_I|
…
001050B6: 7C 28 6E 75 6C 6C 29 3B 28 6E 75 6C 6C 29 0D 0A    ||(null);(null)..|
```

Note the structured format: `Implementation;<ToolName>||<Code>||@<Severity>: <Message>||<filelinks>`. Shadow ends at offset `0x1050C6` with `(null);(null)\r\n` — a message-record continuation or trailing entry. The live file has *none* of this body.

---

## tools.xml — NOT TRUNCATED (both well-formed)

Both files end identically at `</toolSetting>`:

### Live tools.xml final 128 bytes
```
00034D6E: 5F 74 69 6D 69 6E 67 3E 3C 67 6C 6F 62 61 6C 5F    |_timing><global_|
00034D7E: 69 6E 63 6C 75 64 65 5F 66 69 6C 65 3E 66 61 6C    |include_file>fal|
00034D8E: 73 65 3C 2F 67 6C 6F 62 61 6C 5F 69 6E 63 6C 75    |se</global_inclu|
00034D9E: 64 65 5F 66 69 6C 65 3E 3C 2F 66 69 6C 65 3E 3C    |de_file></file><|
00034DAE: 2F 69 6E 70 75 74 5F 66 69 6C 65 73 3E 3C 6F 75    |/input_files><ou|
00034DBE: 74 70 75 74 5F 66 69 6C 65 73 2F 3E 3C 72 65 70    |tput_files/><rep|
00034DCE: 6F 72 74 5F 66 69 6C 65 73 2F 3E 3C 2F 74 6F 6F    |ort_files/></too|
00034DDE: 6C 3E 3C 2F 74 6F 6F 6C 53 65 74 74 69 6E 67 3E    |l></toolSetting>|
```

### Shadow tools.xml final 128 bytes
```
00036473: 5F 74 69 6D 69 6E 67 3E 3C 67 6C 6F 62 61 6C 5F    |_timing><global_|
…
000364E3: 6C 3E 3C 2F 74 6F 6F 6C 53 65 74 74 69 6E 67 3E    |l></toolSetting>|
```

Both terminate the same way. The 5,893-byte delta is in the body — likely a session-state difference (more or fewer tool entries, varying configuration values) accumulated between the April 27 shadow and the morning April 28 overlay session. **Not corruption.** We omit `tools.xml` from the recovery to preserve whatever legitimate state the overlay session set.

---

## Implication

The corruption is **two files truncated mid-write during a non-graceful Libero process termination at 2026-04-28 12:00:41**, immediately after the failed-PnR seed sweep. The truncation pattern (mid-`SUBBLOCK` line in prjx, mid-section-header in `.msg`) is consistent with one of:

- A `__fastfail` / `RtlpAnalyzeHeapFailure` from a heap corruption check inside Libero's save routine
- An uncaught C++ exception during SUBBLOCK serialization that bypassed the structured exception unwind
- An OS-level termination (job-object kill, OOM) targeting libero.exe while save was in progress

No Application Error event log entry is produced by this class of failure (verified on Beelink). WerFault local dumps were not configured at the time, so no `.dmp` exists. The HKCU `LocalDumps` registry is now configured (`C:\CrashDumps`, full dump, 10 retain) so any future libero.exe crash will be captured automatically.

## What this evidence proves

1. The crash bug is **not** in any HDL source file — those have mtime 2026-04-02 and pristine ASCII content.
2. The crash bug is **not** in `designer/` PnR layout state (B2 already proved this; the truncation forensics independently confirm by showing the corruption is in metadata, not layout).
3. The crash bug is **not** in `synthesis/` — that directory's files were written 11:46–11:52, before the 12:00 incident.
4. The crash bug **is** in the prjx + .msg metadata files, both truncated by a single non-graceful save event.

A clean recovery is achievable by replacing those two files from VSS shadow.
