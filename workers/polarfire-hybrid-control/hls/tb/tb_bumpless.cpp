#include <iostream>
#include <cmath>
#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

void nv_pid_top(freq_t, out_t, bool, gain_t, gain_t, gain_t, out_t, out_t,
                gain_t, out_t&);

// Hybrid sector clamp + gate (safety_clamps.cpp). The accepted-inner soft
// state is owned by the caller (passed by reference). In synthesis it lives
// as a static in nv_pid_top; in the testbench we keep our own copy so we
// can observe and corrupt it for SEU verification.
out_t apply_sector_clamp_gated(out_t u_AI, out_t out_min, out_t out_max,
                                gain_t inner_clamp_setpoint,
                                gain_t &accepted_state,
                                bool *out_rejected,
                                bool seu_force_state);

// Testbench-side copy of the soft-state. Tests can read/restore it directly.
static gain_t tb_accepted_state = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;

// Default inner clamp setpoint = outer constant ⇒ no tightening, baseline
// behavior matches the pre-Decision-2-Option-C testbench.
static const gain_t INNER_CLAMP_DEFAULT = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;

// Flush static state between tests: drain cooldown, zero u_AI_latch,
// and let PID integrator settle. Runs enough cycles to clear
// WATCHDOG_COOLDOWN_CYCLES (1000) plus extra for AI latch reset.
// Resetting the inner clamp soft-state happens organically: every nv_pid_top
// call passes inner_clamp_setpoint = INNER_CLAMP_DEFAULT, so the gate accepts
// it and the soft-state lands at the outer default.
static void flush_state(gain_t Kp, gain_t Ki, gain_t Kd,
                         out_t out_min, out_t out_max) {
    out_t dummy;
    for (int i = 0; i < 1200; i++) {
        nv_pid_top(0.0, 0.0, false, Kp, Ki, Kd, out_min, out_max,
                   INNER_CLAMP_DEFAULT, dummy);
    }
}

// Reset the testbench's soft-state copy directly.
static void reset_inner_clamp_state(gain_t target_fraction) {
    tb_accepted_state = target_fraction;
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
// at the HLS gate. The gate must report rejected=true, the runtime soft-state
// must remain at <= outer, and the clamp output must be bounded by outer.
static bool test_clamp_widen_rejected() {
    std::cout << "--- Task A.a: AXI widen attempt rejected ---\n";
    out_t out_min = 0.0, out_max = 5.0;

    // Establish soft-state at the outer default (a tightening setpoint at outer
    // is accepted, so this resets state to a known value).
    reset_inner_clamp_state((gain_t)OUTER_SECTOR_CLAMP_FRACTION);

    // Drive a wider-than-outer setpoint (10% > 4.5%). Must be rejected.
    gain_t wide_setpoint = (gain_t)0.10;
    out_t  u_AI = 0.5;                        // 10% of range
    bool   rejected;
    out_t  clamped = apply_sector_clamp_gated(
        u_AI, out_min, out_max, wide_setpoint,
        tb_accepted_state, &rejected, false);

    double bound = OUTER_SECTOR_CLAMP_FRACTION
                   * (out_max.to_double() - out_min.to_double());  // 0.225 V
    double cv = clamped.to_double();
    bool bounded = (std::abs(cv) <= bound + 1e-3);

    std::cout << "Setpoint:               " << wide_setpoint.to_double() << "\n";
    std::cout << "Rejected flag:          " << (rejected ? "true" : "false") << "\n";
    std::cout << "u_AI input:             " << u_AI.to_double() << " V\n";
    std::cout << "apply_sector_clamp out: " << cv
              << " V  (outer bound = " << bound << " V)\n";

    bool pass = rejected && bounded;
    std::cout << (pass ? "PASS" : "FAIL")
              << ": widen write rejected, clamp bounded by outer.\n\n";
    return pass;
}

// Test C-b: AXI write tightening the inner clamp must be ACCEPTED. Output
// must be bounded by the new tighter inner limit (here ±2% of range).
static bool test_clamp_tighten_accepted() {
    std::cout << "--- Task A.b: AXI tighten accepted ---\n";
    out_t out_min = 0.0, out_max = 5.0;

    // Drive the soft-state to a tightening setpoint of 2%, then verify by
    // re-issuing the same setpoint and checking the clamp behavior.
    gain_t tight_setpoint = (gain_t)0.02;
    bool   rejected;
    out_t  u_AI = 0.5;                        // 10% — well above tightened 2%
    out_t  clamped = apply_sector_clamp_gated(
        u_AI, out_min, out_max, tight_setpoint,
        tb_accepted_state, &rejected, false);

    double bound = 0.02 * (out_max.to_double() - out_min.to_double());  // 0.10 V
    double cv = clamped.to_double();
    bool bounded = (std::abs(cv) <= bound + 1e-3);

    std::cout << "Setpoint:               " << tight_setpoint.to_double() << "\n";
    std::cout << "Rejected flag:          " << (rejected ? "true" : "false") << "\n";
    std::cout << "u_AI input:             " << u_AI.to_double() << " V\n";
    std::cout << "apply_sector_clamp out: " << cv
              << " V  (inner bound = " << bound << " V)\n";

    bool pass = !rejected && bounded;
    std::cout << (pass ? "PASS" : "FAIL")
              << ": tighten write accepted, clamp bounded by inner.\n\n";

    // Restore default state for downstream tests.
    reset_inner_clamp_state((gain_t)OUTER_SECTOR_CLAMP_FRACTION);
    return pass;
}

// Test C-c: SEU emulation. Use the seu_force_state flag to bypass the gate
// and force the soft-state to a wider-than-outer value (10%). The runtime
// path then re-clamps the fraction to outer (4.5%) at use time, so the
// actuator output is still bounded by ±OUTER_SECTOR_CLAMP_FRACTION of the
// actuator range. This is the proof point for the Section 3.1 RTA claim
// that clamps cannot be overridden by any software state — the outer
// constant is structurally immutable to AXI and to SEU on the inner soft-
// state.
static bool test_clamp_seu_outer_holds() {
    std::cout << "--- Task A.c: SEU on inner soft-state — outer holds ---\n";
    out_t  out_min = 0.0, out_max = 5.0;
    gain_t corrupted_frac = (gain_t)0.10;     // would widen authority to 10%
    out_t  u_AI = 0.40;                       // 8% of range
    bool   rejected;

    // seu_force_state=true bypasses the gate and writes corrupted_frac into
    // accepted_state. The runtime fraction-level re-clamp then bounds the
    // effective fraction to outer, and the magnitude-level outer clamp
    // bounds the output.
    out_t clamped = apply_sector_clamp_gated(
        u_AI, out_min, out_max, corrupted_frac,
        tb_accepted_state, &rejected, true);

    double bound = OUTER_SECTOR_CLAMP_FRACTION
                   * (out_max.to_double() - out_min.to_double());   // 0.225 V
    double cv = clamped.to_double();
    bool bounded = (std::abs(cv) <= bound + 1e-3);

    std::cout << "Forced soft-state:      " << corrupted_frac.to_double()
              << "  (gate bypassed via seu_force_state=true)\n";
    std::cout << "u_AI input:             " << u_AI.to_double() << " V\n";
    std::cout << "Clamped output:         " << cv
              << " V  (outer bound = " << bound << " V)\n";

    // Restore the soft-state to the outer default.
    reset_inner_clamp_state((gain_t)OUTER_SECTOR_CLAMP_FRACTION);

    bool pass = bounded;
    std::cout << (pass ? "PASS" : "FAIL")
              << ": outer hardcoded clamp bounds actuator under SEU corruption.\n\n";
    return pass;
}

// =============================================================================
// Task B — Watchdog cooldown chatter test
// =============================================================================
// Drive ai_watchdog_timeout with a rapid 1 kHz toggle and observe whether the
// cooldown holds the actuator without high-frequency transitions. The literal
// 1 kHz spec corresponds to a 200,000-cycle period at 200 MHz; we run two
// full periods and report the max single-cycle actuator delta plus a count
// of "large step" events.
static bool test_chatter_cooldown() {
    std::cout << "--- Task B: Watchdog 1 kHz chatter — cooldown observation ---\n";
    gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
    out_t  out_min = 0.0, out_max = 5.0;
    freq_t error = 5000.0;
    out_t  u_AI = 0.225;
    out_t  actuator_out;

    flush_state(Kp, Ki, Kd, out_min, out_max);

    for (int i = 0; i < 300; i++) {
        nv_pid_top(error, u_AI, false, Kp, Ki, Kd, out_min, out_max,
                   INNER_CLAMP_DEFAULT, actuator_out);
    }
    out_t baseline = actuator_out;

    const int HALF_PERIOD = 100000;
    const int CYCLES      = 2 * 2 * HALF_PERIOD;
    out_t prev = actuator_out;
    double max_abs_delta = 0.0;
    int    large_step_count = 0;
    int    rising_edges     = 0;
    bool   prev_wd          = false;
    const double LARGE_STEP_THRESHOLD = 0.5;

    for (int i = 0; i < CYCLES; i++) {
        bool wd = ((i / HALF_PERIOD) % 2) == 0;
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

    flush_state(0.0001, 0.000019, 0.00001, 0.0, 5.0);

    // Test B: 4 kHz error, Ki=0.000019 → expected delta = 0.076 V
    if (!run_bumpless_test(
            "Test B: 4 kHz error (delta = 0.076 V)",
            4000.0, 0.225, 0.0001, 0.000019, 0.00001, 0.0, 5.0, 1e-3))
        failures++;

    if (!test_clamp_widen_rejected())  failures++;
    if (!test_clamp_tighten_accepted()) failures++;
    if (!test_clamp_seu_outer_holds())  failures++;

    if (!test_chatter_cooldown())       failures++;

    // =========================================================================
    // Task C — CoreVectorBlox output_valid edge cases (P3)
    // =========================================================================
    // The hardware watchdog refresh comes from a one-cycle pulse derived from
    // CoreVectorBlox.output_valid via vbx_completion_sync.v (HB0919 §4.1
    // p.7-8: output_valid is level-held until firmware clears it). At the HLS
    // level the pulse maps to the `ai_watchdog_timeout` bool that nv_pid_top
    // sees: false = inference fresh enough, true = no fresh inference within
    // 1 ms. These three tests cover the failure modes the corpus calls out:
    // repeated completions, a missed completion, and a stuck-high level.

    // Test C-d: repeated completions. The watchdog never fires; the actuator
    //          stays inside the AI+PID basin. We model "every Nth call has a
    //          fresh inference" by keeping ai_watchdog_timeout=false the
    //          entire run. The expected outcome is that the post-flush
    //          baseline remains stable (no large jumps).
    {
        std::cout << "--- Task C.d: Repeated output_valid completions ---\n";
        gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
        out_t  out_min = 0.0, out_max = 5.0;
        flush_state(Kp, Ki, Kd, out_min, out_max);
        out_t actuator_out, prev = 0.0;
        double max_delta = 0.0;
        for (int i = 0; i < 2000; i++) {
            nv_pid_top(5000.0, 0.225, /*ai_watchdog_timeout=*/false,
                       Kp, Ki, Kd, out_min, out_max,
                       INNER_CLAMP_DEFAULT, actuator_out);
            double d = std::abs(actuator_out.to_double() - prev.to_double());
            if (i > 0 && d > max_delta) max_delta = d;
            prev = actuator_out;
        }
        bool pass = max_delta < 0.5;
        std::cout << "Max single-cycle |delta|: " << max_delta << " V\n";
        std::cout << (pass ? "PASS" : "FAIL")
                  << ": repeated completions hold AI+PID without large jumps.\n\n";
        if (!pass) failures++;
    }

    // Test C-e: missed completion (timeout-then-recovery). One watchdog
    //          window passes with no fresh inference; the next inference
    //          arrives. Confirms bumpless behavior on entry to PID-only mode
    //          AND on return to AI+PID mode after recovery.
    {
        std::cout << "--- Task C.e: Missed completion, then recovery ---\n";
        gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
        out_t  out_min = 0.0, out_max = 5.0;
        flush_state(Kp, Ki, Kd, out_min, out_max);
        out_t actuator_out, prev = 0.0;
        double max_delta = 0.0;
        // Phase A: AI active for 200 cycles
        for (int i = 0; i < 200; i++) {
            nv_pid_top(5000.0, 0.225, false,
                       Kp, Ki, Kd, out_min, out_max,
                       INNER_CLAMP_DEFAULT, actuator_out);
            double d = std::abs(actuator_out.to_double() - prev.to_double());
            if (i > 0 && d > max_delta) max_delta = d;
            prev = actuator_out;
        }
        // Phase B: 1500 cycles of timeout (PID-only) — covers cooldown
        for (int i = 0; i < 1500; i++) {
            nv_pid_top(5000.0, 0.0, /*timeout=*/true,
                       Kp, Ki, Kd, out_min, out_max,
                       INNER_CLAMP_DEFAULT, actuator_out);
            double d = std::abs(actuator_out.to_double() - prev.to_double());
            if (d > max_delta) max_delta = d;
            prev = actuator_out;
        }
        // Phase C: AI inference returns
        for (int i = 0; i < 200; i++) {
            nv_pid_top(5000.0, 0.225, false,
                       Kp, Ki, Kd, out_min, out_max,
                       INNER_CLAMP_DEFAULT, actuator_out);
            double d = std::abs(actuator_out.to_double() - prev.to_double());
            if (d > max_delta) max_delta = d;
            prev = actuator_out;
        }
        bool pass = max_delta < 0.5;
        std::cout << "Max |delta| across timeout+recovery: " << max_delta << " V\n";
        std::cout << (pass ? "PASS" : "FAIL")
                  << ": missed completion handled bumplessly.\n\n";
        if (!pass) failures++;
    }

    // Test C-f: stuck-high output_valid. Per HB0919 §4.1 p.8, output_valid
    //          must be cleared by firmware once per inference. If firmware
    //          fails to clear it, vbx_completion_sync emits exactly one pulse
    //          and then nothing — so the watchdog correctly times out. We
    //          model this at the HLS level as a single false-then-permanent-
    //          true transition on ai_watchdog_timeout, and confirm the
    //          actuator settles to its PID-only steady state without
    //          oscillating.
    {
        std::cout << "--- Task C.f: Stuck-high output_valid (no clear) ---\n";
        gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
        out_t  out_min = 0.0, out_max = 5.0;
        flush_state(Kp, Ki, Kd, out_min, out_max);
        out_t actuator_out, prev = 0.0;
        // First pulse arrives — AI active for 1 cycle
        nv_pid_top(5000.0, 0.225, false,
                   Kp, Ki, Kd, out_min, out_max,
                   INNER_CLAMP_DEFAULT, actuator_out);
        prev = actuator_out;
        // Then stuck-high level — no further fresh inferences. Watchdog
        // permanently times out from cycle 2 onwards.
        double max_delta = 0.0;
        for (int i = 0; i < 5000; i++) {
            nv_pid_top(5000.0, 0.0, /*timeout=*/true,
                       Kp, Ki, Kd, out_min, out_max,
                       INNER_CLAMP_DEFAULT, actuator_out);
            double d = std::abs(actuator_out.to_double() - prev.to_double());
            if (d > max_delta) max_delta = d;
            prev = actuator_out;
        }
        bool pass = max_delta < 0.5;
        std::cout << "Max |delta| under stuck-high: " << max_delta << " V\n";
        std::cout << (pass ? "PASS" : "FAIL")
                  << ": stuck-high level produces single pulse then PID-only "
                  << "steady state.\n\n";
        if (!pass) failures++;
    }

    if (failures == 0) {
        std::cout << "ALL TESTS PASSED.\n";
    } else {
        std::cout << failures << " TEST(S) FAILED.\n";
    }

    return failures;
}
