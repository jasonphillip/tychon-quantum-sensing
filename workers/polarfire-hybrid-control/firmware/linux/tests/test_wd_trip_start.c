#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static unsigned writes[8];
static unsigned nwrites;
static void record_write(volatile uint32_t *base, unsigned index, uint32_t value)
{
    assert(nwrites < sizeof(writes) / sizeof(writes[0]));
    writes[nwrites++] = index;
    base[index] = value;
}
#define WD_TRIP_START_WRITE(base, index, value) record_write(base, index, value)
#include "../wd_trip_start.h"

int main(void)
{
    uint32_t page[0x1000 / sizeof(uint32_t)] = {0};
    /* Production initial state: disarmed, so a timeout already high at start is ignored. */
    wd_trip_start_state cold = WD_TRIP_START_INIT;
    page[WD_TRIP_WATCHDOG] = 1u;
    assert(wd_trip_start(page, &cold, 0, 0u) == 0 && cold.forced_starts == 0 && !cold.armed);
    page[WD_TRIP_WATCHDOG] = 0u;
    assert(wd_trip_start(page, &cold, 0, 0u) == 0 && cold.armed);
    nwrites = 0;
    wd_trip_start_state state = {.armed = 1};
    const int64_t error = INT64_C(-0x123456789);
    const uint32_t u_ai = 0xabcdef01u;

    assert(wd_trip_start(page, &state, error, u_ai) == 0);
    assert(state.armed && state.forced_starts == 0 && nwrites == 0);

    page[WD_TRIP_WATCHDOG] = 0x15u;
    assert(wd_trip_start(page, &state, error, u_ai) == 1);
    assert(state.last_watchdog_raw == 0x15u);
    assert(nwrites == 4);
    assert(writes[0] == WD_TRIP_ERROR_LOW);
    assert(writes[1] == WD_TRIP_ERROR_HIGH);
    assert(writes[2] == WD_TRIP_U_AI);
    assert(writes[3] == WD_TRIP_ACC_START);
    assert(page[WD_TRIP_ERROR_LOW] == (uint32_t)error);
    assert(page[WD_TRIP_ERROR_HIGH] == (uint32_t)((uint64_t)error >> 32));
    assert(page[WD_TRIP_U_AI] == u_ai);
    assert(page[WD_TRIP_ACC_START] == 1u);
    assert(!state.armed && state.forced_starts == 1);

    for (int i = 0; i < 10; ++i)
        assert(wd_trip_start(page, &state, error, u_ai) == 0);
    assert(nwrites == 4 && state.forced_starts == 1);

    page[WD_TRIP_WATCHDOG] = 0x16u;
    assert(wd_trip_start(page, &state, error, u_ai) == 0);
    assert(state.armed && state.last_watchdog_raw == 0x16u);
    page[WD_TRIP_WATCHDOG] = 0x17u;
    assert(wd_trip_start(page, &state, error, u_ai) == 1);
    assert(nwrites == 8 && state.forced_starts == 2 && !state.armed);
    puts("wd_trip_start: PASS (two episodes, ordered writes)");
    return 0;
}
