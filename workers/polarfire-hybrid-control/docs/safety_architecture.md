# Safety Architecture

## Bounded Hybrid Simplex RTA

The AI feedforward path is treated as a sector-bounded nonlinearity within a Lur'e system framework. Absolute stability is guaranteed via the Circle Criterion, which requires three conditions:

1. **Sector saturation clamps (±5%)** — AI output bounded to a fraction of the actuator range. Implemented in `hls/src/safety_clamps.cpp` with a 4.5% hardware limit to guarantee ±5.0% compliance after worst-case fixed-point rounding.

2. **Bounded slew rate** — Per-cycle change in AI feedforward output is clamped. Prevents abrupt AI corrections from exciting plant resonances or violating du/dt assumptions in the stability proof.

3. **Asymptotically stable classical PID** — The baseline controller (without AI) must be stable on its own. The AI component adds feedforward corrections but cannot override the PID's stabilizing action.

## Watchdog and Bumpless Transfer

A hardware watchdog (200 MHz counter, 1 ms timeout) monitors AI inference latency. On timeout:
- The system transfers from AI+PID mode to pure PID mode
- Bumpless transfer absorbs the last AI output into the PID integrator: `I_new = I_old + u_AI_old`
- This prevents voltage discontinuities at the actuator output during mode transitions

## Implementation

| Mechanism | File | Function |
|-----------|------|----------|
| Sector clamp | `hls/src/safety_clamps.cpp` | `apply_sector_clamp()` |
| Slew limiter | `hls/src/safety_clamps.cpp` | `apply_slew_limit()` |
| Watchdog | `hls/src/watchdog.cpp` | `watchdog_check()` |
| Bumpless transfer | `hls/src/nv_pid.hpp` | `NVPID::bumpless_transfer()` |
| Config constants | `hls/include/rta_config.hpp` | `SECTOR_CLAMP_FRACTION`, `MAX_SLEW_PER_CYCLE`, `WATCHDOG_TIMEOUT_CYCLES` |
