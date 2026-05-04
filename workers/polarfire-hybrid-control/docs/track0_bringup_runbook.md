# Track 0 — Icicle Kit First-Bitstream Bring-Up Runbook

This runbook drives the four hardware-bring-up items (HW-01..HW-04) that gate the first PID-only bitstream onto the physical Icicle Kit acquired 2026-05-02. As of the 2026-05-04 refresh below, HW-01 / HW-02 / HW-03 are RESOLVED and HW-04b is OBSOLETED; remaining work (HW-04c populate `pinout.pdc`, HW-04d persist bitstream artifact, then program the kit and bring up demo firmware) is now driven by the demo-bringup plan at `~/.claude/plans/i-plugged-in-j11-optimized-quilt.md`. Original recipes are retained below for re-application reference; the active hand-off lives in the demo-bringup plan.

## Status summary (refreshed 2026-05-04)

| Item | Status | Owner |
|---|---|---|
| HW-01 — silkscreen package verification | **RESOLVED 2026-05-03** (silicon corrected to **MPFS250T-FCVG484E**, scaffold updated in commit `8d794e5`) | n/a |
| HW-02 — License.dat line 269 split | **RESOLVED 2026-05-02 evening** (FlexLM lists CoreVectorBlox feature) | n/a |
| HW-03 — CP210x VCP driver install | **RESOLVED 2026-05-02 evening** (Silicon Labs CP2108 enumerates as 4 COM ports under Windows on Beelink) | n/a |
| HW-04a — bundle synced | **RESOLVED 2026-05-02** | n/a |
| HW-04b — package-cross-mapping audit | **OBSOLETED 2026-05-03** (silicon now matches bundle's native FCVG484 package; no per-pin mapping required — see HW-04b note below) | n/a |
| HW-04c — pinout.pdc populated from reference | **OPEN** | covered by demo-bringup plan Part 1 |
| HW-04d — explicit bitstream artifact persistence | **OPEN** | covered by demo-bringup plan Part 1 |
| Track 0 closure (program kit) | **OPEN** | covered by demo-bringup plan Part 2 |
| Demo firmware (Options A→C) | **OPEN** | covered by demo-bringup plan Parts 3–5 |

**Hardware connectivity verified 2026-05-04 (this session):** Both Icicle Kit USB headers (J11 and J33) plugged into Beelink. `Get-PnpDevice` enumerates **both** the FlashPro embedded programmer (`VID_1514 PID_200B`, status OK, HID class) **and** the Silicon Labs CP2108 quad UART bridge (`VID_10C4 PID_EA71`, 4 interfaces visible as COM3 / COM4 / COM5 / COM6). Per-port mapping (which physical header carries which chip) is NOT yet verified — selectively unplug one in Part 2 and re-enumerate to disambiguate. Note: an earlier draft of HW-03 below states "J11 connector is a Silicon Labs CP2108"; this is unverified in either direction at the time of this refresh.

## HW-01 — Silkscreen package verification (RESOLVED 2026-05-03)

Initial reading was `MPFS250T-FCSG536e` (engineering-sample marker). Re-reading on 2026-05-03 against the actual silicon and Microchip datasheet DS00004248 confirmed the production part is **MPFS250T-FCVG484E** — 484-ball flip-chip BGA, **STD speed grade**, Production silicon, **Extended Commercial 0–100 °C** ("E" suffix). The earlier `FCSG536e` reading conflated the engineering-sample suffix `e` with the package code.

Resolution applied:
- `libero/scripts/01_scaffold_proj.tcl:27` updated from `FCSG536` to `FCVG484` in commit `8d794e5` ("Fix FPGA package designator: FCSG536 → FCVG484 (silkscreen-confirmed)").
- TVW audit-006 (commit `0a33ac4`) re-validated that the r6_s25 timing closure (+0.728 ns slack on the 125 MHz FIC CCC PLL OUT0 user clock at slow_lv_ht) was actually generated against FCVG484 STD-grade Production silicon — SmartTime report header confirms `Package: FCVG484 / Speed Grade: STD / Data source: Production`.
- The reference PDC bundle staged at `libero/constraints/icicle_reference/` is FCVG484-keyed (sourced from `polarfire-soc/icicle-kit-reference-design@fd0aebb`); pin mapping is therefore **MAP_OK** with no cross-package remap needed (see HW-04b OBSOLETED note below).

## HW-02 — License.dat line 269 split (RESOLVED 2026-05-02 evening)

The CoreVectorBlox license stanza in `C:\Microchip\Libero_SoC_2025.2\License.dat` had a literal `nn` between the comment banner and the `FEATURE AIPOSOLCORECORE_VECTORBLOX` keyword instead of two real newlines. FlexLM was treating the entire line as a comment, so CoreVectorBlox was invisible.

**Status:** Fix applied 2026-05-02 evening; `lmutil lmstat -a` now lists CoreVectorBlox as a checkable feature. License backup saved at `License.dat.bak-pre-fix-*`.

Required only for AI/CoreVectorBlox demo. PID-only Track 0 closure does not depend on this. Recipes below retained for re-application reference.

### Agent-driven recipe (via `ssh bee`, per-action approval)

```bash
# Step 1: verify backup exists; create if missing.
ssh bee 'ls -la "C:/Microchip/Libero_SoC_2025.2/License.dat.bak-2026-05-02" \
         || cp "C:/Microchip/Libero_SoC_2025.2/License.dat" \
               "C:/Microchip/Libero_SoC_2025.2/License.dat.bak-pre-fix-$(date +%Y-%m-%d-%H%M%S)"'

# Step 2: capture pre-edit context (lines 265-275).
ssh bee 'sed -n "265,275p" "C:/Microchip/Libero_SoC_2025.2/License.dat"'

# Step 3: split line 269 — replace literal `nn` between the banner and FEATURE
# with two real newlines. Use awk to preserve everything else exactly.
ssh bee 'awk "{
    if (NR == 269) {
        sub(/-nnFEATURE/, \"-\\n\\nFEATURE\", \$0)
    }
    print
}" "C:/Microchip/Libero_SoC_2025.2/License.dat" > "C:/Microchip/Libero_SoC_2025.2/License.dat.fixed" \
&& mv "C:/Microchip/Libero_SoC_2025.2/License.dat.fixed" \
      "C:/Microchip/Libero_SoC_2025.2/License.dat"'

# Step 4: capture post-edit context (lines 265-275 should now show banner / blank /
# FEATURE / SIGN... rather than banner-glued-to-FEATURE).
ssh bee 'sed -n "265,275p" "C:/Microchip/Libero_SoC_2025.2/License.dat"'

# Step 5: validate via FlexLM. Locate lmutil — typically under
#   C:\Microchip\Libero_SoC_2025.2\Designer\bin\lmutil.exe
# Adjust path as needed.
ssh bee '"C:/Microchip/Libero_SoC_2025.2/Designer/bin/lmutil" lmstat -a -c "C:/Microchip/Libero_SoC_2025.2/License.dat"' | grep -i vectorblox
```

The expected post-edit excerpt around line 269 is:

```
#--------------------------------------------------------------------------------

FEATURE AIPOSOLCORECORE_VECTORBLOX actlmgrd 1.0 permanent uncounted \
  ...
SIGN=...
```

Stop-gate: `lmutil lmstat -a` lists CoreVectorBlox as a checkable feature.

### Manual fallback (user)

Open `C:\Microchip\Libero_SoC_2025.2\License.dat` in a text editor that preserves UNIX line endings (Notepad++, VSCode). Find line 269. The literal sequence `-nnFEATURE` should be `-\n\nFEATURE`. Save. Run `lmutil lmstat -a` and confirm CoreVectorBlox is visible.

## HW-03 — CP210x VCP driver install (RESOLVED 2026-05-02 evening)

The Icicle Kit exposes a Silicon Labs **CP2108 quad-UART bridge** on one of its USB headers (J11 or J33 — see connectivity verification note in Status Summary above). Without the CP210x VCP driver, the four virtual COM ports (including the MSS UART0 used for console) do not enumerate under Windows.

**Status:** CP210x Universal Windows Driver installed on Beelink 2026-05-02 evening. Confirmed 2026-05-04: `Get-PnpDevice` shows all 4 CP2108 interfaces present and OK as **COM3 / COM4 / COM5 / COM6** (Interface 3 / 2 / 1 / 0 respectively). Which COM port carries MMUART0 (the MSS console) is verified post-programming in demo-bringup plan Part 2 by opening all four simultaneously and resetting the kit.

Required only for runtime observability. Bitstream programming over JTAG works without this. Recipes below retained for re-application reference.

### Agent-driven recipe (via `ssh bee`, per-action approval)

```bash
# Step 1: download from silabs.com developer-tools page.
# URL: https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers
# Driver bundle: CP210x Universal Windows Driver v11.x (latest).
ssh bee 'mkdir -p ~/Downloads/cp210x && cd ~/Downloads/cp210x \
   && curl -L -o cp210x.zip "https://www.silabs.com/documents/public/software/CP210x_Universal_Windows_Driver.zip"'

# Step 2: extract bundle.
ssh bee 'cd ~/Downloads/cp210x && unzip -o cp210x.zip'

# Step 3: install via pnputil. Note: Beelink runs Windows 11; pnputil is the
# scriptable CLI driver-store tool. Git Bash MINGW64 may need to invoke
# powershell.exe or cmd.exe directly to reach pnputil.
ssh bee 'powershell.exe -Command "pnputil /add-driver \"$HOME/Downloads/cp210x/silabser.inf\" /install"'

# Step 4: validate.
ssh bee 'powershell.exe -Command "pnputil /enum-drivers" | grep -i CP210x'
```

Stop-gate: pnputil reports CP210x driver present in driver store. User confirms via Device Manager that four virtual COM ports (one per UART of the CP2108 quad bridge) appear under "Ports (COM & LPT)". The MSS UART0 console will land on COM1 (per CLAUDE.md memory `reference_icicle_kit_connectors`).

### Manual fallback (user)

1. Download CP210x Universal Windows Driver from silabs.com developer-tools page.
2. Extract.
3. Right-click `silabser.inf` → "Install".
4. Verify Device Manager shows 4 virtual COM ports.

## HW-04 — pinout.pdc integration (sub-steps a/b done; c/d open)

The original concern (staged reference bundle is FCVG484-keyed but silicon is FCSG536e — a per-pin cross-package audit was required) was resolved when HW-01 was re-verified and the scaffold device was corrected to FCVG484E in commit `8d794e5`. Reference bundle now matches silicon natively. HW-04b is therefore obsoleted; HW-04c (single concatenated `pinout.pdc`) and HW-04d (explicit bitstream artifact persistence) remain open and are covered by the demo-bringup plan Part 1.

### HW-04a — Bundle synced

Done 2026-05-02. The 17 reference PDC files plus README from `polarfire-soc/icicle-kit-reference-design@fd0aebb` now live at `libero/constraints/icicle_reference/` on spark1.

### HW-04b — Package-cross-mapping audit (FCVG484 → FCSG536e) — OBSOLETED 2026-05-03

**This entire sub-step is obsoleted.** Silicon was re-verified as FCVG484E in HW-01 above; the reference bundle is FCVG484-native; no cross-package mapping is required. All pins are MAP_OK by construction. The procedure below is retained for historical reference only — do not execute.

For each `set_io ... -pin_name {<ball>}` declaration in every sub-PDC, look up the ball coordinate in:
- the FCVG484 ball matrix (484-ball, 19×19 mm) — the reference bundle's native package, AND
- the FCSG536e ball matrix (536-ball, 16×16 mm CSP, ES variant) — actual silicon.

Source for ball-matrix data: Microchip's PolarFire SoC Pin Description Tables (UG0726). Check `~/.corpus/polarfire-control-corpus/` first — UG0726 was not found there during T3.1 corpus search, so it must be fetched from the Microchip portal (also captures publication date for the Appendix C citation closeout).

Per-pin verdict:

| Tag | Meaning |
|---|---|
| `MAP_OK` | Same ball on both packages, or 1:1 mapping documented |
| `MAP_REROUTE` | Different ball on FCSG536e but same I/O bank, equivalent pad type — rewrite the `-pin_name` |
| `MAP_DROP` | No equivalent on FCSG536e — drop and surface in design doc which top-level I/O loses physical pinning |
| `MAP_TBD` | Manual review required (e.g. transceiver references, dedicated XCVR REF_CLK locator) |

Critical for ES variant: the engineering-sample die may have different pad-to-ball routing than production silicon. Verify via Libero device DB at runtime; if Libero exposes ES-specific Pin Description data, prefer it over the production-die UG0726 entries.

Audit table lands at `libero/constraints/icicle_reference/PACKAGE_AUDIT.md`. Commit alongside the bundle as `audit: FCVG484→FCSG536e per-pin mapping for icicle_reference bundle`.

### HW-04c — Populate `libero/constraints/pinout.pdc`

Re-triggers P&R. The single P&R-affecting commit on Track 0.

Concatenation strategy: produce one self-contained `pinout.pdc` (preferred over multiple `import_files -io_pdc` calls) so the existing scaffold binding at `01_scaffold_proj.tcl:74` continues to work without change. Embed the audit verdict per pin as a trailing comment.

Order from the staged README, applied as concatenated section banners:
1. `ICICLE.pdc` (master — clock, reset, switches, LEDs)
2. `ICICLE_PCIE.pdc` (REF_CLK_PAD_P/N at L19/L20)
3. `decision-2-option-c.pdc` (XCVR REF_CLK explicit-lock fix; layered AFTER ICICLE_PCIE per its own internal documentation)
4. `ICICLE_MMUART0.pdc` (MSS UART0 console)
5. Other peripheral PDCs as the top-level uses them: `ICICLE_MAC.pdc`, `ICICLE_USB.pdc`, `ICICLE_SDIO.pdc`, `ICICLE_CAN0.pdc`, `ICICLE_MMUART1/2/3.pdc`, `ICICLE_I2C_LOOPBACK.pdc`, `ICICLE_SPI_LOOPBACK.pdc`, `ICICLE_MIKROBUS.pdc`, `ICICLE_RPi.pdc` (or `ICICLE_RPi_MICRON_QSPI.pdc`), `NW_PLL.pdc`, `DRI_CCC_DEMO.pdc`.

Trim to the I/O actually exposed by `MPFS_ICICLE_KIT_BASE_DESIGN`. The top-level entity has 148 ports across input/output/inout — intersect against each sub-PDC's `set_io` declarations and drop unused.

Apply the audit results: keep `MAP_OK` pins as-is. (HW-04b is obsoleted — there are no `MAP_REROUTE` or `MAP_DROP` pins because silicon and bundle now share the FCVG484 package natively.)

Commit as `feat(pdc): populate pinout.pdc from Icicle reference bundle (FCVG484 native, MAP_OK)`.

### HW-04d — Extend `04_synth_pnr.tcl` for explicit bitstream artifact persistence

Phase I had 20 P&R seeds across 5 dated subdirs but no `.job`/`.stp`/`.bit` artifacts persisted to repo. The current script (`libero/scripts/04_synth_pnr.tcl:120-128`) calls `export_prog_job` and declares `$REPORT_DIR/polarfire_hybrid_control.job` but the `.job` is not landing in `libero/reports/` at run time.

Add explicit `export_bitstream_file_pdb` (or 2025.2 equivalent — verify via Libero command reference at execution time) to persist a `.fs` alongside the `.job`. Add an explicit copy/checksum step that lands both artifacts in the dated closure subdir, not just `$REPORT_DIR`.

Re-runs `GENERATEPROGRAMMINGDATA` only; full P&R re-run only if Libero invalidates PD/STA cache.

## Track 0 closure — FPExpress invocation

Once HW-04 produces a `.job` and `.fs` in the dated subdir, program the kit on the Beelink:

```bash
# Beelink Git Bash. FPExpress launches the GUI; for headless invocation,
# use the Tcl script form. Tool path: 2025.2 install root.
"/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/FPExpress.exe" \
    -script:program_polarfire_hybrid_control.tcl
```

`program_polarfire_hybrid_control.tcl` content (place at `libero/scripts/`):

```tcl
# program_polarfire_hybrid_control.tcl — FPExpress headless programming.
new_project -name {polarfire_hybrid_control_program} -location {.} -overwrite 1
construct_chain_automatically
set_programming_action -name {<device-name>} -action {PROGRAM}
set_programming_file -name {<device-name>} \
    -file {libero/reports/2026-05-XX-firstprog-r1/polarfire_hybrid_control.job}
run_selected_actions
```

Stop-gate (user-reported, since the agent has no Beelink GUI access):
- FlashPro embedded programmer enumerates in Device Manager: VID `0x1514`, PID `0x200B` (already verified 2026-05-04).
- FPExpress `run_selected_actions` returns success.
- Device verifies (DEVICE_INFO action returns the expected **MPFS250T-FCVG484E** signature).

## Verification chain

```bash
# Local (no Beelink):
make verify-local
make verify-strict

# Beelink (post-HW-04, requires HW-02 if AI demo):
ssh bee 'cd ~/dev/projects/polarfire-hybrid-control && git pull \
   && libero SCRIPT:libero/scripts/04_synth_pnr.tcl'

# Bitstream artifacts land at:
ssh bee 'ls -la ~/dev/projects/polarfire-hybrid-control/libero/reports/2026-05-XX-firstprog-r1/'

# Programming (user, GUI):
# Open FPExpress → load .job → Program → verify FlashPro6 enumerates.
```
