// vnnx_latency.c - CoreVectorBlox V250 start/poll latency probe.
//
// Measures the deployed .vnnx model on the Icicle Linux runtime after one-time
// model load and DMA allocation. Each sample times vbx_cnn_model_start() plus
// the busy-poll loop around vbx_cnn_model_poll(). It records U54 rdcycle counts
// and rdtime ticks when accessible from userspace, plus CLOCK_MONOTONIC_RAW
// nanoseconds.

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

#include "vbx_cnn_api.h"

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

static void print_stats_ns(const char *name, uint64_t *values, int n)
{
    qsort(values, (size_t)n, sizeof(values[0]), cmp_u64);
    printf("%s_ns min=%" PRIu64 " median=%" PRIu64 " p95=%" PRIu64 " p99=%" PRIu64 " max=%" PRIu64 "\n",
           name,
           values[0],
           percentile_u64(values, n, 0.50),
           percentile_u64(values, n, 0.95),
           percentile_u64(values, n, 0.99),
           values[n - 1]);
}

static void print_stats_cycles(const char *name, uint64_t *values, int n)
{
    qsort(values, (size_t)n, sizeof(values[0]), cmp_u64);
    printf("%s_cycles min=%" PRIu64 " median=%" PRIu64 " p95=%" PRIu64 " p99=%" PRIu64 " max=%" PRIu64 "\n",
           name,
           values[0],
           percentile_u64(values, n, 0.50),
           percentile_u64(values, n, 0.95),
           percentile_u64(values, n, 0.99),
           values[n - 1]);
}

static void print_stats_ticks(const char *name, uint64_t *values, int n)
{
    qsort(values, (size_t)n, sizeof(values[0]), cmp_u64);
    printf("%s_ticks min=%" PRIu64 " median=%" PRIu64 " p95=%" PRIu64 " p99=%" PRIu64 " max=%" PRIu64 "\n",
           name,
           values[0],
           percentile_u64(values, n, 0.50),
           percentile_u64(values, n, 0.95),
           percentile_u64(values, n, 0.99),
           values[n - 1]);
}

static model_t *read_model_file(vbx_cnn_t *vbx, const char *fn)
{
    FILE *f = fopen(fn, "rb");
    if (!f) {
        perror("fopen .vnnx");
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    long fsz = ftell(f);
    fseek(f, 0, SEEK_SET);
    model_t *m = (model_t *)malloc((size_t)fsz);
    if (!m || fread(m, 1, (size_t)fsz, f) != (size_t)fsz) {
        fclose(f);
        free(m);
        return NULL;
    }
    fclose(f);

    size_t alloc = model_get_allocate_bytes(m);
    void *dma = vbx_allocate_dma_buffer(vbx, alloc, 0);
    if (!dma) {
        free(m);
        return NULL;
    }
    memcpy(dma, m, model_get_data_bytes(m));
    free(m);
    return (model_t *)dma;
}

static double output0(vbx_cnn_io_ptr_t *io, size_t nin, const model_t *model)
{
    int scale_fix16 = model_get_output_scale_fix16_value(model, 0);
    int zp = model_get_output_zeropoint(model, 0);
    int8_t *out = (int8_t *)(uintptr_t)io[nin];
    return ((int)out[0] - zp) * (scale_fix16 / 65536.0);
}

int main(int argc, char **argv)
{
    const char *vnnx = (argc > 1) ? argv[1] : "fcnn_v2_residual_dataset_a.vnnx";
    int samples = (argc > 2) ? atoi(argv[2]) : 200;
    int warmup = (argc > 3) ? atoi(argv[3]) : 10;
    const int max_poll_iters = 10000000;

    if (samples < 1 || samples > 10000 || warmup < 0 || warmup > 10000) {
        fprintf(stderr, "usage: %s [model.vnnx] [samples 1..10000] [warmup 0..10000]\n", argv[0]);
        return 2;
    }

    int have_rdcycle = csr_available(rdcycle_raw);
    int have_rdtime = csr_available(rdtime_raw);
    uint32_t timebase_hz = read_timebase_hz();
    printf("vnnx_latency model=%s samples=%d warmup=%d rdcycle=%d rdtime=%d timebase_hz=%" PRIu32 "\n",
           vnnx, samples, warmup, have_rdcycle, have_rdtime, timebase_hz);

    vbx_cnn_t *vbx = vbx_cnn_init(NULL);
    if (!vbx || !vbx->initialized) {
        fprintf(stderr, "vbx_cnn_init failed\n");
        return 1;
    }

    model_t *model = read_model_file(vbx, vnnx);
    if (!model) {
        fprintf(stderr, "read_model_file(%s) failed\n", vnnx);
        return 1;
    }

    size_t nin = model_get_num_inputs(model);
    size_t nout = model_get_num_outputs(model);
    printf("model_io inputs=%zu outputs=%zu sanity=%d config=%d\n",
           nin, nout, model_check_sanity(model), (int)model_get_size_conf(model));

    vbx_cnn_io_ptr_t io[MAX_IO_BUFFERS];
    for (size_t i = 0; i < nin; ++i) {
        io[i] = (vbx_cnn_io_ptr_t)(uintptr_t)model_get_test_input(model, (int)i);
    }
    for (size_t o = 0; o < nout; ++o) {
        size_t n = model_get_output_length(model, (int)o);
        void *ob = vbx_allocate_dma_buffer(vbx, n * sizeof(uint32_t), 0);
        if (!ob) {
            fprintf(stderr, "alloc output %zu failed\n", o);
            return 1;
        }
        memset(ob, 0, n * sizeof(uint32_t));
        io[nin + o] = (vbx_cnn_io_ptr_t)(uintptr_t)ob;
    }

    uint64_t *total_ns = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *start_ns = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *poll_ns = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *total_cycles = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *start_cycles = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *poll_cycles = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *total_ticks = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *start_ticks = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *poll_ticks = calloc((size_t)samples, sizeof(uint64_t));
    uint64_t *poll_iters = calloc((size_t)samples, sizeof(uint64_t));
    if (!total_ns || !start_ns || !poll_ns || !total_cycles || !start_cycles || !poll_cycles ||
        !total_ticks || !start_ticks || !poll_ticks || !poll_iters) {
        fprintf(stderr, "calloc failed\n");
        return 1;
    }

    int stored = 0;
    for (int iter = 0; iter < warmup + samples; ++iter) {
        uint64_t c0 = have_rdcycle ? rdcycle_raw() : 0;
        uint64_t t0 = have_rdtime ? rdtime_raw() : 0;
        uint64_t n0 = nsec_now();
        int status = vbx_cnn_model_start(vbx, model, io);
        uint64_t c1 = have_rdcycle ? rdcycle_raw() : 0;
        uint64_t t1 = have_rdtime ? rdtime_raw() : 0;
        uint64_t n1 = nsec_now();
        if (status != 0) {
            fprintf(stderr, "model_start ret=%d err=%d iter=%d\n", status, (int)vbx_cnn_get_error_val(vbx), iter);
            return 1;
        }

        int p = 1;
        int polls = 0;
        while ((p = vbx_cnn_model_poll(vbx)) > 0) {
            ++polls;
            if (polls > max_poll_iters) {
                fprintf(stderr, "poll timeout iter=%d err=%d\n", iter, (int)vbx_cnn_get_error_val(vbx));
                return 1;
            }
        }
        uint64_t c2 = have_rdcycle ? rdcycle_raw() : 0;
        uint64_t t2 = have_rdtime ? rdtime_raw() : 0;
        uint64_t n2 = nsec_now();
        if (p < 0 || vbx_cnn_get_error_val(vbx)) {
            fprintf(stderr, "poll ret=%d err=%d iter=%d\n", p, (int)vbx_cnn_get_error_val(vbx), iter);
            return 1;
        }

        if (iter >= warmup) {
            start_ns[stored] = n1 - n0;
            poll_ns[stored] = n2 - n1;
            total_ns[stored] = n2 - n0;
            if (have_rdcycle) {
                start_cycles[stored] = c1 - c0;
                poll_cycles[stored] = c2 - c1;
                total_cycles[stored] = c2 - c0;
            }
            if (have_rdtime) {
                start_ticks[stored] = t1 - t0;
                poll_ticks[stored] = t2 - t1;
                total_ticks[stored] = t2 - t0;
            }
            poll_iters[stored] = (uint64_t)polls;
            ++stored;
        }
    }

    printf("error_val=%d out0=%.6f\n", (int)vbx_cnn_get_error_val(vbx), output0(io, nin, model));
    print_stats_ns("start", start_ns, stored);
    print_stats_ns("poll", poll_ns, stored);
    print_stats_ns("total", total_ns, stored);
    if (have_rdcycle) {
        print_stats_cycles("start", start_cycles, stored);
        print_stats_cycles("poll", poll_cycles, stored);
        print_stats_cycles("total", total_cycles, stored);
    }
    if (have_rdtime) {
        print_stats_ticks("start", start_ticks, stored);
        print_stats_ticks("poll", poll_ticks, stored);
        print_stats_ticks("total", total_ticks, stored);
    }
    print_stats_ticks("poll_iters", poll_iters, stored);

    return 0;
}
