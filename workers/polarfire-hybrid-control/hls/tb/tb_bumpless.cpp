#include <iostream>
#include <cmath>
#include "nv_pid.hpp"

void nv_pid_top(freq_t, out_t, bool, gain_t, gain_t, gain_t, out_t, out_t, out_t&);

// Flush static state between tests: drain cooldown, zero u_AI_latch,
// and let PID integrator settle. Runs enough cycles to clear
// WATCHDOG_COOLDOWN_CYCLES (1000) plus extra for AI latch reset.
static void flush_state(gain_t Kp, gain_t Ki, gain_t Kd,
                         out_t out_min, out_t out_max) {
    out_t dummy;
    // Clear cooldown and run AI-active with u_AI=0 to zero u_AI_latch
    for (int i = 0; i < 1200; i++) {
        nv_pid_top(0.0, 0.0, false, Kp, Ki, Kd, out_min, out_max, dummy);
    }
}

// Run a single bumpless transfer scenario: 2 AI-active cycles then watchdog trip.
// Returns true if delta at transition matches expected_natural_step within tolerance.
static bool run_bumpless_test(
    const char *label,
    freq_t error, out_t u_AI,
    gain_t Kp, gain_t Ki, gain_t Kd,
    out_t out_min, out_t out_max,
    double tolerance
) {
    bool watchdog = false;
    out_t actuator_out;

    std::cout << "--- " << label << " ---\n";

    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max, actuator_out);
    std::cout << "Cycle 1 [AI Active]        Actuator Output: "
              << actuator_out.to_double() << " V\n";

    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max, actuator_out);
    out_t pre_fail_out = actuator_out;
    std::cout << "Cycle 2 [AI Active]        Actuator Output: "
              << actuator_out.to_double() << " V\n";

    // Simulate >1ms AI inference lag
    watchdog = true;
    u_AI = 0.0;
    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max, actuator_out);
    out_t post_fail_out = actuator_out;

    std::cout << "Cycle 3 [Watchdog Trip]    Actuator Output: "
              << actuator_out.to_double() << " V\n";

    double delta = post_fail_out.to_double() - pre_fail_out.to_double();
    double expected_natural_step = (Ki * error).to_double();
    std::cout << "Delta at transition:   " << delta << " V\n";
    std::cout << "Expected natural step: " << expected_natural_step << " V\n";

    bool pass = std::abs(delta - expected_natural_step) < tolerance;
    std::cout << (pass ? "PASS" : "FAIL") << ": Bumpless transfer "
              << (pass ? "successful" : "voltage jump detected") << ".\n\n";
    return pass;
}

int main() {
    std::cout << "=== SmartHLS NV-Magnetometer Bumpless Transfer Testbench ===\n\n";

    int failures = 0;

    // Test A: 5 kHz error, Ki=0.00002 → expected delta = 0.100 V
    if (!run_bumpless_test(
            "Test A: 5 kHz error (delta = 0.100 V)",
            5000.0, 0.225, 0.0001, 0.00002, 0.00001, 0.0, 5.0, 1e-3))
        failures++;

    // Flush static state between tests (drain cooldown, zero AI latch)
    flush_state(0.0001, 0.000019, 0.00001, 0.0, 5.0);

    // Test B: 4 kHz error, Ki=0.000019 → expected delta = 0.076 V
    if (!run_bumpless_test(
            "Test B: 4 kHz error (delta = 0.076 V)",
            4000.0, 0.225, 0.0001, 0.000019, 0.00001, 0.0, 5.0, 1e-3))
        failures++;

    if (failures == 0) {
        std::cout << "ALL TESTS PASSED.\n";
    } else {
        std::cout << failures << " TEST(S) FAILED.\n";
    }

    return failures;
}
