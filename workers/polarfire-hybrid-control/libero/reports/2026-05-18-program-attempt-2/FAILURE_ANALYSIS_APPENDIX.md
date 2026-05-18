# Rung A — Override Attempt FAILED 2026-05-18 (Option 1 closed)

**Status: STOPPED per pre-execution rollback rule. Option 1 (run-time override in FPExpress) is conclusively closed. Only Option 2 (.ppd re-export with correct silicon target) remains.**

This appendix supplements `libero/reports/2026-05-18-program-failure/FAILURE_ANALYSIS.md` (first-attempt failure). It documents the second attempt, taken with operator-authorized silicon-identity correction context.

## What Option 1 attempted

Updated `libero/scripts/program_kit.tcl` (per operator's hybrid-plan direction) to:

1. `set_fpexpress_mode -mode {developer}` — switch FPExpress out of Operator mode into Developer mode so the chain config could be modified before programming. (Note: `-mode developer` was wrong; the corpus said "developer_mode". Both `developer` and `developer` values returned the same FPExpress error: "Invalid argument value: 'developer' (expecting operator_mode or developer_mode)." Minor cosmetic bug — STEP 2 below still worked, so this did not block the test.)
2. `create_job_project` — same as first attempt, succeeded.
3. **`set_device_name -name {MPFS250T} -new_name {MPFS250T_ES}`** — rename the chain device to the engineering-sample variant. **This succeeded** ("The 'set_device_name' command succeeded.")
4. `set_programming_action -name {MPFS250T_ES} -action {PROGRAM}` — select PROGRAM action against the renamed device. **Succeeded** ("The 'set_programming_action' command succeeded.")
5. `run_selected_actions` — execute. **FAILED with identical error.**

## Identical error after override

```
programmer '065D9ACD' : Scan Chain...
programmer '065D9ACD' : Check Chain...
Error:  programmer '065D9ACD' : Device 1: Found: MPFS250(T_ES|TS_ES), Expected: MPFS250T
Error:  programmer '065D9ACD' : Scan and Check Chain FAILED.
Error:  Failed to run Action.
```

The "Expected: MPFS250T" string is unchanged from the first attempt, despite `set_device_name` having renamed the chain device entry to `MPFS250T_ES`. **This proves that the "Expected" target is sourced from the `.ppd` file's payload header, not from FPExpress's chain configuration.** `set_device_name` only updates the chain display name; the underlying silicon-class match for Scan-Check-Chain is locked at .ppd-export time inside Libero Designer.

## Forensic IDCODE-capture status (Step 1a per operator hybrid plan)

**Attempted, failed cleanly:**
- `sdbg.exe SCRIPT:read_idcode.tcl LOGFILE:...` returns exit code 127 with empty log. SmartDebug headless mode appears non-functional in 2025.2 (GUI-only?).
- `libero.exe SCRIPT:read_idcode_libero.tcl` opens the seed_7 project successfully but `read_id_code` Tcl command returns "invalid command name" — `read_id_code` is documented as a SmartDebug-only command, not available in Libero Designer's Tcl namespace.

**Forensic evidence we DO have:**
- FPExpress's class-level identification: `MPFS250(T_ES|TS_ES)` — this is the silicon-class pattern from FPExpress's `chain.def` / device-recognition database. It conclusively places the silicon in the engineering-sample family.
- April-2 Beelink session log (per operator): documents the silicon as `MPFS250T_ES + FCVG484 package`.
- Today's Scan-Check-Chain rejection: third independent confirmation that the kit's IDCODE does NOT match the production `MPFS250T` IDCODE.

The raw 32-bit hex IDCODE is unrecoverable via headless tooling in this Libero install. Recovery would require:
- Launching SmartDebug GUI (X11/RDP session over Tailscale)
- Or writing a custom direct-JTAG probe via openocd against the FlashPro6 (out-of-scope, training-data risk per Microchip-specific guidance)

## What Option 2 (re-export .ppd with ES target) requires

To get a PROGRAM PASS today, the .ppd inside the `.job` file must be regenerated against the `MPFS250T_ES` silicon target. The April-2 session log notes that Libero 2025.2 lacks full package data for `MPFS250T_ES` (only `tpp/` directory, no `.ddf` files), which is why the seed_7 closure was forced to `MPFS250T` Production. But the PROGRAMMING step may accept ES as a target via a different mechanism than synthesis/P&R.

Two sub-paths to investigate (deferred — operator decision):

1. **Edit the .pdb header field for "device_class" / "silicon_target" directly.** The .pdb is FlashPro's compiled programming database (part of the .job archive). If there's a documented field that controls the chain-check Expected value, editing it would let us reuse the existing Production-targeted bitstream against ES silicon.

2. **Re-run `export_prog_job` in Libero Designer with explicit ES target.** Requires:
   - Open seed_7 project in Libero Designer (on bee)
   - Find Tcl/GUI control to set "silicon target for chain check" to `MPFS250T_ES`
   - Re-export the .job
   - Replace `libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job` with the re-exported one
   - Re-run rung A

Estimated effort: 30–60 min on bee in a Libero Designer session if a suitable Tcl flag exists; longer if the only path is GUI-driven.

## Recommended next steps (operator decision)

A. **Proceed to rung B (RPO-6 SmartPower closure) in parallel** — simulation-only, unaffected by rung A status. Operator pre-authorized this.

B. **Defer rung A re-attempt** until either:
   - Option 2 (.ppd re-export with ES target) is investigated and either confirms a working path or definitively closes
   - OR operator authorizes a SmartDebug GUI session to launch the programming via the FlashPro Express GUI directly (which may have a different chain-check tolerance than the headless Tcl flow)

C. **Document the audit-005 correction** as scoped in the operator's hybrid-plan documentation section. ASK before editing `~/projects/tychon-sbir/docs/` per CLAUDE.md authority.

## Status

- Operator-authorized Option 1 (run-time override): **CLOSED** (override is at wrong layer; .ppd locks the silicon target)
- Operator-authorized Option 2 (.ppd re-export): **OPEN** (investigation pending)
- Rung B in parallel: **READY TO START** (operator pre-authorized)
- Rung A status: blocked on Option 2 or on operator decision to launch SmartDebug GUI session
