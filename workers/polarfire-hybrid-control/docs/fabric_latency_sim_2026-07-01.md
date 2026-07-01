# Fabric-internal PID latency — RTL cycle-count simulation (2026-07-01)

**Result: 6 cycles = 48 ns** (start-write AW-accept → actuator write-enable),
**constant across 128 iterations** at the 125 MHz PID fabric clock. **[TB]** —
simulated on the real two-slot RTL, not measured on silicon (see "What this
is / is not" below).

## What was measured

`tests/two_slot_sim/tb_pid_latency.v` (ModelSim Pro, Beelink, transcript:
`libero/reports/2026-07-01-fabric-latency-sim/vsim_latency_transcript.log`)
drives the same `pid_subsystem` RTL stack that `tb_actuator.v` verified
against silicon during the 2026-06-18 M0-demux fix, through real AXI
transactions, and counts clock cycles from the M0 start pulse (`0x008`) to
the `nv_pid_top` actuator-output write-enable pulse (`pid_actuator_we`), the
event whose value the silicon latches for the `0x60040844` readback.

| Event anchor | Latency | @ 8 ns/cycle (125 MHz) | n | spread |
|---|---|---|---|---|
| start AW-handshake accepted → actuator-we | **6 cycles** | **48 ns** | 128 | **0 (constant)** |
| start B-response retired → actuator-we | 4 cycles | 32 ns | 128 | 0 (constant) |

- 128 error values swept (alternating sign, growing magnitude through clamp
  saturation); zero missed events; final actuator readback `0xffff0000`
  (−1.0 Q16.16, out_min clamp) confirms a live, clamping datapath.
- The constant count is the direct RTL confirmation of the II=1 fixed-latency
  pipeline claim.
- Consistency: the Phase I report's "~48 ns pipeline fill (II=1, 125 MHz)"
  figure — previously derived from the SmartHLS scheduler report [MODEL] —
  is exactly reproduced by transaction-level RTL simulation on the shipped
  two-slot topology (start-accept anchor: 6 cycles = 48 ns).

## Why the cycle count carries to the placed design (P&R-invariance argument)

The two-slot builds meet timing with positive worst slack on every corner
(r10_s29 +0.977 ns, r13_s32 +1.006 ns on the 125 MHz PID domain), and the
flow uses no retiming/register-balancing options — so synthesis and P&R do
not add or remove pipeline stages; they only place/route the same registered
netlist. Cycle counts are therefore P&R-invariant for this single-clock
synchronous subsystem; only intra-cycle path delay varies, and STA bounds
that. **Caveat honestly stated:** this argument assumes no synthesis-inserted
register stages; a post-layout back-annotated (SDF) simulation or an
on-silicon counter would remove even that assumption.

## What this is / is not (claim discipline)

- **IS:** a [TB]-grade simulated bound. The "<150 µs" classical-loop budget
  is now backed by a measured-in-simulation 48 ns fabric compute latency on
  the real RTL — a ~3000× margin, with the AXI/CSR transaction path included
  in the measurement anchors.
- **IS NOT:** an on-silicon measurement. Userspace timing on the kit remains
  API/MMIO-bounded at 1 µs resolution (`docs/latency_measured_2026-06-21.md`:
  PID MMIO pulse+read median 4 µs — dominated by the U54→FIC→AXI round trip,
  not fabric compute). The on-silicon fabric-internal number still requires a
  latched hardware cycle counter (`acc_start`→actuator-valid) or a fixed
  Linux image with `rdcycle` enabled — tracked as the open remainder of
  fix-list row `EV-FABRIC-LATENCY`.

## Repro

```
ssh bee
cd ~/dev/projects/polarfire-hybrid-control
vsim -c -do sim/modelsim_pid_latency.do
```
Preconditions: `hls/hls_output/rtl/` at netlist vintage (do not re-run
`shls hw` casually — `rta_config.hpp` changed after the r12_s31/r13_s32
builds). Benign TFMPC warnings on unconnected optional ECC/debug ports of
the HLS-generated AXI slave are expected (9 warnings, 0 errors).
