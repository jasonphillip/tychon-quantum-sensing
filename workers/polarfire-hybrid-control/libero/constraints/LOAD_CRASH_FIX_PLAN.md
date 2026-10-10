# Load-Crash Fix Plan — `MPFS_ICICLE_Vectorblox` Recovery via VSS

**Branch**: decision-2-option-c
**Date drafted**: 2026-04-29
**Status**: Awaiting user approval before execution
**Prerequisite reading**: `LOG_ARCHAEOLOGY_FINDINGS.md` in this directory

This plan describes the recovery procedure that follows from the Phase A
diagnosis. **Nothing here has been executed.** The user needs to approve
the approach before any project files are modified.

---

## Recovery vector

VSS shadow copies on Beelink contain pristine project files from
**2026-04-27 12:34–12:36 PM**, with file mtimes preserved from the
**2026-04-02** baseline. We use any of the four shadow copies (they're
identical) to restore the corrupted files. Pick `HarddiskVolumeShadowCopy4`
(latest of the four).

```
Source: \\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy4
        \Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\
        Icicle_SoC\ref_design\MPFS_ICICLE_Vectorblox\

Target: C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\
        Icicle_SoC\ref_design\MPFS_ICICLE_Vectorblox\
```

---

## Risk assessment

**Risk level: low.** Justification:

- The VSS shadow files have **mtimes from 2026-04-02** — the same date as the
  successful baseline P&R run. That is the canonical pre-overlay state of
  the project.
- Restoration is a **file-replace** operation, not a project-edit. Libero
  will load the restored files exactly as it loaded them on April 2.
- The PDC fix (`libero/constraints/decision-2-option-c.pdc`) and overlay
  scripts are committed in git on `decision-2-option-c` HEAD `baa9c9d`.
  They replay deterministically against the April 2 baseline.
- The April 28 morning overlay session demonstrated the overlay applies
  cleanly and synthesis closes (24.69% 4LUT, Δ −0.03% vs April 2). Only the
  P&R failed, and only because of the missing XCVR_REF_CLK location lock —
  which is exactly what `decision-2-option-c.pdc` adds.

**What gets lost** by restoring from April 2:
- The morning April 28 overlay state in the live project. **This is fine** —
  the overlay re-applies idempotently from `decision-2-c-overlay.tcl` and
  the result is what we want.
- Any post-April-2 manual edits to the project files. **Verified none
  exist** — the shadow's file mtimes are still 2026-04-02 14:11:49,
  meaning the project was untouched between April 2 and April 27. No work
  product to lose.

**What gets preserved**:
- The user's decision-2-option-c branch on Spark1 (HEAD `baa9c9d`).
- The PDC fix, overlay scripts, recovery notes, all committed.
- The committed reports from April 2 and April 28 morning syntheses
  (`libero/reports/2026-04-28/` etc.).

**What's irreversible**: the file replacement. Backups of the broken state
are already on disk (`MPFS_ICICLE_Vectorblox.prjx.bak-*`) and these contain
the truncated prjx, which is forensically interesting only — there's
nothing recoverable from them since the truncation is data loss, not a
reorderable corruption.

---

## Step-by-step procedure (TO BE APPROVED BY USER)

### Step 1 — Pre-flight backups

Before touching anything, snapshot the current broken state with a labelled
backup directory. This is independent of existing `.bak` files (those only
back up the prjx, not the entire project).

```bash
# On Beelink (ssh bee):
cd /c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design
cp -a MPFS_ICICLE_Vectorblox MPFS_ICICLE_Vectorblox.broken-20260429
ls -la MPFS_ICICLE_Vectorblox.broken-20260429/MPFS_ICICLE_Vectorblox.prjx
```

Confirm the backup dir contains the 178,303-byte truncated prjx.

### Step 2 — Restore the two truncated files from VSS shadow

**Forensics update (post-evidence-capture):** Of the three originally-suspect
files, only `prjx` and `.msg` are actually truncated. `tools.xml` is well-
formed at the boundary in both live and shadow (both end with
`</toolSetting>`); its 5,893-byte delta is legitimate session-state evolution
between the April 27 shadow and the morning April 28 overlay. **We restore
only prjx + .msg** to avoid rolling back valid tool-config changes from the
overlay session. See `TRUNCATION_FORENSICS.md` for byte-level evidence.

PowerShell script (run as user `jason` on Beelink):

```powershell
$shadow = "\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy4"
$root = $shadow + "\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\Icicle_SoC\ref_design\MPFS_ICICLE_Vectorblox"
$liveRoot = "C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\Icicle_SoC\ref_design\MPFS_ICICLE_Vectorblox"

$files = @(
    @{ Src = "$root\MPFS_ICICLE_Vectorblox.prjx";          Dst = "$liveRoot\MPFS_ICICLE_Vectorblox.prjx" },
    @{ Src = "$root\tooldata\MPFS_ICICLE_Vectorblox.msg";  Dst = "$liveRoot\tooldata\MPFS_ICICLE_Vectorblox.msg" }
)

foreach ($f in $files) {
    [System.IO.File]::Copy($f.Src, $f.Dst, $true)
    $info = Get-Item -LiteralPath $f.Dst
    Write-Host ("Restored " + $f.Dst.Split('\')[-1] + "  Size=" + $info.Length)
}
```

Expected post-step:
- prjx: 363,261 bytes
- .msg: 1,069,254 bytes

### Step 3 — Decision: go for full project restore, or minimal-restore?

**Recommend MINIMAL.** Step 2 alone restores exactly what's broken.

If the load test (Step 5) still fails, escalate to a full project restore:
copy the entire `MPFS_ICICLE_Vectorblox\` from the shadow over the live tree.
This is a heavier operation (~hundreds of MB), but it brings the entire
project to the known-good April 2 state.

**Don't do the full restore preemptively.** If minimal works, we keep the
designer/ and synthesis/ artifacts that contain the morning overlay
synthesis state — useful reference even if we re-run synth.

### Step 4 — Smoke check the prjx tail

```bash
# On Beelink:
cd /c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox
tail -3 MPFS_ICICLE_Vectorblox.prjx
```

Expected: a clean ENDLIST or proper closing tag, NOT the `,` mid-line that
characterizes the broken file.

### Step 5 — Load-only test (the gate)

```bash
ssh bee "cd ~/dev/projects/polarfire-hybrid-control && git pull ws1 decision-2-option-c && libero \"SCRIPT:libero/scripts/decision-2-c-load-only.tcl\"" 2>&1 | tee /tmp/loadonly_postrestore.log
```

Expected: clean completion ending with `==> LOAD_ONLY COMPLETE`.

If this fails, **stop and escalate to full project restore** (Step 3
escalation path).

### Step 6 — Pre-flight integrity check, then PDC rerun

**Pre-flight (added 2026-04-29 per user review):** `decision-2-c-pdc-rerun.tcl`
documents that the HLS overlay must already be applied. Confirm on-disk
consistency before kicking off the heavy P&R run, otherwise risk a
silent-wrong-answer where synthesis succeeds against a stale netlist that
doesn't match the new HLS.

Pre-flight checklist:
1. `grep "wire .*5:0.* axi4target_araddr" component/work/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN.v`
   → must find at least one match (decision-2-option-c marker; pre-overlay
   state is `[4:0]`)
2. `grep "inner_clamp_setpoint" <hls_path>/nv_pid_top_nv_pid_top.v`
   → must find at least one match (decision-2 Option C hybrid clamp marker)
3. Verify prjx TIME / SIZE for the nv_pid_top entry matches the actual file
   on disk (`stat -c "%Y %s"` vs prjx TIME field; epoch second-equality is
   sufficient)

If all three pass, **proceed directly to `decision-2-c-pdc-rerun.tcl`**.

If any fail, run `decision-2-c-overlay.tcl` first to bring the project into
a consistent decision-2-option-c state, then `decision-2-c-pdc-rerun.tcl`.
Adds ~15-20 min wall time but eliminates silent-wrong-answer risk.

Pre-flight result for THIS recovery (2026-04-29):

| Check | Result |
|---|---|
| SmartDesign top has 6-bit araddr | ✅ `wire [5:0] axi4target_araddr_const_net_0;` (line 736) |
| nv_pid_top has inner_clamp_setpoint | ✅ multiple matches |
| prjx TIME / SIZE match on-disk file | ✅ TIME=1777390997 (Apr 28 11:43:17) / SIZE=257368 — both exact |

**Conclusion**: VSS shadow captured a post-overlay, pre-corruption state.
On-disk state is fully consistent with decision-2-option-c. `pdc-rerun.tcl`
can run directly, no overlay re-run needed.

```bash
# Pre-stage the PDC (already done as part of restore prep — verify it's there):
ssh bee 'ls -la /c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox/constraint/fp/decision-2-option-c.pdc'

# Kick off the run (~30-60 min wall):
ssh bee "cd ~/dev/projects/polarfire-hybrid-control && libero \"SCRIPT:libero/scripts/decision-2-c-pdc-rerun.tcl\"" \
    | tee libero/reports/_pdc_rerun_postrestore.log
```

The `decision-2-c-pdc-rerun.tcl` script imports the fp_pdc, re-runs
synthesis, runs place-and-route with the XCVR_REF_CLK location lock, and
extracts timing + power reports.

### Step 7 — Pull reports back to Spark1, integrity check, commit

```bash
# On Spark1:
bash libero/scripts/extract_reports.sh
```

**Post-run integrity check** (added 2026-04-29 per user review): confirm the
new reports actually correspond to decision-2-option-c HLS, not a stale
netlist:
1. `compile_netlist_resources.rpt` shows ~24.69% 4LUT (matches morning
   overlay synthesis, demonstrating overlay HLS made it through)
2. The synthesized netlist references the `inner_clamp_setpoint` register at
   AXI offset 0x20. Verify in `MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_hier_resources.csv`
   or via `grep inner_clamp_setpoint synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.srr`.
3. `iteration_summary.rpt` shows positive worst slack at 200 MHz
   (target: ≥0 ns; April 2 baseline was +0.165 ns, no PRPF_009)
4. SmartPower fabric power within ±5% of 2,664 mW

Only after all four checks pass:
```bash
git add libero/reports/2026-04-29-recovered/
git commit -m "Recovery: post-VSS-restore P&R reports for decision-2-option-c overlay"
```

Acceptance criteria for completing Phase I:
- 4LUT delta within ±1% of April 2 baseline (24.72%)
- Worst slack ≥ 0 ns at 200 MHz
- Fabric power within ±5% of 2,664 mW
- No PRPF_009 anywhere in the layout logs (the PDC fix targets exactly this)
- `inner_clamp_setpoint` register present at AXI offset 0x20 in the synth
  output — proves the reports correspond to decision-2-option-c HLS, not
  stale netlist

---

## What to do if Step 5 fails

If load-only still crashes after Step 2, the corruption is broader than
prjx + tools.xml + .msg. Escalation order:

1. **Full project restore.** Copy the entire `MPFS_ICICLE_Vectorblox\` from
   the shadow (large operation, but pristine state guaranteed).
2. **GUI-driven open** with WerFault dump capture in place (HKCU LocalDumps
   already configured per Phase A side action). Whatever the GUI surfaces in
   a dialog is the real problem.
3. **Procmon trace** of `libero.exe` during load attempt to capture the
   exact file-system operation that fails.

---

## What this fix plan does NOT cover

- The B4 install bug (ES-targeted `ICICLE_MSS.cxf` shipped in SmartHLS
  reference designs that fails to import into production-die projects) is
  **independent** of the load crash and is unaffected by this recovery. It
  remains a Microchip support case.
- We do NOT need to delete or modify the existing `prjx.bak-*` files —
  they're forensically interesting (they document the truncation) but not
  load-bearing for recovery.

---

## Decision request

**User: please review and approve before I execute Step 1.** Specifically:

1. Confirm the recovery approach (VSS shadow restore, minimal three files
   first) is what you want.
2. Confirm I should run Steps 1–5 autonomously and pause for your review
   before Steps 6–7 (pipeline rerun and commit).
3. If you'd prefer to run any step yourself (e.g. the GUI test, or the
   pipeline rerun), say which.
