#ifndef RTA_CONFIG_HPP
#define RTA_CONFIG_HPP

#include "fp_types.hpp"

// Sector saturation clamp: ±4.5% of actuator range in hardware
// Provides margin for fixed-point rounding to guarantee ±5.0% compliance
// with Lur'e/Circle Criterion formal stability bounds (Addendum §3.1)
constexpr double SECTOR_CLAMP_FRACTION = 0.045;

// Maximum slew rate per cycle for AI feedforward output (du_AI/dt bound)
// Units: out_t per clock cycle at 200 MHz
// Prevents abrupt AI output changes from destabilizing the control loop
constexpr double MAX_SLEW_PER_CYCLE = 0.001;

// Watchdog timeout: 200,000 cycles at 200 MHz = 1.0 ms
// Triggers AI isolation and bumpless transfer to pure PID on timeout
constexpr unsigned int WATCHDOG_TIMEOUT_CYCLES = 200000;

// Clock frequency (Hz) — PolarFire SoC fabric clock
constexpr unsigned int CLOCK_FREQ_HZ = 200000000;

#endif // RTA_CONFIG_HPP
