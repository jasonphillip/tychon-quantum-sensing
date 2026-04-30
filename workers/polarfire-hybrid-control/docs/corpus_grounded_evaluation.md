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
| HLS behavior tests | Confirmed by local test | Existing bumpless, clamp, SEU, and watchdog chatter tests all pass through `hls-test-local`. **Updated this branch:** added Tasks C.d/C.e/C.f covering repeated/missed/stuck-high `output_valid` scenarios; all pass. |
| SmartHLS type choice | Confirmed by corpus | Repo uses `hls::ap_fixpt`; corpus/CLAUDE guidance warns against Xilinx `ap_fixed`. |
| Constant-folding diagnosis | Confirmed by corpus | Corpus says inactive AXI writes make coefficients constant-propagatable; `patch_smartdesign_axi_target_experiment.py` states and tests that exact hypothesis. |
| Real PID closure evidence | Mostly confirmed | `2026-04-29-pid-real` has positive parsed slack, 45 `nv_pid_top` hierarchy rows, summed PID footprint of 2390 4LUT / 1728 DFF / 25 Math blocks, and aggregate Math grows from 164 to 189. Re-synthesis with this branch's patches is pending Beelink reachability — see overnight-r* tags. |
| Production AXI integration | Locally fixed; pending Beelink synth | `patch_smartdesign_pid_axi.py` (new) supersedes the experiment with a full read+write channel rewire and 8'hFF wstrb (corpus rule HB0919 p.12). Residual two-slot interconnect work is now scoped explicitly as Phase II SmartDesign canvas surgery. |
| Watchdog source | Locally fixed; opt-in via flag | `vbx_completion_sync.v` (new, 2-FF + edge detect) and `--vbx-output-valid` flag in `patch_smartdesign_watchdog.py` give a corpus-aligned path (HB0919 §6.4 p.15). Default still GPIO test stimulus; flag fails fast if `Vectorblox_ss_output_valid` is not exposed at top level. |
| Synplify pruning cleanliness | Pending Beelink synth | Strict audit gates now flag CL189/CL260 critical pruning hits as fail-fast violations on `pid-real` / `overnight-*` / `*-strict` bundles. Existing `2026-04-29-pid-real` correctly fails strict mode with 4 critical hits + 3 output_valid wiring issues — the gap this branch's patches must close. |
| Safety proof claims | Correct, claim-tightened | README replaces "cannot destabilize" with sector-bounded language and a pointer to residual Phase II proof obligations. `docs/safety_architecture.md` adds an explicit Residual Phase II Proof Obligations table (plant model, ZOH, transport delay, derivative filter, ReLU sector verification, VCD-driven SmartPower) with corpus citations. |
| Power claim | Claim-tightened | Power table relabeled as "default-toggle estimate" with explicit "preliminary until workload-driven" language. Workload-driven SmartPower remains future work. |
| Status observability | Locally added, pending Beelink synth | `pid_io_block.v` extended with coefficient shadow registers, status CSRs (saturation, watchdog event counter, ai_active, cooldown, integrator), and an axi_write_count register that proves the slave is alive. New ports wired in `patch_smartdesign_top.py`. |

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
