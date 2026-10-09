#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

// Hardware Watchdog Timer (Addendum §3.1)
// Free-running counter at 200 MHz. Resets on each valid AI heartbeat.
// If AI inference exceeds 1 ms (200,000 cycles), asserts timeout signal
// which triggers bumpless transfer from AI+PID to pure PID mode.
//
// The timeout threshold is set by WATCHDOG_TIMEOUT_CYCLES in rta_config.hpp.
// 200 MHz * 1 ms = 200,000 cycles.

bool watchdog_check(bool ai_heartbeat) {
    #pragma HLS function top
    #pragma HLS function pipeline II(1)

    #pragma HLS interface argument(ai_heartbeat) type(simple)

    static unsigned int counter = 0;
    static bool timed_out = false;

    if (ai_heartbeat) {
        counter = 0;
        timed_out = false;
    } else {
        if (counter < WATCHDOG_TIMEOUT_CYCLES) {
            counter++;
        } else {
            timed_out = true;
        }
    }

    return timed_out;
}
