# Reshaped C–G bring-up plan (Linux) — 2026-06-15

**Status: PLAN FOR REVIEW. Nothing here that re-architects the fabric or re-spins the
bitstream will be executed without your explicit go-ahead.** The Linux userspace path
(rungs C–G on the *current* bitstream) is staged and ready to run the moment the kit is
booted.

## Context — what changed since the old A–I plan

The old plan (`~/.claude/plans/goal-take-the-existing-wobbly-hollerith.md`) was **bare-metal
A–I**. Three things moved it:
1. **Rung A is done** — PROGRAM PASS on Production MPFS250T (2026-06-15); the seed_7
   V250-in-fabric bitstream is on silicon and verified (digests match).
2. **Linux/Yocto adopted** for the MSS side (rungs C–G) — the only Microchip-supported
   VectorBlox-on-Icicle runtime (`docs/track0_bringup_runbook.md` decision record). The
   PID safety/real-time is in fabric, so Linux doesn't touch it.
3. The 2026-06-02 **strategy audit** flagged two reframes beyond the runtime: the
   *eavesdropper* bitstream (Risk 1) and the *replayed-CSV* demo (Risk 3 + safety Risk 5).

Already staged (so C–G is mostly "run it"): the Linux `.wic` (on bee), `pid_poke` +
`vnnx_smoke` (cross-built RISC-V ELFs, on bee+NAS), the `.vnnx` (on bee), the
`seed7_vbx_pid.dtso` overlay, and the copy-paste runbook (`firmware/linux/README.md`).
F.1 confirmed the seed_7 MSS has eMMC/SD + eNVM + MMUART0/1 enabled, so SD-boot is viable.

---

## THE decision for you — eavesdropper bitstream vs clean two-slot integration

This is the audit's highest-leverage call (Risk 1) and it gates demo credibility.

**Current (on silicon): the "eavesdropper" `pid_io_block`.** The MSS read path is severed
(reads fall through to `nv_pid_top_top`), and writes collide — only **3 of the gain/limit
addresses round-trip cleanly** (Kd `0x14` / out_min `0x18` / out_max `0x1C`); `Kp`/`Ki`/
`acc_start` are aliased to stimulus inputs. It *works* for a demo, but a reviewer's
engineer who opens the netlist sees a tap hack, and you'd have to narrate caveats live.

**Alternative: the clean two-slot integration** (`docs/smartdesign_two_slot_canvas_runbook.md`,
`libero/hdl/pid_csr_block.v` — 18 real CSRs incl. `csr_version=0x00010000`). Proper AXI
slave, full read/write, no collisions. **Cost:** a Libero GUI canvas session + re-synth +
re-P&R + re-export + re-program + **re-extract the axi4target offsets** (Risk 6 — the
firmware offsets change). It's testbench-validated (D.1/D.2/D.3 pass) but **NOT
netlist-validated**, so first netlist carries real integration risk. A new bitstream also
means re-programming (allowed per your rule: new bitstream → branch + log, keep rung-A
`.job` recoverable).

**My recommendation: do the Linux C–G bring-up on the CURRENT eavesdropper bitstream
FIRST, then do the clean two-slot re-integration BEFORE the reviewer-facing capture (rung I)
— not before C–G.** Reasons:
- The Linux path has its own unknowns (HSS version match, `udmabuf-nc`, `/dev/mem` strict
  mode, V250 clock). Prove the whole stack end-to-end on what's *already on silicon* —
  it's staged and free — before spending a bitstream re-spin.
- The 3 clean addresses + V250 inference + the closed-loop/safety framing (below) are
  enough to validate the path and even to demo, honestly, with the eavesdropper.
- Then upgrade to the clean CSR block for the *credibility* pass, on a branch, with the
  rung-A `.job` preserved — sequencing the integration risk after the path is proven.

If you'd rather re-integrate first (e.g. you want the clean netlist before *any* firmware
demo), say so and I'll run the canvas session on a branch — but that's the
re-architecture+re-bitstream I won't start without your nod.

---

## Reshaped rung sequence (Linux)

| Rung | Old (bare-metal) | New (Linux) | State |
|---|---|---|---|
| **C** | min UART firmware | **Boot Linux from SD** (image staged) + apply DT overlay | ready — needs SD flash + boot (hands-on) |
| **D** | identify MMUART0 COM | **Falls out of first boot** — watch COM7–10 (HSS=MMUART0, login=MMUART1) | folds into C |
| **E** | AXI loopback (bare-metal) | **`pid_poke`** /dev/mem MMIO; clean loopback at 0x14/0x18/0x1C | tool built + staged |
| **F** | `.vnnx` on V250 (bare-metal) | **`vnnx_smoke`** via VBX SoC runtime (poll + udmabuf-nc) | tool built + staged |
| **G** | ODMR replay | **closed-loop replay + safety stunt** (below) | needs authoring after C–F prove out |

C–F are essentially "boot + run the staged tools" (see `firmware/linux/README.md`). The
real new authoring is **G** plus the demo reframe.

---

## Demo reframe (audit Risk 3 + Risk 5) — build into rung G

The weakest artifact is "stream a CSV, plot vs a synthetic baseline." Upgrade it:

1. **Closed-loop in software (Risk 3).** Feed `pid_poke`/`vnnx_smoke` actuator output back
   through a host-side ODMR plant model so the error trace **converges** (the loop closes),
   and overlay **PID-only vs PID+NN** so the NN's value is legible. This is the
   CartPole/F1TENTH-shaped story (a closed loop, not a replay). Host harness on spark1;
   `tools/compare_corrections.py` produces the convergence + RMS-deviation plot.
2. **Safety stunt (Risk 5).** Make the sector-bound *demonstrable*, not asserted:
   - inject an out-of-sector / oversized NN output → show the **±5 % clamp + slew limiter
     visibly bound it** in the trace;
   - stall the inference path → show the **1 ms watchdog trip → bumpless transfer to pure
     PID** with no actuator discontinuity (the `tb_bumpless` logic already exists in HDL —
     promote it to a live on-silicon stunt).
   Pair with an honest caveat card listing the 6 open RPOs as the funded-work roadmap.

UART flow control for the stream: firmware/host echoes each row after inference; the
spark1 harness blocks on echo (prevents silent RX overrun).

---

## What needs YOU (batched)

- **Hands-on:** flash SD, set SD boot, insert SD, press RESET, read COM7–10 (rung C/D).
- **Decision:** eavesdropper-now vs clean-two-slot-first (above). My rec: Linux first,
  clean integration before rung I.
- **ASK-FIRST (destructive):** HSS eNVM reflash *if* the factory HSS is too old to boot the
  2026.04 image (try factory HSS first). Any clean-two-slot re-bitstream + re-program.
- **Possible base-DTS edit:** add `udmabuf-ddr-nc0` if the image lacks it (rung F).

## Verification (path proven when all hold)
1. Linux logs in on a COM port; `/dev/uioN` with name "vbx" after overlay.
2. `pid_poke r 0x14` returns what `pid_poke w 0x14` wrote (AXI loopback on silicon).
3. `vnnx_smoke` prints "inference complete" + dequantized outputs (V250 runs on silicon).
4. Rung G: host plot shows the loop **converging**, PID-only vs PID+NN overlaid, and the
   clamp + watchdog stunts visibly firing.

## Cross-refs
- Runbook: `firmware/linux/README.md` · Decision record: `docs/track0_bringup_runbook.md`
- Audit: `docs/whole_process_strategy_audit_2026-06-02.md` · Register map:
  `docs/seed_7_register_map_2026-05-04.md` / `docs/fic_0_address_map_2026-05-18.md`
- Old plan (superseded for C–G): `~/.claude/plans/goal-take-the-existing-wobbly-hollerith.md`
