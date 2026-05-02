# Track 0 — Icicle Kit First-Bitstream Bring-Up Runbook

This runbook drives the four hardware-bring-up items (HW-01..HW-04) that gate the first PID-only bitstream onto the physical Icicle Kit acquired 2026-05-02. Items HW-02 and HW-03 are Beelink-side vendor-infrastructure edits the agent attempts via `ssh bee` with per-action approval; manual recipes are documented as fallback. HW-04 has the most surgical work because the staged reference PDC bundle is FCVG484-keyed but the silicon is FCSG536e — a per-pin package-cross-mapping audit is required before integration.

## Status summary

| Item | Status | Owner |
|---|---|---|
| HW-01 — silkscreen package verification | RESOLVED 2026-05-02 (FCSG536e) | n/a |
| HW-02 — License.dat line 269 split | OPEN | agent via `ssh bee` (per-action approval), or user manual fallback |
| HW-03 — CP210x VCP driver install | OPEN | agent via `ssh bee` (per-action approval), or user manual fallback |
| HW-04 — pinout.pdc integration | OPEN, gated on HW-04b audit | agent (4 sub-steps, a/b/c/d) |
| Track 0 closure | OPEN | user (FPExpress GUI on Beelink) |

## HW-01 — Silkscreen package verification (RESOLVED)

Silkscreen reads `MPFS250T-FCSG536e`. The trailing `e` is the engineering-sample marker; Libero's device DB tracks ES dies as `PA5SOC250 ES` (or similar) separately from production silicon.

Resolution applied:
- `libero/scripts/01_scaffold_proj.tcl:27` (`set DEVICE_PACKAGE "FCSG536"`) — **no change**, scaffold matches silicon.
- `2026-04-29-pid-real/r6_s25` retroactive validity is preserved; r6_s25 is the canonical baseline for r6_s25 power and timing.

ES variant verification (defer to HW-04b execution time): when the scaffold runs against Libero 2025.2, log the resolved device label after `new_project` and confirm it lands on the ES entry rather than production-die. If Libero silently uses production-die ball assignments against ES silicon, pin assignments may diverge — check Libero's Pin Description data for ES-specific entries.

## HW-02 — License.dat line 269 split

The CoreVectorBlox license stanza in `C:\Microchip\Libero_SoC_2025.2\License.dat` has a literal `nn` between the comment banner and the `FEATURE AIPOSOLCORECORE_VECTORBLOX` keyword instead of two real newlines. FlexLM treats the entire line as a comment, so CoreVectorBlox is invisible.

Required only for AI/CoreVectorBlox demo. PID-only Track 0 closure does not depend on this.

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

## HW-03 — CP210x VCP driver install

The Icicle Kit's J11 connector is a Silicon Labs CP2108 quad-UART bridge. Without the CP210x VCP driver, the four virtual COM ports (including MSS UART0 used for console) do not enumerate.

Required only for runtime observability. Bitstream programming over JTAG works without this.

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

## HW-04 — pinout.pdc integration (4 sub-steps)

The riskiest item in Track 0. The staged reference bundle is FCVG484-keyed; silicon is FCSG536e. A per-pin audit precedes integration.

### HW-04a — Bundle synced

Done 2026-05-02. The 17 reference PDC files plus README from `polarfire-soc/icicle-kit-reference-design@fd0aebb` now live at `libero/constraints/icicle_reference/` on spark1.

### HW-04b — Package-cross-mapping audit (FCVG484 → FCSG536e)

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

Apply the audit results: keep `MAP_OK` pins as-is; rewrite `MAP_REROUTE` pins to the FCSG536e ball; drop `MAP_DROP` pins.

Commit as `feat(pdc): populate pinout.pdc from Icicle reference bundle (FCVG484→FCSG536e mapped)`.

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
- FlashPro6 enumerates in Device Manager: VID `0x1514`, PID `0x200B`.
- FPExpress `run_selected_actions` returns success.
- Device verifies (DEVICE_INFO action returns the expected MPFS250T-FCSG536e signature).

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
