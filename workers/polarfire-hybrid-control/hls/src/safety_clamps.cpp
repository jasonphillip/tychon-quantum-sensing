#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

// Sector Saturation Clamp
// Clamps AI feedforward output to ±4.5% of actuator range.
// The 4.5% hardware limit guarantees ±5.0% compliance after
// worst-case fixed-point rounding in Q16.16 arithmetic.
//
// Formal role: implements the nonlinear bound phi(y,t) in the
// Lur'e/Circle Criterion absolute stability proof.
out_t apply_sector_clamp(out_t u_AI, out_t out_min, out_t out_max) {
    #pragma HLS function inline

    out_t range = out_max - out_min;
    out_t clamp_mag = (out_t)(range * SECTOR_CLAMP_FRACTION);
    out_t pos_limit = clamp_mag;
    out_t neg_limit = (out_t)(0) - clamp_mag;

    if (u_AI > pos_limit) return pos_limit;
    if (u_AI < neg_limit) return neg_limit;
    return u_AI;
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
