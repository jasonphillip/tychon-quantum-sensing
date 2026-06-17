# Two-Slot Integration — working notes (2026-06-17, branch bringup/2026-06-17-two-slot-pid)

Live engineering log for the clean two-slot PID integration. Evidence-labeled per
`docs/agent_ground_truth_contract.md`.

## Confirmed topology (seed7_vbx201_v250 netlist, CONFIRMED via synth + grep)

FIC_0 path: MSS FIC_0_AXI4_INITIATOR -> FIC_0_PERIPHERALS `AXI4mslave0` slave-interface
-> `FIC0_INITIATOR` crossbar (COREAXI4INTERCONNECT 2.9.100, NUM_SLAVES=4) -> peripheral slots.
NOTE the naming trap: top-level `FIC_0_PERIPHERALS_1_AXI4mslave0_*` is the MSS<->crossbar
bus (also wired to MSS_WRAPPER_1.FIC_0_AXI4_TARGET for DDR), NOT a peripheral slot.
The real peripheral slots are the crossbar-internal `FIC0_INITIATOR_AXI4mslaveN_*` nets.

Crossbar slot map (FIC0_INITIATOR.v SLAVEn_START/END_ADDR):
- SLAVE0 0x60001000-0x60001fff -> DMA_CONTROLLER CTRL (CoreAXI4DMAController) — OCCUPIED, needed
- SLAVE1 0x60000000-0x60000fff -> (occupied instance) — OCCUPIED
- SLAVE2 0x60030000-0x60030fff -> Vectorblox_ss (V250) — OCCUPIED
- SLAVE3 0x60040000-0x60040fff -> FREE (was GND-tied)  <-- the only free slot

CONSEQUENCE: nv_pid_top never had a crossbar slot; the seed_7 eavesdropper hacked it
onto the MSS bus tap (severed reads). A clean integration needs TWO AXI slaves
(nv_pid_top.axi4target for gains + pid_csr for error/u_ai inject + actuator readback)
but there is ONE free slot -> a 1->2 AXI splitter on SLAVE3 (the runbook's
CoreAXI4Interconnect 1M x 2S, hand-written here as axi4_demux2.v).

## Address plan (SLAVE3 0x60040000, 4 KiB, split by addr[11])
- 0x60040000-0x600407ff  M0 -> nv_pid_top.axi4target  (gains Kp/Ki/Kd/out_min/out_max/inner_clamp)
- 0x60040800-0x60040fff  M1 -> pid_csr_axi4_wrap       (liveness/version, error/u_ai inject, actuator/watchdog readback)
  pid_csr_axi4_wrap passes awaddr[10:0] to pid_csr_block so its regs appear at the 0x800 base.

## Datapath (all LOCAL inside FIC_0_PERIPHERALS — nv_pid_top moves IN from top)
- pid_csr.error_shadow_out[63:0] -> nv_pid_top.error
- pid_csr.u_ai_shadow_out[31:0]  -> nv_pid_top.u_AI_in
- nv_pid_top.actuator_out_write_data[31:0] -> pid_csr.tap_post_clamp_in
- Vectorblox_ss output_valid -> vbx_pulse_gen -> watchdog_timer -> nv_pid_top.ai_watchdog_timeout + pid_csr.tap_watchdog_in

## Widths (CONFIRMED)
- crossbar SLAVE3 / demux S: AXI4 full, 64-bit data, 38-bit addr, 9-bit ID
- nv_pid_top.axi4target: 64-bit data, 6-bit addr [5:0], 1-bit ID  (slice/pad at M0 wiring)
- pid_csr_axi4_wrap: presents full AXI4 (bridges to AXI4-Lite-32 pid_csr_block)

## Watchdog (RESOLVED 2026-06-17) — fabric clock = 125 MHz (PF_CCC_C0 OUT0 = 50 MHz x 5/2)
- DASHBOARD-DEMO build: 62_500_000 cycles = 500 ms  (host-paced; NOT the 1 ms safety bound)
- SAFETY-SPEC build:     125_000 cycles    = 1 ms    (the real bound)
- patch_two_slot.py --watchdog-cycles selects; both built from the same netlist.

## Status
- v1 patch (nv_pid_top onto top-level AXI4mslave0) -> SYNTH FAILED: multiple-drivers
  (that net is the MSS bus, already driven). Root-caused to the topology trap above.
- v2 (this plan): nv_pid_top + pid_csr behind axi4_demux2 on SLAVE3, all inside FIC_0_PERIPHERALS.
- No critical pruning on our logic in v1 synth (CL279/CL260/CL189 hits are all Microchip IP).
