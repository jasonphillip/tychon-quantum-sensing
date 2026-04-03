#ifndef NV_PID_HPP
#define NV_PID_HPP

#include <hls/ap_fixpt.hpp>

// Fixed-point type definitions
typedef hls::ap_fixpt<64, 34> freq_t; // Q34.30 (Hz Detuning Error)
typedef hls::ap_fixpt<32, 16> gain_t; // Q16.16 (Controller Gains)
typedef hls::ap_fixpt<32, 16> out_t;  // Q16.16 (Actuator Voltage)

class NVPID {
private:
    out_t integral;
    freq_t prev_error;
    out_t out_min;
    out_t out_max;

public:
    NVPID() : integral(0), prev_error(0), out_min(0), out_max(0) {}

    void set_limits(out_t min_val, out_t max_val) {
        out_min = min_val;
        out_max = max_val;
    }

    // Bumpless Transfer from AI feedforward to PID
    // Absorb last AI output into integrator: I_new = I_old + u_AI_old
    void bumpless_transfer(out_t u_AI_old) {
        integral = integral + u_AI_old;
        if (integral > out_max) integral = out_max;
        if (integral < out_min) integral = out_min;
    }

    out_t compute(freq_t error, gain_t Kp, gain_t Ki, gain_t Kd) {
        #pragma HLS function inline

        out_t p_term = (out_t)(Kp * error);
        integral = integral + (out_t)(Ki * error);
        if (integral > out_max) integral = out_max;
        if (integral < out_min) integral = out_min;

        out_t d_term = (out_t)(Kd * (error - prev_error));
        prev_error = error;

        out_t output = p_term + integral + d_term;
        if (output > out_max) output = out_max;
        if (output < out_min) output = out_min;

        return output;
    }
};

#endif // NV_PID_HPP
