// tb_cascade.cpp — Cascade composition + safety-pipeline-survival testbench.
//
// Verifies the Phase II Tier-1 hierarchical INT8 cascade (P3-11B) under the
// canonical compose_int8 arithmetic from
//   tychon_shared_data.cascade.cascade_ref:compose_int8
// without modifying any HLS source. The composition is an upstream-of-safety
// transformation: it produces a single composite u_AI value per cycle, which
// is then fed to the existing nv_pid_top axi_target through the same
// simple-wire u_AI_in port that tb_bumpless.cpp uses.
//
// Three independent checks:
//   1. Differential composition matches expected_int8.csv (golden output).
//   2. Identity: when fine_int8 == z_fine elementwise, composed == coarse.
//   3. Safety-pipeline survival: feeding composed values to nv_pid_top keeps
//      actuator_out bounded by [out_min, out_max] across the fixture.
//
// The full sector-clamp accept/reject, SEU, watchdog-cooldown, and
// stuck-output_valid edge cases live in tb_bumpless.cpp — preserved
// untouched so r6_s25-equivalent verification gating remains canonical.

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <cmath>
#include <cstdint>
#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

void nv_pid_top(freq_t, out_t, bool, gain_t, gain_t, gain_t, out_t, out_t,
                gain_t, out_t&);

static const gain_t INNER_CLAMP_DEFAULT = (gain_t)OUTER_SECTOR_CLAMP_FRACTION;

// ---------------------------------------------------------------------------
// Fixture loader
// ---------------------------------------------------------------------------

static std::vector<int8_t> read_csv_int8(const std::string &path,
                                         std::size_t expected_count) {
    std::ifstream f(path);
    if (!f) {
        std::cerr << "FATAL: cannot open fixture " << path << "\n";
        std::exit(2);
    }
    std::vector<int8_t> out;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        std::stringstream ss(line);
        std::string cell;
        while (std::getline(ss, cell, ',')) {
            // Trim whitespace.
            while (!cell.empty() && std::isspace(static_cast<unsigned char>(cell.back())))
                cell.pop_back();
            while (!cell.empty() && std::isspace(static_cast<unsigned char>(cell.front())))
                cell.erase(cell.begin());
            if (cell.empty()) continue;
            int v = std::stoi(cell);
            if (v < -128 || v > 127) {
                std::cerr << "FATAL: " << path << " value " << v
                          << " out of int8 range\n";
                std::exit(2);
            }
            out.push_back(static_cast<int8_t>(v));
        }
    }
    if (out.size() != expected_count) {
        std::cerr << "FATAL: " << path << " loaded " << out.size()
                  << " values, expected " << expected_count << "\n";
        std::exit(2);
    }
    return out;
}

// ---------------------------------------------------------------------------
// C++ port of cascade_ref.compose_int8 (round_half_up branch).
// Locked to the synthetic fixture's manifest; not a general implementation.
//
// VectorBlox-SDK@4186f9a python/vbx/vbx/generate/vnnx_tflite.py line 416,
// MultiplyByQuantizedMultiplier, implements
//   result = int(x * quantized_multiplier + 2**(shift-1))
//   result = result // (2**shift)
// which is the canonical TFLite round_half_up pattern (.5 ties round toward
// +infinity for both positive and negative values). HW-05 T3.2.
// ---------------------------------------------------------------------------

static long long round_half_up(double x) {
    // .5 ties round toward +inf:
    //   0.5 + 0.5 = 1.0 -> floor 1
    //  -0.5 + 0.5 = 0.0 -> floor 0
    //  -1.5 + 0.5 = -1.0 -> floor -1
    return static_cast<long long>(std::floor(x + 0.5));
}

struct ComposeParams {
    double s_coarse, s_fine, s_comp;
    int z_coarse, z_fine, z_comp;
    bool saturate_int8;
};

static std::vector<int8_t> compose_int8_cpp(
        const std::vector<int8_t> &coarse,
        const std::vector<int8_t> &fine,
        const ComposeParams &p) {
    if (coarse.size() != fine.size()) {
        std::cerr << "FATAL: compose_int8_cpp: shape mismatch ("
                  << coarse.size() << " vs " << fine.size() << ")\n";
        std::exit(2);
    }
    std::vector<int8_t> out(coarse.size());
    for (std::size_t i = 0; i < coarse.size(); ++i) {
        double accum = (static_cast<double>(coarse[i]) - p.z_coarse)
                         * (p.s_coarse / p.s_comp)
                     + (static_cast<double>(fine[i])   - p.z_fine)
                         * (p.s_fine   / p.s_comp);
        long long y = round_half_up(accum) + p.z_comp;
        if (p.saturate_int8) {
            if (y > 127)  y = 127;
            if (y < -128) y = -128;
        }
        out[i] = static_cast<int8_t>(y);
    }
    return out;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static bool int8_vec_equal(const std::vector<int8_t> &a,
                           const std::vector<int8_t> &b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
        if (a[i] != b[i]) return false;
    return true;
}

static void print_int8_vec(const char *label, const std::vector<int8_t> &v) {
    std::cout << label;
    for (std::size_t i = 0; i < v.size(); ++i) {
        std::cout << static_cast<int>(v[i]);
        if (i + 1 < v.size()) std::cout << ",";
    }
    std::cout << "\n";
}

static void flush_state(gain_t Kp, gain_t Ki, gain_t Kd,
                         out_t out_min, out_t out_max) {
    out_t dummy;
    for (int i = 0; i < 1200; i++) {
        nv_pid_top(0.0, 0.0, false, Kp, Ki, Kd, out_min, out_max,
                   INNER_CLAMP_DEFAULT, dummy);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

static bool test_differential_composition(
        const std::vector<int8_t> &coarse,
        const std::vector<int8_t> &fine,
        const std::vector<int8_t> &expected,
        const ComposeParams &params) {
    std::cout << "--- Cascade T1: differential composition matches expected ---\n";
    auto composed = compose_int8_cpp(coarse, fine, params);
    bool pass = int8_vec_equal(composed, expected);
    print_int8_vec("Composed: ", composed);
    print_int8_vec("Expected: ", expected);
    std::cout << (pass ? "PASS" : "FAIL")
              << ": cascade composition matches golden expected_int8.\n\n";
    return pass;
}

static bool test_identity_residual(
        const std::vector<int8_t> &coarse,
        const ComposeParams &params) {
    std::cout << "--- Cascade T2: identity (fine = z_fine -> composed == coarse) ---\n";
    std::vector<int8_t> fine_zero(coarse.size(),
                                   static_cast<int8_t>(params.z_fine));
    auto composed = compose_int8_cpp(coarse, fine_zero, params);

    // Coarse values are already int8 and should pass through unchanged when
    // residual is zero. The general case is composed[i] ==
    // round_half_to_even(coarse[i] * (s_coarse/s_comp)) + z_comp; for the
    // synthetic fixture both ratios are 1.0 and z's are zero, so it reduces
    // to the identity.
    bool pass = int8_vec_equal(composed, coarse);
    print_int8_vec("Composed (fine = 0): ", composed);
    print_int8_vec("Coarse (reference):  ", coarse);
    std::cout << (pass ? "PASS" : "FAIL")
              << ": zero-residual composition is identity over coarse.\n\n";
    return pass;
}

static bool test_safety_pipeline_survival(const std::vector<int8_t> &composed,
                                           const ComposeParams &params) {
    std::cout << "--- Cascade T3: safety-pipeline-survival smoke ---\n";
    gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
    out_t  out_min = 0.0, out_max = 5.0;
    freq_t error = 1000.0;
    out_t  actuator_out;

    flush_state(Kp, Ki, Kd, out_min, out_max);

    // Convert each composite_int8 to a Q16.16 actuator-domain u_AI value.
    // u_AI_volts = (composite_int8 - z_comp) * s_comp.
    // Range for this fixture: [-128*0.01, 127*0.01] = [-1.28 V, 1.27 V].
    // The outer sector clamp (±OUTER_SECTOR_CLAMP_FRACTION × actuator span)
    // should bound the AI-attributable contribution to ±0.225 V regardless.
    double max_abs_actuator = 0.0;
    bool all_in_range = true;
    for (std::size_t i = 0; i < composed.size(); ++i) {
        double u_volts =
            (static_cast<double>(composed[i]) - params.z_comp) * params.s_comp;
        out_t u_AI = static_cast<double>(u_volts);
        nv_pid_top(error, u_AI, /*ai_watchdog_timeout=*/false,
                   Kp, Ki, Kd, out_min, out_max, INNER_CLAMP_DEFAULT,
                   actuator_out);
        double a = actuator_out.to_double();
        if (a < out_min.to_double() - 1e-3 ||
            a > out_max.to_double() + 1e-3) {
            all_in_range = false;
        }
        if (std::abs(a) > max_abs_actuator) max_abs_actuator = std::abs(a);
    }
    std::cout << "Max |actuator_out| across composed sweep: "
              << max_abs_actuator << " V\n";
    std::cout << "Actuator range bounds: ["
              << out_min.to_double() << ", " << out_max.to_double() << "] V\n";

    bool pass = all_in_range;
    std::cout << (pass ? "PASS" : "FAIL")
              << ": actuator stays in [out_min, out_max] under composed AI.\n\n";
    return pass;
}

int main() {
    std::cout << "=== Cascade composition + safety-pipeline-survival ===\n\n";

    // Fixture (matches manifest.json in the same directory).
    constexpr std::size_t N = 16;
    const std::string base = "hls/tb/stimulus/cascade_synthetic_v1/";
    auto coarse   = read_csv_int8(base + "coarse_int8.csv",   N);
    auto fine     = read_csv_int8(base + "fine_int8.csv",     N);
    auto expected = read_csv_int8(base + "expected_int8.csv", N);

    ComposeParams params{
        /* s_coarse */ 0.01,
        /* s_fine   */ 0.005,
        /* s_comp   */ 0.01,
        /* z_coarse */ 0,
        /* z_fine   */ 0,
        /* z_comp   */ 0,
        /* saturate */ true
    };

    int failures = 0;
    if (!test_differential_composition(coarse, fine, expected, params))
        failures++;
    if (!test_identity_residual(coarse, params))
        failures++;
    if (!test_safety_pipeline_survival(expected, params))
        failures++;

    if (failures == 0) {
        std::cout << "ALL CASCADE TESTS PASSED.\n";
    } else {
        std::cout << failures << " CASCADE TEST(S) FAILED.\n";
    }
    return failures;
}
