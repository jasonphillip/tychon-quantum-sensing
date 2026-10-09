#include "nv_pid.hpp"
#include "../include/rta_config.hpp"

// Hardware Watchdog Timer
// Free-running counter on the 125 MHz PID fabric clock. Resets on each
// valid AI heartbeat. If AI inference exceeds the timeout, asserts the
// timeout signal which triggers bumpless transfer from AI+PID to pure PID.
//
// The timeout threshold is set by WATCHDOG_TIMEOUT_CYCLES in rta_config.hpp:
// 250,000 cycles at 125 MHz = 2.0 ms (current two-slot hardware image).
// (Historical r6_s25-era value: 200,000 cycles on a 200 MHz counter = 1.0 ms.)

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
