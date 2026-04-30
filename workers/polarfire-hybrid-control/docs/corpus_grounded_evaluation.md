# Corpus-Grounded Evaluation

Date: 2026-04-30
Branch: `codex/corpus-verification`
Corpus: `~/.corpus/polarfire-control-corpus`

## Purpose

This evaluates the repo as a pre-corpus artifact: what was built before the
new project corpus existed, checked against the corpus as ground truth. The
goal is not to refactor the design in this pass. It is to answer: how well did
the general frontier-model work hold up once domain references were available?

## Corpus Anchors Used

- SmartHLS `axi_target` scalar arguments become on-chip storage reachable by
  AXI transactions, not free-running combinational inputs. See
  `~/.corpus/polarfire-control-corpus/raw/microchiptech.github.io/fpga-hls-docs20231hwarchitecturehtml.md`
  lines 86-92.
- The corpus-specific PID datapath note says `axi_target` coefficients are
  runtime-variable only with a live, nonconstant write path; tied or inactive
  AXI inputs allow constant propagation. See
  `~/.corpus/polarfire-control-corpus/raw/user-contributed/preserving-real-smarthls-pid-datapath.md`
  lines 27-46.
- That same note ranks proof artifacts: hierarchy/flat/post-layout evidence
  is stronger than warnings alone, while hierarchy CSVs are supporting evidence
  rather than semantic proof. See lines 72-103.
- The CoreVectorBlox handbook describes an AXI4-Lite control slave and states
  that partial `WSTRB` writes are undefined for the control slave. See
  `~/.corpus/polarfire-control-corpus/raw/download-soc.microsemi.com/fpgaoutgoingvectorbloxvectorblox-launch-collateral-v10microsemi-corevectorblox-i.md`
  lines 570-632.
- The same handbook says `Output Valid` is set when network outputs are valid,
  must be cleared once per invocation, and the `output_valid` interrupt mirrors
  that control bit. See lines 360-375 and 778-785.

## Verification Run

Local checks:

- `make hls-test-local`: passed. The local g++ build used the checked-in
  software-only `ap_fixpt` shim and reported `ALL TESTS PASSED`.
- `python3 tools/audit_libero_reports.py`: passed for the real PID closure.

Remote checks:

- `ssh -o BatchMode=yes -o ConnectTimeout=8 bee ...`: blocked. After full
  local access was available, noninteractive SSH returned `No route to host`.
  No Beelink `shls sw_run` or Libero rerun was performed in this pass.
- `tools/run_beelink_verification.sh`: added as the repeatable remote runner.
  It performs the same noninteractive SSH check, then runs SmartHLS software
  verification, optional Libero closure, report extraction, and this audit when
  the Beelink route is available.

## Scorecard

| Area | Result | Evidence |
|---|---|---|
| HLS behavior tests | Confirmed by local test | Existing bumpless, clamp, SEU, and watchdog chatter tests all pass through `hls-test-local`. |
| SmartHLS type choice | Confirmed by corpus | Repo uses `hls::ap_fixpt`; corpus/CLAUDE guidance warns against Xilinx `ap_fixed`. |
| Constant-folding diagnosis | Confirmed by corpus | Corpus says inactive AXI writes make coefficients constant-propagatable; `patch_smartdesign_axi_target_experiment.py` states and tests that exact hypothesis. |
| Real PID closure evidence | Mostly confirmed | `2026-04-29-pid-real` has positive parsed slack, 45 `nv_pid_top` hierarchy rows, summed PID footprint of 2390 4LUT / 1728 DFF / 25 Math blocks, and aggregate Math grows from 164 to 189. |
| Production AXI integration | Risky/contradicted | The real closure depends on an experimental FIC_0 tap, not an address-decoded AXI4-Lite slave slot. The corpus says a real FIC_0 interconnect path and readback are the safe rule. |
| Watchdog source | Risky/under-evidenced | Current hardware report uses MSS GPIO as heartbeat stimulus. The report audit now also flags CoreVectorBlox `output_valid` warnings: port not found, net undriven, and net floating. Corpus says `output_valid` is a level-like completion bit that should be edge-detected or deliberately treated as level-held. |
| Synplify pruning cleanliness | Needs review | Real closure has strong resource evidence but still contains PID-scoped pruning excerpts. The audit now separates likely critical multiplier pruning from expected fixed-width/state-bit pruning, but coefficient/full-width impact still needs toolchain review. |
| Safety proof claims | Correct but under-evidenced | Code has hard outer clamp, slew limiting, cooldown, and bumpless transfer. Full "cannot destabilize" claims still depend on plant/ZOH/delay assumptions documented as residual work. |
| Power claim | Under-evidenced | Closure report says SmartPower uses default toggle rates; corpus-backed conclusion is that workload/VCD-driven power is needed before treating power as final. |

## What The General Model Got Right

- It identified the key synthesis failure mode before the corpus was available:
  structural presence is not enough if AXI register writes are tied off or not
  semantically reachable.
- It built a discriminating experiment instead of only adding synthesis
  attributes. That matches the corpus recommendation that the fix is
  architectural observability, not `syn_keep`/`syn_noprune` first.
- It added useful behavioral HLS tests for bumpless transfer, clamp rejection,
  tightening, SEU defense, and watchdog chatter.
- It captured a real report bundle that shows a large `nv_pid_top` footprint
  and timing closure after the AXI-target experiment.

## What The Corpus Changes

- The experimental AXI tap should be treated as proof of hypothesis only. The
  corpus-backed production requirement is a real AXI4-Lite slave connection in
  the FIC_0 address map, including write response and readback.
- Report resource growth is strong evidence but not semantic proof. The next
  standard should include a mapped/post-compile netlist or cross-probed path
  from a software-written coefficient register to PID output/readback.
- CoreVectorBlox `output_valid` should not be treated as a raw heartbeat pulse.
  It mirrors a control bit that remains set until software clears it.
- Power numbers should be labeled as default-toggle estimates until a workload
  activity source is used.

## Improvement Backlog

1. Replace the experimental `patch_smartdesign_axi_target_experiment.py` path
   with a real address-decoded AXI4-Lite slot for `nv_pid_top` registers.
2. Add software-readable shadow/status CSRs for coefficients, current error,
   integrator, derivative term, pre/post-clamp output, saturation flags, and
   counters.
3. Wire CoreVectorBlox `output_valid` into watchdog refresh through an explicit
   edge detector and clock-domain synchronization if clocks differ.
4. Continue refining `tools/audit_libero_reports.py` with exact register-name
   matching once fresh Beelink logs are available.
5. Run `make beelink-verify TAG=<date-tag>` when `bee` is reachable to capture
   Beelink `shls sw_run`, SmartHLS interface reports, and exported SmartDesign
   Tcl into the verification record.
6. Add VCD/workload-driven SmartPower reporting before final SWaP claims.
7. Tighten README safety language so guarantees are stated only within the
   assumptions already documented in `docs/safety_architecture.md`.

## Bottom Line

The pre-corpus work performed well on the central failure diagnosis. It found
the real problem: the PID could be present in RTL while its meaningful datapath
was optimized away unless coefficients and outputs became observable. The
corpus makes the next step sharper: move from a successful discriminating
experiment to a production-grade, address-decoded AXI4-Lite integration with
readback and report gates.
