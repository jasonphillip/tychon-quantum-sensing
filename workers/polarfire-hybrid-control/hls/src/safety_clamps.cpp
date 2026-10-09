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
//   INNER (AXI-config) : The runtime `inner_clamp_setpoint` argument is the
//                        AXI target register. Each call validates it against
//                        the outer constant. Tightening writes (setpoint <=
//                        outer) update the function-local accepted soft-
//                        state; widening writes leave the soft-state
//                        untouched and report rejection via *out_rejected.
//
//   SEU robustness     : The runtime path re-clamps the soft-state fraction
//                        itself to the outer constant before computing the
//                        magnitude, AND clamps once more at the magnitude
//                        level after the inner pass. If a single-event upset
//                        corrupts the accepted-inner soft-state to a wider
//                        value, the actuator output is still bounded by
//                        ±OUTER_SECTOR_CLAMP_FRACTION of the actuator range.
//
//   SmartHLS note      : The accepted-inner state is held as a `static` in
//                        the body of nv_pid_top and passed to this function
//                        by reference. SmartHLS reliably infers statics
//                        defined inside the top function as internal
//                        registers; statics inside helper functions get
//                        hoisted to external Scalar Memory interfaces even
//                        when the helper is force-inlined.
// =============================================================================

// Sector Saturation Clamp with integrated AXI tightening gate.
//
// State (`accepted_state`) is passed by reference. The caller owns the
// storage — typically a `static` declared inside nv_pid_top, which SmartHLS
// infers as an internal register.
//
// Args:
//   u_AI                 : raw AI feedforward sample
//   out_min, out_max     : actuator range
//   inner_clamp_setpoint : AXI-driven setpoint for the inner clamp fraction
//   accepted_state       : caller-owned soft-state for the most recently
//                          accepted inner clamp fraction. Updated on a
//                          tightening setpoint or under seu_force_state.
//   out_rejected         : optional pointer; set true if the gate rejected a
//                          widening setpoint, false otherwise
//   seu_force_state      : testbench-only knob; when true, bypasses the gate
//                          and forces accepted_state to inner_clamp_setpoint
//                          (for SEU defense-in-depth verification). nv_pid_top
//                          always passes false; SmartHLS constant-folds the
//                          bypass path away in synthesis.
//
// Formal role: implements the nonlinear bound phi(y,t) in the
// Lur'e/Circle Criterion absolute stability proof.
out_t apply_sector_clamp_gated(out_t u_AI, out_t out_min, out_t out_max,
                                gain_t inner_clamp_setpoint,
                                gain_t &accepted_state,
                                bool *out_rejected,
                                bool seu_force_state) {
    #pragma HLS function inline

    gain_t outer_q = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;
    gain_t zero_q  = (gain_t)0;

    bool rejected = false;
    if (seu_force_state) {
        // Testbench-only: bypass gate to corrupt the soft-state.
        accepted_state = inner_clamp_setpoint;
    } else {
        if (inner_clamp_setpoint < zero_q || inner_clamp_setpoint > outer_q) {
            rejected = true;
        } else {
            accepted_state = inner_clamp_setpoint;
        }
    }
    if (out_rejected != 0) *out_rejected = rejected;

    // Read the soft-state and re-clamp the fraction itself to [0, outer].
    // SEU defense at the fraction level — even if accepted_state is corrupted
    // to a wider value, the effective fraction here is bounded by outer
    // before any magnitude is computed.
    gain_t inner_q = accepted_state;
    if (inner_q > outer_q) inner_q = outer_q;
    if (inner_q < zero_q)  inner_q = zero_q;

    out_t range     = out_max - out_min;
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
