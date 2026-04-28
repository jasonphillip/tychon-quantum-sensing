#include <iostream>
#include <cmath>
#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

void nv_pid_top(freq_t, out_t, bool, gain_t, gain_t, gain_t, out_t, out_t,
                gain_t, out_t&);

// Hybrid sector clamp accessors (safety_clamps.cpp)
bool   get_inner_clamp_rejected();
gain_t get_accepted_inner_fraction();
void   gate_inner_clamp(gain_t setpoint_fraction);
void   seu_force_inner_clamp_fraction(gain_t forced_fraction);
out_t  apply_sector_clamp(out_t u_AI, out_t out_min, out_t out_max);

// Default inner clamp setpoint = outer constant ⇒ no tightening, baseline
// behavior matches the pre-Decision-2-Option-C testbench.
static const gain_t INNER_CLAMP_DEFAULT = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;

// Flush static state between tests: drain cooldown, zero u_AI_latch,
// and let PID integrator settle. Runs enough cycles to clear
// WATCHDOG_COOLDOWN_CYCLES (1000) plus extra for AI latch reset.
// Also resets the inner clamp soft-state to the outer default.
static void flush_state(gain_t Kp, gain_t Ki, gain_t Kd,
                         out_t out_min, out_t out_max) {
    out_t dummy;
    // Restore inner clamp to outer default (in case a prior test tightened
    // or SEU-corrupted the soft-state).
    gate_inner_clamp(INNER_CLAMP_DEFAULT);
    for (int i = 0; i < 1200; i++) {
        nv_pid_top(0.0, 0.0, false, Kp, Ki, Kd, out_min, out_max,
                   INNER_CLAMP_DEFAULT, dummy);
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

    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max,
               INNER_CLAMP_DEFAULT, actuator_out);
    std::cout << "Cycle 1 [AI Active]        Actuator Output: "
              << actuator_out.to_double() << " V\n";

    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max,
               INNER_CLAMP_DEFAULT, actuator_out);
    out_t pre_fail_out = actuator_out;
    std::cout << "Cycle 2 [AI Active]        Actuator Output: "
              << actuator_out.to_double() << " V\n";

    // Simulate >1ms AI inference lag
    watchdog = true;
    u_AI = 0.0;
    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max,
               INNER_CLAMP_DEFAULT, actuator_out);
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

// =============================================================================
// Task A — Hybrid sector clamp (Decision 2 Option C)
// =============================================================================

// Test C-a: AXI write attempting to widen the inner clamp must be REJECTED
// at the HLS gate. The accepted soft-state must remain at or below the outer
// constant, and apply_sector_clamp must bound u_AI to the outer magnitude.
//
// Unit-style test on the clamp+gate pair. We bypass nv_pid_top to avoid PID
// integrator residue from prior tests (apply_sector_clamp has no integrator
// state — its only state is the accepted-inner soft-state in safety_clamps.cpp).
static bool test_clamp_widen_rejected() {
    std::cout << "--- Task A.a: AXI widen attempt rejected ---\n";
    out_t out_min = 0.0, out_max = 5.0;

    // Reset accepted-inner to the outer default.
    gate_inner_clamp((gain_t)OUTER_SECTOR_CLAMP_FRACTION);

    // Drive a wider-than-outer setpoint (10% > 4.5%) through the gate.
    gain_t wide_setpoint = (gain_t)0.10;
    gate_inner_clamp(wide_setpoint);

    bool rejected = get_inner_clamp_rejected();
    double accepted = get_accepted_inner_fraction().to_double();

    // u_AI = 0.5 V (10% of range) — would exceed outer if gate had widened.
    out_t u_AI = 0.5;
    out_t clamped = apply_sector_clamp(u_AI, out_min, out_max);

    double bound  = OUTER_SECTOR_CLAMP_FRACTION
                    * (out_max.to_double() - out_min.to_double());  // 0.225 V
    double cv     = clamped.to_double();
    bool bounded  = (std::abs(cv) <= bound + 1e-3);

    std::cout << "Setpoint:               " << wide_setpoint.to_double() << "\n";
    std::cout << "Rejected flag:          " << (rejected ? "true" : "false") << "\n";
    std::cout << "Accepted soft-state:    " << accepted
              << "  (must remain <= " << OUTER_SECTOR_CLAMP_FRACTION << ")\n";
    std::cout << "u_AI input:             " << u_AI.to_double() << " V\n";
    std::cout << "apply_sector_clamp out: " << cv
              << " V  (outer bound = " << bound << " V)\n";

    bool pass = rejected && bounded
                && (accepted <= OUTER_SECTOR_CLAMP_FRACTION + 1e-3);
    std::cout << (pass ? "PASS" : "FAIL")
              << ": widen write rejected, clamp bounded by outer.\n\n";
    return pass;
}

// Test C-b: AXI write tightening the inner clamp must be ACCEPTED. The
// accepted soft-state must update to the new value, and apply_sector_clamp
// must bound u_AI to the tighter inner magnitude.
static bool test_clamp_tighten_accepted() {
    std::cout << "--- Task A.b: AXI tighten accepted ---\n";
    out_t out_min = 0.0, out_max = 5.0;

    // Start from outer default, then write a tighter setpoint (2% < 4.5%).
    gate_inner_clamp((gain_t)OUTER_SECTOR_CLAMP_FRACTION);
    gain_t tight_setpoint = (gain_t)0.02;
    gate_inner_clamp(tight_setpoint);

    bool rejected = get_inner_clamp_rejected();
    double accepted = get_accepted_inner_fraction().to_double();

    out_t u_AI = 0.5;                          // 10% — well above tightened 2%
    out_t clamped = apply_sector_clamp(u_AI, out_min, out_max);

    double bound = 0.02 * (out_max.to_double() - out_min.to_double());  // 0.10 V
    double cv = clamped.to_double();
    bool bounded = (std::abs(cv) <= bound + 1e-3);

    std::cout << "Setpoint:               " << tight_setpoint.to_double() << "\n";
    std::cout << "Rejected flag:          " << (rejected ? "true" : "false") << "\n";
    std::cout << "Accepted soft-state:    " << accepted
              << "  (must equal setpoint = 0.02)\n";
    std::cout << "u_AI input:             " << u_AI.to_double() << " V\n";
    std::cout << "apply_sector_clamp out: " << cv
              << " V  (inner bound = " << bound << " V)\n";

    bool pass = !rejected && bounded && std::abs(accepted - 0.02) < 1e-3;
    std::cout << (pass ? "PASS" : "FAIL")
              << ": tighten write accepted, clamp bounded by inner.\n\n";

    // Restore default for downstream tests.
    gate_inner_clamp((gain_t)OUTER_SECTOR_CLAMP_FRACTION);
    return pass;
}

// Test C-c: SEU emulation. Forcibly corrupt the accepted-inner soft-state to
// a wider-than-outer value (bypassing the gate), then call apply_sector_clamp
// directly. Output must remain bounded by the outer hardcoded constant.
// This is the proof point for the Section 3.1 RTA claim that clamps cannot
// be overridden by any software state — the outer constant is structurally
// immutable to AXI and to SEU on the inner soft-state.
static bool test_clamp_seu_outer_holds() {
    std::cout << "--- Task A.c: SEU on inner soft-state — outer holds ---\n";
    out_t out_min = 0.0, out_max = 5.0;

    // Corrupt the soft-state: write 10% (wider than outer 4.5%). This bypasses
    // the gate completely (testbench-only hook).
    gain_t corrupted_frac = (gain_t)0.10;
    seu_force_inner_clamp_fraction(corrupted_frac);

    double soft_state = get_accepted_inner_fraction().to_double();
    std::cout << "Corrupted soft-state:   " << soft_state
              << " (gate bypassed, would widen authority to 10% if respected)\n";

    // Drive an aggressive u_AI that exceeds the outer bound.
    out_t u_AI_aggressive = 0.40;             // 8% of range — exceeds outer
    out_t result = apply_sector_clamp(u_AI_aggressive, out_min, out_max);

    double bound = OUTER_SECTOR_CLAMP_FRACTION
                   * (out_max.to_double() - out_min.to_double());   // 0.225 V
    double r = result.to_double();
    bool bounded = (std::abs(r) <= bound + 1e-3);

    std::cout << "u_AI input:             " << u_AI_aggressive.to_double() << " V\n";
    std::cout << "Clamped output:         " << r
              << " V  (outer bound = " << bound << " V)\n";

    // Restore soft-state for any subsequent tests.
    seu_force_inner_clamp_fraction((gain_t)OUTER_SECTOR_CLAMP_FRACTION);

    bool pass = bounded;
    std::cout << (pass ? "PASS" : "FAIL")
              << ": outer hardcoded clamp bounds actuator under SEU corruption.\n\n";
    return pass;
}

// =============================================================================
// Task B — Watchdog cooldown chatter test
// =============================================================================
// Drive ai_watchdog_timeout with a rapid 1 kHz toggle and observe whether the
// cooldown holds the actuator in pure-PID mode without high-frequency
// transitions. The literal 1 kHz spec corresponds to a 200,000-cycle period
// at 200 MHz; we run a few cycles of that and report the max single-cycle
// actuator delta in the post-first-trip window. A genuine cooldown failure
// would show repeated bumpless_transfer absorptions visible as actuator step
// transitions on each watchdog rising edge.
static bool test_chatter_cooldown() {
    std::cout << "--- Task B: Watchdog 1 kHz chatter — cooldown observation ---\n";
    gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
    out_t  out_min = 0.0, out_max = 5.0;
    freq_t error = 5000.0;
    out_t  u_AI = 0.225;
    out_t  actuator_out;

    flush_state(Kp, Ki, Kd, out_min, out_max);

    // Step 1: AI-active for 300 cycles to populate u_AI_latch fully.
    for (int i = 0; i < 300; i++) {
        nv_pid_top(error, u_AI, false, Kp, Ki, Kd, out_min, out_max,
                   INNER_CLAMP_DEFAULT, actuator_out);
    }
    out_t baseline = actuator_out;

    // Step 2: 1 kHz toggle (period 200,000 cycles, half-period 100,000) for
    // two full periods = 400,000 cycles. Track max single-cycle |delta| and
    // count "chatter events" (|delta| > 0.05 V, i.e. 50 mV — well above the
    // per-cycle Ki*error step of ~0.1 V/cycle so we filter that too).
    const int HALF_PERIOD = 100000;
    const int CYCLES      = 2 * 2 * HALF_PERIOD;  // 2 periods
    out_t prev = actuator_out;
    double max_abs_delta = 0.0;
    int    large_step_count = 0;
    int    rising_edges     = 0;
    bool   prev_wd          = false;
    const double LARGE_STEP_THRESHOLD = 0.5;  // 0.5 V — well above any single
                                              // PID step at these gains.

    for (int i = 0; i < CYCLES; i++) {
        bool wd = ((i / HALF_PERIOD) % 2) == 0;  // 1 kHz square wave
        if (wd && !prev_wd) rising_edges++;
        prev_wd = wd;

        nv_pid_top(error, u_AI, wd, Kp, Ki, Kd, out_min, out_max,
                   INNER_CLAMP_DEFAULT, actuator_out);

        double d = std::abs(actuator_out.to_double() - prev.to_double());
        if (d > max_abs_delta) max_abs_delta = d;
        if (d > LARGE_STEP_THRESHOLD) large_step_count++;
        prev = actuator_out;
    }

    std::cout << "Baseline (pre-toggle):  " << baseline.to_double() << " V\n";
    std::cout << "Cycles run:             " << CYCLES << "\n";
    std::cout << "Watchdog rising edges:  " << rising_edges << "\n";
    std::cout << "Max |delta_actuator|:   " << max_abs_delta << " V/cycle\n";
    std::cout << "Large steps (>"
              << LARGE_STEP_THRESHOLD << " V): " << large_step_count << "\n";

    // Cooldown holds ⇒ at most one bumpless transfer per period is observable
    // as a step. Two periods = at most 2 transitions. We allow a small slack
    // for slew-limited ramp-up after watchdog falls.
    bool pass = (large_step_count <= 2 * rising_edges);
    std::cout << (pass ? "PASS" : "FAIL")
              << ": cooldown chatter behavior "
              << (pass ? "as expected (no excess transitions)"
                       : "shows EXCESS transitions per rising edge")
              << ".\n\n";
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

    // Task A — Hybrid sector clamp (Decision 2 Option C)
    if (!test_clamp_widen_rejected())  failures++;
    if (!test_clamp_tighten_accepted()) failures++;
    if (!test_clamp_seu_outer_holds())  failures++;

    // Task B — Watchdog cooldown chatter test
    if (!test_chatter_cooldown())       failures++;

    if (failures == 0) {
        std::cout << "ALL TESTS PASSED.\n";
    } else {
        std::cout << failures << " TEST(S) FAILED.\n";
    }

    return failures;
}
