// watchdog_trip.c - fabric watchdog clear->trip time measurement (idfix2 2 ms image).
//
// Passively tight-polls the M1 watchdog CSR (0x60040854: bit0 = timeout LIVE,
// bits[31:1] = trip count) and timestamps BOTH edges of bit0:
//   1 -> 0  : a V250 completion pulse cleared the watchdog  (t_clear)
//   0 -> 1  : the watchdog counter reached timeout          (t_trip)
// trip_time = t_trip - t_clear. Both edges are observed by the same tight
// MMIO poll loop (~sub-us per read), so no cross-process clock sync is
// needed and the measurement is self-contained.
//
// External stimulus (separate shell): fire ONE V250 inference every ~100 ms
// so the watchdog alternates cleared -> tripped, e.g.
//   while true; do /root/bringup/v250_pid_loop --rows 1 ...; sleep 0.1; done
// (exact one-shot flags: see v250_pid_loop.c usage / the finite-smoke logs).
// Each stimulus iteration produces one (clear, trip) pair here.
//
// Expected on the r13_s32 image: 250,000 cycles @ 125 MHz = 2.000 ms.
// Resolution: MMIO poll period (typ. < 1 us) + rdtime 1 MHz tick (1 us).
//
// Usage: watchdog_trip [n_events (default 100)] [max_wall_seconds (default 120)]
// Output: per-event CSV lines on stdout + summary stats; exit 0 on n_events
// collected, 3 on wall-timeout with fewer events.
//
// Follows the pid_latency.c conventions: touches ONLY the 0x60040000 slot-3
// page (never 0x60001000); read-only except nothing -- this tool performs NO
// register writes at all.

#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

#define PAGE       0x1000UL
#define SLOT3_PAGE 0x60040000UL

#define R_CSR_VERSION     0x60040804UL
#define R_WATCHDOG        0x60040854UL

static inline uint64_t rdtime_raw(void)
{
    uint64_t v;
#if defined(__riscv)
    __asm__ volatile("rdtime %0" : "=r"(v));
#else
    v = 0;
#endif
    return v;
}

static uint32_t read_timebase_hz(void)
{
    FILE *f = fopen("/proc/device-tree/cpus/timebase-frequency", "rb");
    if (!f) {
        return 0;
    }
    unsigned char b[4] = {0, 0, 0, 0};
    size_t n = fread(b, 1, sizeof(b), f);
    fclose(f);
    if (n != sizeof(b)) {
        return 0;
    }
    return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
}

static uint64_t nsec_now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static int cmp_u64(const void *a, const void *b)
{
    uint64_t va = *(const uint64_t *)a;
    uint64_t vb = *(const uint64_t *)b;
    return (va > vb) - (va < vb);
}

static uint64_t percentile_u64(uint64_t *sorted, int n, double p)
{
    int idx = (int)ceil(p * (double)n) - 1;
    if (idx < 0) {
        idx = 0;
    }
    if (idx >= n) {
        idx = n - 1;
    }
    return sorted[idx];
}

static void print_stats(const char *name, const char *suffix, uint64_t *values, int n)
{
    qsort(values, (size_t)n, sizeof(values[0]), cmp_u64);
    printf("%s_%s min=%" PRIu64 " median=%" PRIu64 " p95=%" PRIu64 " p99=%" PRIu64 " max=%" PRIu64 "\n",
           name, suffix,
           values[0],
           percentile_u64(values, n, 0.50),
           percentile_u64(values, n, 0.95),
           percentile_u64(values, n, 0.99),
           values[n - 1]);
}

static volatile uint32_t *map_slot3(void)
{
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem");
        return NULL;
    }
    volatile uint32_t *m = mmap(NULL, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)SLOT3_PAGE);
    close(fd);
    if (m == MAP_FAILED) {
        perror("mmap slot3");
        return NULL;
    }
    return m;
}

static inline volatile uint32_t *regp(volatile uint32_t *base, unsigned long addr)
{
    return base + ((addr - SLOT3_PAGE) / 4);
}

static inline uint32_t rd(volatile uint32_t *base, unsigned long addr)
{
    uint32_t v = *regp(base, addr);
    __sync_synchronize();
    return v;
}

int main(int argc, char **argv)
{
    int n_events = (argc > 1) ? atoi(argv[1]) : 100;
    int max_wall_s = (argc > 2) ? atoi(argv[2]) : 120;
    if (n_events < 1 || n_events > 100000 || max_wall_s < 1 || max_wall_s > 3600) {
        fprintf(stderr, "usage: %s [n_events 1..100000] [max_wall_seconds 1..3600]\n", argv[0]);
        return 2;
    }

    uint32_t timebase_hz = read_timebase_hz();
    printf("watchdog_trip n_events=%d max_wall_s=%d timebase_hz=%" PRIu32 "\n",
           n_events, max_wall_s, timebase_hz);

    volatile uint32_t *base = map_slot3();
    if (!base) {
        return 1;
    }

    uint32_t csr_version = rd(base, R_CSR_VERSION);
    uint32_t wd0 = rd(base, R_WATCHDOG);
    printf("csr_version=0x%08x watchdog_raw=0x%08x (timeout=%u trip_count=%u)\n",
           csr_version, wd0, wd0 & 1u, wd0 >> 1);
    if (csr_version != 0x00010000u) {
        fprintf(stderr, "unexpected csr_version\n");
        return 1;
    }

    uint64_t *trip_ns = calloc((size_t)n_events, sizeof(uint64_t));
    uint64_t *trip_ticks = calloc((size_t)n_events, sizeof(uint64_t));
    if (!trip_ns || !trip_ticks) {
        fprintf(stderr, "calloc failed\n");
        return 1;
    }

    printf("polling for clear->trip pairs (fire one V250 inference every ~100 ms in another shell)...\n");
    printf("event,trip_ns,trip_ticks,trip_count_delta,poll_gap_max_ns\n");
    fflush(stdout);

    uint64_t deadline_ns = nsec_now() + (uint64_t)max_wall_s * 1000000000ull;
    int collected = 0;
    uint32_t prev = rd(base, R_WATCHDOG);
    uint64_t t_clear_ns = 0, t_clear_tk = 0;
    uint32_t count_at_clear = prev >> 1;
    int have_clear = 0;
    uint64_t last_poll_ns = nsec_now();
    uint64_t gap_max_ns = 0;

    while (collected < n_events) {
        uint32_t cur = rd(base, R_WATCHDOG);
        uint64_t now_ns = nsec_now();
        uint64_t now_tk = rdtime_raw();
        uint64_t gap = now_ns - last_poll_ns;
        if (gap > gap_max_ns) {
            gap_max_ns = gap;   // records preemption/poll-jitter worst case
        }
        last_poll_ns = now_ns;

        if ((prev & 1u) && !(cur & 1u)) {
            // 1 -> 0: heartbeat cleared the watchdog; start timing
            t_clear_ns = now_ns;
            t_clear_tk = now_tk;
            count_at_clear = cur >> 1;
            have_clear = 1;
            gap_max_ns = 0;
        } else if (have_clear && !(prev & 1u) && (cur & 1u)) {
            // 0 -> 1: trip observed
            uint64_t d_ns = now_ns - t_clear_ns;
            uint64_t d_tk = now_tk - t_clear_tk;
            uint32_t d_count = (cur >> 1) - count_at_clear;
            trip_ns[collected] = d_ns;
            trip_ticks[collected] = d_tk;
            printf("%d,%" PRIu64 ",%" PRIu64 ",%u,%" PRIu64 "\n",
                   collected, d_ns, d_tk, d_count, gap_max_ns);
            fflush(stdout);
            ++collected;
            have_clear = 0;
        }
        prev = cur;

        if (now_ns > deadline_ns) {
            break;
        }
    }

    if (collected == 0) {
        fprintf(stderr, "no clear->trip events observed in %d s (is the one-shot inference loop running?)\n",
                max_wall_s);
        return 3;
    }

    printf("collected=%d/%d\n", collected, n_events);
    print_stats("trip", "ns", trip_ns, collected);
    if (timebase_hz > 0) {
        print_stats("trip", "ticks", trip_ticks, collected);
        printf("expected: 250000 cycles @ 125 MHz = 2.000 ms = 2000000 ns = %u ticks\n",
               (uint32_t)((uint64_t)timebase_hz * 2000000ull / 1000000000ull));
    }

    munmap((void *)base, PAGE);
    return (collected == n_events) ? 0 : 3;
}
