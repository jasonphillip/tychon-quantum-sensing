#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

// =============================================================================
// Section 3.1 RTA — Numerical Constants
// -----------------------------------------------------------------------------
//   Slew rate limit            : MAX_SLEW_PER_CYCLE        = 0.001 V / cycle
//                                (200 V/ms at 200 MHz fabric clock)
//   Watchdog cooldown duration : WATCHDOG_COOLDOWN_CYCLES  = 1000 cycles
//                                (5.0 µs at 200 MHz)
//   Watchdog reset hysteresis  : enforced by the cooldown above. After a
//                                watchdog rising edge, AI re-entry is gated
//                                by ai_active = !timeout && !in_cooldown,
//                                so the watchdog flag must FALL and the
//                                cooldown counter must reach 1000 cycles
//                                before the AI feedforward path re-engages.
// =============================================================================
// Hybrid Sector Saturation Clamp (Decision 2 Option C)
// -----------------------------------------------------------------------------
//   OUTER (hardcoded)  : OUTER_SECTOR_CLAMP_FRACTION = 0.045
//                        Defined `constexpr` in rta_config.hpp; synthesized
//                        as an immutable constant in the netlist. No AXI
//                        path can widen it; no SEU on soft-state can widen
//                        the effective bound past it. Chosen as the tighter
//                        of the design report's ±5% / ±4.5% sector pair.
//
//   INNER (AXI-config) : `inner_clamp_setpoint` AXI target register. Each
//                        cycle the gate validates the setpoint against the
//                        outer constant. Tightening writes (setpoint <= outer)
//                        update the accepted soft-state. Widening writes
//                        (setpoint > outer) are rejected at the HLS gate;
//                        the previously accepted value is retained, and the
//                        rejection status is latched on `s_inner_rejected`.
//
//   SEU robustness     : The runtime path in apply_sector_clamp() re-clamps
//                        the soft-state fraction itself to the outer constant
//                        before computing the magnitude, AND clamps once more
//                        at the magnitude level after the inner pass. If a
//                        single-event upset corrupts the accepted-inner
//                        register to a wider value, the actuator output is
//                        still bounded by ±OUTER_SECTOR_CLAMP_FRACTION of the
//                        actuator range.
// =============================================================================

// File-scope soft-state. Default at reset: accepted-inner equals the outer
// constant (i.e., no AXI tightening applied yet). Inner-rejected flag clears
// at reset and is latched true on any out-of-range AXI write.
static gain_t s_accepted_inner_fraction = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;
static bool   s_inner_rejected          = false;

// Per-cycle AXI write gate. Called from nv_pid_top with the current value
// of the inner_clamp_setpoint AXI register. Tightening writes update the
// soft-state and clear the rejection flag; widening writes leave the
// soft-state untouched and latch the rejection flag.
void gate_inner_clamp(gain_t setpoint_fraction) {
    #pragma HLS function inline
    gain_t outer_q = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;
    gain_t zero_q  = (gain_t)0;
    if (setpoint_fraction < zero_q || setpoint_fraction > outer_q) {
        s_inner_rejected = true;
    } else {
        s_accepted_inner_fraction = setpoint_fraction;
        s_inner_rejected = false;
    }
}

bool   get_inner_clamp_rejected()       { return s_inner_rejected; }
gain_t get_accepted_inner_fraction()    { return s_accepted_inner_fraction; }

#ifndef __SYNTHESIS__
// Testbench-only hook. Bypasses the gate to forcibly write the accepted-inner
// soft-state, simulating a single-event upset that flips bits in the register
// AFTER it was written. NOT compiled into the synthesized netlist.
void seu_force_inner_clamp_fraction(gain_t forced_fraction) {
    s_accepted_inner_fraction = forced_fraction;
}
#endif

// Sector Saturation Clamp (hybrid: AXI-tightened inner + hardcoded outer)
// Formal role: implements the nonlinear bound phi(y,t) in the
// Lur'e/Circle Criterion absolute stability proof.
out_t apply_sector_clamp(out_t u_AI, out_t out_min, out_t out_max) {
    #pragma HLS function inline

    out_t  range   = out_max - out_min;
    gain_t outer_q = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;
    gain_t zero_q  = (gain_t)0;

    // Read accepted-inner soft-state, then re-clamp the fraction itself to
    // [0, outer]. This is the SEU defense at the fraction level — even if the
    // soft-state is corrupted to a wider value, the effective fraction here
    // is bounded by OUTER_SECTOR_CLAMP_FRACTION before any magnitude is
    // computed.
    gain_t inner_q = s_accepted_inner_fraction;
    if (inner_q > outer_q) inner_q = outer_q;
    if (inner_q < zero_q)  inner_q = zero_q;

    out_t inner_mag = (out_t)(range * inner_q);
    out_t outer_mag = (out_t)(range * outer_q);
    out_t neg_inner = (out_t)(0) - inner_mag;
    out_t neg_outer = (out_t)(0) - outer_mag;

    // First clamp: AXI-tightened inner.
    out_t after_inner = u_AI;
    if (after_inner > inner_mag)      after_inner = inner_mag;
    else if (after_inner < neg_inner) after_inner = neg_inner;

    // Second clamp: outer hardcoded. Defense in depth at the magnitude level.
    if (after_inner > outer_mag) return outer_mag;
    if (after_inner < neg_outer) return neg_outer;
    return after_inner;
}

// Slew-Rate Limiter
// Bounds the per-cycle change in AI feedforward output.
// Prevents abrupt AI corrections from exciting plant resonances
// or violating the du/dt assumptions in the stability proof.
out_t apply_slew_limit(out_t u_AI_new, out_t u_AI_prev) {
    #pragma HLS function inline

    out_t delta = u_AI_new - u_AI_prev;
    out_t max_slew = (out_t)MAX_SLEW_PER_CYCLE;
    out_t neg_max_slew = (out_t)(0) - max_slew;

    if (delta > max_slew) return u_AI_prev + max_slew;
    if (delta < neg_max_slew) return u_AI_prev + neg_max_slew;
    return u_AI_new;
}
