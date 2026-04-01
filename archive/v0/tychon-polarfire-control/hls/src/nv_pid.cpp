#include "nv_pid.hpp"

void nv_pid_top(
    freq_t error,
    out_t u_AI_in,
    bool ai_watchdog_timeout,
    gain_t Kp, gain_t Ki, gain_t Kd,
    out_t out_min, out_t out_max,
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

    // Bare wires for real-time nanosecond datapath
    #pragma HLS interface argument(error) type(simple)
    #pragma HLS interface argument(u_AI_in) type(simple)
    #pragma HLS interface argument(ai_watchdog_timeout) type(simple)
    #pragma HLS interface argument(actuator_out) type(simple)

    static NVPID pid;
    static bool prev_watchdog = false;
    static out_t u_AI_latch = 0;

    pid.set_limits(out_min, out_max);

    // Watchdog rising edge detection for bumpless handoff
    if (ai_watchdog_timeout && !prev_watchdog) {
        pid.bumpless_transfer(u_AI_latch);
    }

    out_t u_pid = pid.compute(error, Kp, Ki, Kd);

    out_t total_out;
    if (ai_watchdog_timeout) {
        total_out = u_pid;
    } else {
        // TODO: Insert safety_clamps (sector saturation + slew-rate) on u_AI_in HERE
        // u_AI_clamped = apply_sector_clamp(u_AI_in);  // ±5% of (out_max - out_min)
        // u_AI_safe = apply_slew_limit(u_AI_clamped, u_AI_latch);  // du/dt bounded
        // total_out = u_AI_safe + u_pid;
        total_out = u_AI_in + u_pid;  // TEMPORARY: replace with clamped version
        u_AI_latch = u_AI_in;
    }

    if (total_out > out_max) total_out = out_max;
    if (total_out < out_min) total_out = out_min;

    actuator_out = total_out;
    prev_watchdog = ai_watchdog_timeout;
}
