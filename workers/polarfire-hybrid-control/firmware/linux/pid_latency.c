// pid_latency.c - idfix2 PID pulse/read latency probe.
//
// Bounded userspace timing helper for the two-slot PID page. It writes only the
// idfix2-safe M0 gain/limit/start registers and M1 error/u_ai registers, then
// reads M1 post_clamp_out. It never touches 0x60001000.

#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <setjmp.h>
#include <signal.h>
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

#define R_ACC_START       0x60040008UL
#define R_KP              0x6004000CUL
#define R_KI              0x60040010UL
#define R_KD              0x60040014UL
#define R_OUT_MIN         0x60040018UL
#define R_OUT_MAX         0x6004001CUL
#define R_AXI_WRITE_COUNT 0x60040800UL
#define R_CSR_VERSION     0x60040804UL
#define R_ERROR_LOW       0x60040810UL
#define R_ERROR_HIGH      0x60040814UL
#define R_U_AI            0x60040818UL
#define R_POST_CLAMP      0x60040844UL
#define R_WATCHDOG        0x60040854UL

static sigjmp_buf g_ill_jmp;
static volatile sig_atomic_t g_probe_csr = 0;

static void sigill_handler(int signo)
{
    (void)signo;
    if (g_probe_csr) {
        g_probe_csr = 0;
        siglongjmp(g_ill_jmp, 1);
    }
    signal(SIGILL, SIG_DFL);
    raise(SIGILL);
}

static inline uint64_t rdcycle_raw(void)
{
    uint64_t v;
#if defined(__riscv)
    __asm__ volatile("rdcycle %0" : "=r"(v));
#else
    v = 0;
#endif
    return v;
}

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

static int csr_available(uint64_t (*reader)(void))
{
#if !defined(__riscv)
    return 0;
#else
    struct sigaction sa;
    struct sigaction old_sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = sigill_handler;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGILL, &sa, &old_sa) != 0) {
        return 0;
    }
    if (sigsetjmp(g_ill_jmp, 1) == 0) {
        g_probe_csr = 1;
        (void)reader();
        g_probe_csr = 0;
        sigaction(SIGILL, &old_sa, NULL);
        return 1;
    }
    sigaction(SIGILL, &old_sa, NULL);
    return 0;
#endif
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

static uint32_t f_to_q16(double v)
{
    return (uint32_t)(int32_t)llround(v * 65536.0);
}

static double q16_to_f(uint32_t raw)
{
    return (double)(int32_t)raw / 65536.0;
}

static void f_to_q34_30(double v, uint32_t *lo, uint32_t *hi)
{
    int64_t raw = (int64_t)llround(v * (double)(1LL << 30));
    *lo = (uint32_t)(raw & 0xffffffffu);
    *hi = (uint32_t)((uint64_t)raw >> 32);
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

static inline void wr(volatile uint32_t *base, unsigned long addr, uint32_t val)
{
    *regp(base, addr) = val;
    __sync_synchronize();
}

static inline uint32_t rd(volatile uint32_t *base, unsigned long addr)
{
    uint32_t v = *regp(base, addr);
    __sync_synchronize();
    return v;
}

int main(int argc, char **argv)
{
    int samples = (argc > 1) ? atoi(argv[1]) : 5000;
    int warmup = (argc > 2) ? atoi(argv[2]) : 100;
    if (samples < 1 || samples > 200000 || warmup < 0 || warmup > 200000) {
        fprintf(stderr, "usage: %s [samples 1..200000] [warmup 0..200000]\n", argv[0]);
        return 2;
    }

    int have_rdcycle = csr_available(rdcycle_raw);
    int have_rdtime = csr_available(rdtime_raw);
    uint32_t timebase_hz = read_timebase_hz();
    printf("pid_latency samples=%d warmup=%d rdcycle=%d rdtime=%d timebase_hz=%" PRIu32 "\n",
           samples, warmup, have_rdcycle, have_rdtime, timebase_hz);

    volatile uint32_t *base = map_slot3();
    if (!base) {
        return 1;
    }

    uint32_t csr_version = rd(base, R_CSR_VERSION);
    printf("csr_version=0x%08x watchdog_raw=0x%08x\n", csr_version, rd(base, R_WATCHDOG));
    if (csr_version != 0x00010000u) {
        fprintf(stderr, "unexpected csr_version\n");
        return 1;
    }

    wr(base, R_OUT_MIN, f_to_q16(-1.0));
    wr(base, R_OUT_MAX, f_to_q16(1.0));
    wr(base, R_KP, f_to_q16(0.8));
    wr(base, R_KI, f_to_q16(0.0));
    wr(base, R_KD, f_to_q16(0.0));
    wr(base, R_U_AI, f_to_q16(0.0));
    uint32_t lo, hi;
    f_to_q34_30(0.25, &lo, &hi);
    wr(base, R_ERROR_LOW, lo);
    wr(base, R_ERROR_HIGH, hi);

    uint64_t *pulse_ns = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *sample_ns = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *pulse_cycles = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *sample_cycles = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *pulse_ticks = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *sample_ticks = calloc((size_t)samples, sizeof(uint64_t));
    if (!pulse_ns || !sample_ns || !pulse_cycles || !sample_cycles || !pulse_ticks || !sample_ticks) {
        fprintf(stderr, "calloc failed\n");
        return 1;
    }

    uint32_t sink = 0;
    int stored = 0;
    for (int i = 0; i < warmup + samples; ++i) {
        uint64_t c0 = have_rdcycle ? rdcycle_raw() : 0;
        uint64_t t0 = have_rdtime ? rdtime_raw() : 0;
        uint64_t n0 = nsec_now();
        wr(base, R_ACC_START, 1);
        sink ^= rd(base, R_POST_CLAMP);
        uint64_t c1 = have_rdcycle ? rdcycle_raw() : 0;
        uint64_t t1 = have_rdtime ? rdtime_raw() : 0;
        uint64_t n1 = nsec_now();

        double err = 0.20 + 0.001 * (double)(i % 97);
        f_to_q34_30(err, &lo, &hi);
        uint64_t c2 = have_rdcycle ? rdcycle_raw() : 0;
        uint64_t t2 = have_rdtime ? rdtime_raw() : 0;
        uint64_t n2 = nsec_now();
        wr(base, R_ERROR_LOW, lo);
        wr(base, R_ERROR_HIGH, hi);
        wr(base, R_U_AI, f_to_q16(0.0));
        wr(base, R_ACC_START, 1);
        sink ^= rd(base, R_POST_CLAMP);
        sink ^= rd(base, R_AXI_WRITE_COUNT);
        uint64_t c3 = have_rdcycle ? rdcycle_raw() : 0;
        uint64_t t3 = have_rdtime ? rdtime_raw() : 0;
        uint64_t n3 = nsec_now();

        if (i >= warmup) {
            pulse_ns[stored] = n1 - n0;
            sample_ns[stored] = n3 - n2;
            if (have_rdcycle) {
                pulse_cycles[stored] = c1 - c0;
                sample_cycles[stored] = c3 - c2;
            }
            if (have_rdtime) {
                pulse_ticks[stored] = t1 - t0;
                sample_ticks[stored] = t3 - t2;
            }
            ++stored;
        }
    }

    uint32_t post = rd(base, R_POST_CLAMP);
    printf("post_clamp_raw=0x%08x post_clamp=%.6f axi_write_count=0x%08x sink=0x%08x\n",
           post, q16_to_f(post), rd(base, R_AXI_WRITE_COUNT), sink);
    print_stats("pulse_read", "ns", pulse_ns, stored);
    print_stats("sample", "ns", sample_ns, stored);
    if (have_rdcycle) {
        print_stats("pulse_read", "cycles", pulse_cycles, stored);
        print_stats("sample", "cycles", sample_cycles, stored);
    }
    if (have_rdtime) {
        print_stats("pulse_read", "ticks", pulse_ticks, stored);
        print_stats("sample", "ticks", sample_ticks, stored);
    }

    munmap((void *)base, PAGE);
    return 0;
}
