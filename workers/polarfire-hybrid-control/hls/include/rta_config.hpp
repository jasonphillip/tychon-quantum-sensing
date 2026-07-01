#ifndef RTA_CONFIG_HPP
#define RTA_CONFIG_HPP

#include "fp_types.hpp"

// Outer sector saturation clamp: hardcoded ±4.5% of actuator range.
// This is the absolute hardware safety bound — synthesized as an immutable
// constant, untouchable by any AXI transaction or software write. It is the
// last line of defense against single-event upset (SEU) of soft-state in the
// AXI-configurable inner clamp register (Decision 2 Option C, hybrid arch).
//
// Chosen as the MORE CONSERVATIVE (tighter) value of the design report's
// ±5% vs ±4.5% sector pair. The 4.5% hardware limit also guarantees ±5%
// compliance after worst-case Q16.16 fixed-point rounding.
//
// FLAG: the design report has a residual-clamp inconsistency (±2.5 µT vs
// ±2.25 µT). We adopt the tighter ±2.25 µT figure operationally — to be
// reconciled in Section 1.3 / 6.4 of the doc.
constexpr double OUTER_SECTOR_CLAMP_FRACTION = 0.045;

// Maximum slew rate per cycle for AI feedforward output (du_AI/dt bound)
// Units: out_t per clock cycle at 200 MHz
// Prevents abrupt AI output changes from destabilizing the control loop
constexpr double MAX_SLEW_PER_CYCLE = 0.001;

// Watchdog timeout: 250,000 cycles at 125 MHz = 2.0 ms
// Triggers AI isolation and bumpless transfer to pure PID on timeout
constexpr unsigned int WATCHDOG_TIMEOUT_CYCLES = 250000;

// Watchdog cooldown: minimum cycles in PID-only mode after a timeout
// before AI is allowed to re-enter. Prevents high-frequency limit-cycling
// (chattering) between AI+PID and pure PID modes.
// 1000 cycles at 200 MHz = 5.0 µs
constexpr unsigned int WATCHDOG_COOLDOWN_CYCLES = 1000;

// Clock frequency (Hz) — PolarFire SoC fabric clock
constexpr unsigned int CLOCK_FREQ_HZ = 200000000;

// Derivative filter time constant Tf for Kd·s/(1 + s·Tf).
// Chosen as ~10× above the assumed 3 kHz closed-loop control bandwidth
// (matching the ODMR modulation frequency upper bound). Filter corner =
// 1/(2π·Tf) ≈ 32 kHz, sufficient to roll off high-frequency derivative
// noise without consuming phase margin at the control bandwidth.
//
// Backward Euler discretization at Ts = 1/CLOCK_FREQ_HZ = 5 ns:
//   D[k] = a · D[k-1] + β · Kd · (error[k] - error[k-1])
//   a = Tf / (Ts + Tf)
//   β = Ts / (Ts + Tf) = 1 - a
//
// At Tf = 5 µs and Ts = 5 ns:
//   a ≈ 0.999000999, β ≈ 0.000999001
//
// FORMAL ARGUMENT: This is a synthesis-time constant. AXI writes cannot
// modify Tf, a, or β. The filter preserves the Phase I sector bound
// because at DC the gain is 1 (sector at DC unchanged) and at HF the
// filter attenuates (sector contracts). See docs/derivative_filter_design.md
// for the full derivation.
constexpr double DERIV_FILTER_TF_SECONDS = 5e-6;
constexpr double DERIV_FILTER_A          = 0.999000999;
constexpr double DERIV_FILTER_BETA       = 0.000999001;

#endif // RTA_CONFIG_HPP
