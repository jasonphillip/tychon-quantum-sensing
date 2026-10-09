#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

// Forward declarations for safety clamp functions (safety_clamps.cpp)
out_t apply_sector_clamp_gated(out_t u_AI, out_t out_min, out_t out_max,
                                gain_t inner_clamp_setpoint,
                                gain_t &accepted_state,
                                bool *out_rejected,
                                bool seu_force_state);
out_t apply_slew_limit(out_t u_AI_new, out_t u_AI_prev);

void nv_pid_top(
    freq_t error,
    out_t u_AI_in,
    bool ai_watchdog_timeout,
    gain_t Kp, gain_t Ki, gain_t Kd,
    out_t out_min, out_t out_max,
    gain_t inner_clamp_setpoint,
    out_t &actuator_out
) {
    #pragma HLS function top
    #pragma HLS function pipeline II(1)

    // AXI4 Target for CPU/VectorBlox configuration
    #pragma HLS interface control type(axi_target)
    #pragma HLS interface argument(Kp) type(axi_target)
    #pragma HLS interface argument(Ki) type(axi_target)
    #pragma HLS interface argument(Kd) type(axi_target)
    #pragma HLS interface argument(out_min) type(axi_target)
    #pragma HLS interface argument(out_max) type(axi_target)
    #pragma HLS interface argument(inner_clamp_setpoint) type(axi_target)

    // Bare wires for real-time nanosecond datapath
    #pragma HLS interface argument(error) type(simple)
    #pragma HLS interface argument(u_AI_in) type(simple)
    #pragma HLS interface argument(ai_watchdog_timeout) type(simple)
    #pragma HLS interface argument(actuator_out) type(simple)

    static NVPID pid;
    static bool prev_watchdog = false;
    static out_t u_AI_latch = 0;
    static unsigned int cooldown_counter = 0;
    static bool in_cooldown = false;
    // Inner sector clamp soft-state. Default at reset = outer constant
    // (no AXI tightening applied). SmartHLS infers this as an internal
    // register because it lives in the top function body.
    static gain_t inner_clamp_state = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;

    pid.set_limits(out_min, out_max);

    // Watchdog rising edge detection for bumpless handoff
    if (ai_watchdog_timeout && !prev_watchdog) {
        pid.bumpless_transfer(u_AI_latch);
        in_cooldown = true;
        cooldown_counter = 0;
    }

    // Cooldown timer: after watchdog timeout, hold PID-only mode for
    // WATCHDOG_COOLDOWN_CYCLES before allowing AI re-entry. Prevents
    // high-frequency limit-cycling (chattering) between AI+PID and PID-only.
    if (in_cooldown) {
        if (cooldown_counter < WATCHDOG_COOLDOWN_CYCLES) {
            cooldown_counter++;
        } else {
            in_cooldown = false;
        }
    }

    bool ai_active = !ai_watchdog_timeout && !in_cooldown;

    out_t u_pid = pid.compute(error, Kp, Ki, Kd);

    out_t total_out;
    if (ai_active) {
        // TODO: Phase II — implement valid/ready handshake for u_AI_in.
        // Currently assumes u_AI_in is always valid (simplified signal path).
        // A stale inference result is bounded by the sector clamp and slew
        // limiter, but a proper handshake would avoid processing stale data.

        // Safety chain: hybrid sector bound (AXI inner + hardcoded outer)
        // → slew limit → hybrid sector bound again → sum with PID
        // → final actuator saturation. Re-clamping handles a tightened bound
        // immediately, even when the previous AI latch exceeds it.
        // MAX_SLEW_PER_CYCLE = 0.001 corresponds to 125 V/ms at 125 MHz.
        // seu_force_state=false in synthesized hardware (testbench-only knob).
        bool dummy_rejected;
        out_t u_AI_clamped = apply_sector_clamp_gated(
            u_AI_in, out_min, out_max,
            inner_clamp_setpoint,
            inner_clamp_state,
            &dummy_rejected,
            false);
        out_t u_AI_safe = apply_slew_limit(u_AI_clamped, u_AI_latch);
        u_AI_safe = apply_sector_clamp_gated(
            u_AI_safe, out_min, out_max,
            inner_clamp_setpoint,
            inner_clamp_state,
            &dummy_rejected,
            false);
        total_out = u_AI_safe + u_pid;
        u_AI_latch = u_AI_safe;
    } else {
        total_out = u_pid;
    }

    if (total_out > out_max) total_out = out_max;
    if (total_out < out_min) total_out = out_min;

    actuator_out = total_out;
    prev_watchdog = ai_watchdog_timeout;
}
