#ifndef WD_TRIP_START_H
#define WD_TRIP_START_H

#include <stdint.h>

/* Offsets within the mapped 0x60040000 slot-3 page. */
#define WD_TRIP_ACC_START   (0x008u / 4u)
#define WD_TRIP_ERROR_LOW   (0x810u / 4u)
#define WD_TRIP_ERROR_HIGH  (0x814u / 4u)
#define WD_TRIP_U_AI        (0x818u / 4u)
#define WD_TRIP_WATCHDOG    (0x854u / 4u)

typedef struct {
    uint64_t forced_starts;
    uint32_t last_watchdog_raw;
    int armed;
} wd_trip_start_state;

/* Start disarmed: at program start the timeout is usually still high from the idle period,
 * and forcing a start then would put the controller PID-only for its first cooldown.
 * The rule arms the first time it reads the timeout low, i.e. once the loop is running. */
#define WD_TRIP_START_INIT {0, 0u, 0}

/* A test may replace the MMIO write to record its order. */
#ifndef WD_TRIP_START_WRITE
#define WD_TRIP_START_WRITE(base, index, value) \
    do { (base)[(index)] = (value); __sync_synchronize(); } while (0)
#endif

/* error_q34_30 is the signed fixed-point error word; u_ai_q16 is Q16.16. */
static inline int wd_trip_start(volatile uint32_t *base, wd_trip_start_state *state,
                                int64_t error_q34_30, uint32_t u_ai_q16)
{
    uint32_t raw = base[WD_TRIP_WATCHDOG];
    __sync_synchronize();
    state->last_watchdog_raw = raw;
    if (!(raw & 1u)) {
        state->armed = 1;
        return 0;
    }
    if (!state->armed)
        return 0;

    WD_TRIP_START_WRITE(base, WD_TRIP_ERROR_LOW, (uint32_t)error_q34_30);
    WD_TRIP_START_WRITE(base, WD_TRIP_ERROR_HIGH, (uint32_t)((uint64_t)error_q34_30 >> 32));
    WD_TRIP_START_WRITE(base, WD_TRIP_U_AI, u_ai_q16);
    WD_TRIP_START_WRITE(base, WD_TRIP_ACC_START, 1u);
    state->armed = 0;
    ++state->forced_starts;
    return 1;
}

#endif
