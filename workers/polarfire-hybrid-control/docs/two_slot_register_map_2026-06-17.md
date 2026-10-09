# Two-Slot PID — Register Map & Address Plan (2026-06-17)

Canonical address/register reference for the clean two-slot integration
(branch `bringup/2026-05-18-real-silicon` → `bringup/2026-06-17-two-slot-pid`).
Supersedes the eavesdropper map in `docs/fic_0_address_map_2026-05-18.md` and
`docs/seed_7_register_map_2026-05-04.md`. Topology evidence:
`docs/two_slot_integration_notes_2026-06-17.md`.

## FIC_0 crossbar slot map (CONFIRMED, FIC0_INITIATOR.v params)

| Slot | Base | Occupant |
|---|---|---|
| SLAVE0 | `0x60001000` | DMA_CONTROLLER CTRL (CoreAXI4DMAController) — **NOT the PID** |
| SLAVE1 | `0x60000000` | (base-design instance) |
| SLAVE2 | `0x60030000` | CoreVectorBlox V250 control |
| SLAVE3 | `0x60040000` | **pid_subsystem** (the only free slot) |

`pid_subsystem` splits SLAVE3's 4 KiB by `axi4_demux2` (`SEL_BIT=11`):

| Sub-window | Base | Slave |
|---|---|---|
| low 2 KiB | `0x60040000` | `nv_pid_top.axi4target` (SmartHLS PID gains) |
| high 2 KiB | `0x60040800` | `pid_csr` (`pid_csr_axi4_wrap` → `pid_csr_block`) |

## Slot M0 — nv_pid_top.axi4target gains @ 0x60040000 (Q16.16, RW)

| Address | Reg | Notes |
|---|---|---|
| `0x60040008` | acc_start | write 1 = start / read run state |
| `0x6004000C` | Kp | proportional gain |
| `0x60040010` | Ki | integral gain |
| `0x60040014` | Kd | derivative gain |
| `0x60040018` | out_min | actuator lower clamp |
| `0x6004001C` | out_max | actuator upper clamp |

(6-bit `axi4target` decode; software writes these to set the live PID gains —
this is the "software write-then-readback on the surviving SmartHLS slave"
architectural-survival proof, now on a real decoded crossbar sub-slot.)

## Slot M1 — pid_csr @ 0x60040800 (`pid_csr_block`)

| Address | Reg | Dir | Notes |
|---|---|---|---|
| `0x60040800` | axi_write_count | RO | monotonic accepted-write counter (liveness) |
| `0x60040804` | csr_version | RO | `0x00010000` |
| `0x60040810` | error_low | RW | error[31:0]  (Q34.30) — host PID stimulus |
| `0x60040814` | error_high | RW | error[63:32] |
| `0x60040818` | u_ai | RW | Q16.16 AI feedforward — host injects NN output |
| `0x60040820`..`834` | Kp/Ki/Kd/out_min/out_max/inner_clamp shadow | RW | aux shadow regs (gains are authoritative at M0) |
| `0x60040844` | post_clamp_out | RO | **actuator output (Q16.16), LIVE** (nv_pid_top tap) |
| `0x60040854` | watchdog_csr | RO | bit0 = watchdog timeout (**LIVE**), bits[31:1] = trip count |

**Tied-off taps (DISCLOSED, not hidden):** `pre_clamp_out` (`+0x840`),
`integrator` (`+0x848`), `derivative` (`+0x84C`), `saturation_csr` (`+0x850`),
`cooldown` (`+0x858`), `ai_active` (`+0x85C`) read 0 — the current `nv_pid_top`
exposes only its final actuator output as a port (per the user-confirmed
pragmatic scope; exposing the rest needs a SmartHLS re-spin). `post_clamp_out`
and `watchdog_csr` are the two LIVE taps.

## Datapath wiring (pid_subsystem, all internal)

```
pid_csr.error_shadow_out -> nv_pid_top.error
pid_csr.u_ai_shadow_out  -> nv_pid_top.u_AI_in
nv_pid_top.actuator_out_write_data -> pid_csr.tap_post_clamp_in (-> 0x60040844)
V250 output_valid -> vbx_pulse_gen -> watchdog_timer -> nv_pid_top.ai_watchdog_timeout
                                                       + pid_csr.tap_watchdog_in (-> 0x60040854 bit0)
```

## Watchdog — fabric clock = 125 MHz (PF_CCC_C0 OUT0 = 50 MHz × 5/2), CONFIRMED

| Build | `WATCHDOG_TIMEOUT_CYCLES` | Time @125 MHz | Use |
|---|---|---|---|
| **dashboard-demo** | `62_500_000` | **500 ms** (host-paced; NOT the safety bound) | Rung G stable telemetry, plumbing/bumpless-transfer proof |
| **watchdog-2ms (current hardware image, r13_s32)** | `250_000` | **2 ms** (the current real bound; programmed 2026-06-21) | safety-bound demo + trip-time measurement target |
| ~~safety-spec 1 ms~~ (superseded 2026-06-21) | `125_000` | 1 ms | the 1 ms safety-clone builds failed (see `libero/reports/2026-06-21-safety-*/`); 2 ms adopted as the near-term bound |

All from the same netlist via `patch_two_slot.py --watchdog-cycles`. Artifacts
are kept separate by filename + sha256 + program log (see release checklist).
NOTE (updated 2026-07-01): the HLS `rta_config` 200 MHz clock assumption was
stale and has been corrected to 125 MHz; `rta_config.hpp` now carries
`WATCHDOG_TIMEOUT_CYCLES = 250_000` (2 ms @125 MHz), matching the programmed
r13_s32 image.

## GATE 1a synthesis evidence (demo build, 2026-06-17)

- `SYNTHESIZE OK`, exit 0. No multiple-drivers/conflicts (the v1 topology bug is fixed).
- No unresolved modules; no whole-instance prune (CL168/BN362) of our logic;
  gains/integrator/derivative registers NOT pruned. (CL189/CL260 hits on
  `nv_pid_top` are benign constant-bit prunes — mem_size FIFO depth, II=1 counter,
  unused fixed-point/bool upper bits — inherent to the SmartHLS RTL.)
- Survival: pid_subsystem, axi4_demux2, nv_pid_top, pid_csr_axi4_wrap,
  pid_csr_block, watchdog_timer, vbx_pulse_gen all present in the netlist.
- Footprint: 109 DSP (45 Mults + 64 MultAdds), 54491 LUTs → real datapath
  (not a paper shell). nv_pid_top = 2199 netlist refs, pid_subsystem = 1426.
- Address map confirmed (table above).
