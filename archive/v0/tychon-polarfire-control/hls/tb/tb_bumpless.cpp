#include <iostream>
#include <cmath>
#include "nv_pid.hpp"

void nv_pid_top(freq_t, out_t, bool, gain_t, gain_t, gain_t, out_t, out_t, out_t&);

int main() {
    freq_t error = 5000.0;    // 5 kHz frequency error
    out_t u_AI = 2.5;          // AI outputting 2.5V feedforward
    bool watchdog = false;

    gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
    out_t out_min = 0.0, out_max = 5.0;
    out_t actuator_out;

    std::cout << "--- SmartHLS NV-Magnetometer Bumpless Transfer Testbench ---\n\n";

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
    std::cout << "\nDelta at transition:   " << delta << " V\n";
    std::cout << "Expected natural step: " << expected_natural_step << " V\n";

    if (std::abs(delta - expected_natural_step) < 1e-5) {
        std::cout << "\nPASS: Bumpless transfer successful.\n";
    } else {
        std::cout << "\nFAIL: Voltage jump detected.\n";
    }

    return 0;
}
