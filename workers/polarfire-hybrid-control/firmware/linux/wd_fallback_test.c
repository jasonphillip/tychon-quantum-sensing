// Watchdog fallback stimulus on the idfix2 slot-3 page. Never touch 0x60001000.
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#ifndef WD_NO_VBX
#include "vbx_cnn_api.h"
#endif
#include "wd_trip_start.h"

#define PAGE 0x1000UL
#define SLOT3_PAGE 0x60040000UL
#define R_ACC_START 0x60040008UL
#define R_KP 0x6004000CUL
#define R_KI 0x60040010UL
#define R_KD 0x60040014UL
#define R_OUT_MIN 0x60040018UL
#define R_OUT_MAX 0x6004001CUL
#define R_INNER_CLAMP 0x60040020UL
#define R_AXI_WRITE_COUNT 0x60040800UL
#define R_CSR_VERSION 0x60040804UL
#define R_ERROR_LOW 0x60040810UL
#define R_ERROR_HIGH 0x60040814UL
#define R_U_AI 0x60040818UL
#define R_POST_CLAMP 0x60040844UL
#define R_WATCHDOG 0x60040854UL
#define MAX_POLL_ITERS 10000000

static volatile sig_atomic_t running = 1;
static void stop(int sig) { (void)sig; running = 0; }
static uint64_t nsec_now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
static uint64_t rdtime_raw(void)
{
#ifdef __riscv
    uint64_t v;
    __asm__ volatile("rdtime %0" : "=r"(v));
    return v;
#else
    return 0; // Host syntax check only.
#endif
}
static uint32_t q16(double v) { return (uint32_t)(int32_t)llround(v * 65536.0); }
static void q34_30(double v, uint32_t *lo, uint32_t *hi)
{
    int64_t raw = (int64_t)llround(v * (double)(1LL << 30));
    *lo = (uint32_t)raw; *hi = (uint32_t)((uint64_t)raw >> 32);
}
static volatile uint32_t *map_slot3(void)
{
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("open /dev/mem"); return NULL; }
    volatile uint32_t *p = mmap(NULL, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)SLOT3_PAGE);
    close(fd);
    if (p == MAP_FAILED) { perror("mmap slot3"); return NULL; }
    return p;
}
static volatile uint32_t *regp(volatile uint32_t *base, unsigned long addr)
{ return base + ((addr - SLOT3_PAGE) / 4); }
static void wr(volatile uint32_t *base, unsigned long addr, uint32_t value)
{ *regp(base, addr) = value; __sync_synchronize(); }
static uint32_t rd(volatile uint32_t *base, unsigned long addr)
{ uint32_t value = *regp(base, addr); __sync_synchronize(); return value; }
static void wait_until(uint64_t deadline)
{ while (running && nsec_now() < deadline) { } }
static int number(const char *s, double *out)
{
    char *end;
    errno = 0;
    *out = strtod(s, &end);
    return s != end && !*end && !errno && isfinite(*out);
}
static int integer(const char *s, uint64_t *out)
{
    char *end;
    errno = 0;
    *out = strtoull(s, &end, 10);
    return s != end && !*end && !errno && *s != '-';
}

typedef struct {
    volatile uint32_t *pid;
    wd_trip_start_state *trip;
    uint64_t idx;
    int64_t error_q34_30;
    uint32_t u_ai_q16;
    double error;
    double ai;
    uint64_t *emitted;
    uint64_t *timeouts;
    uint64_t *edge_idx;
    uint64_t *trips_started;
    uint64_t skip_at;
    int resume_mode;
} trip_context_t;

static void check_trip_start(trip_context_t *ctx)
{
    if (!ctx || !wd_trip_start(ctx->pid, ctx->trip, ctx->error_q34_30, ctx->u_ai_q16))
        return;
    uint32_t post = rd(ctx->pid, R_POST_CLAMP), wd = rd(ctx->pid, R_WATCHDOG);
    uint32_t writes = rd(ctx->pid, R_AXI_WRITE_COUNT);
    uint64_t ticks = rdtime_raw(), t_ns = nsec_now();
    printf("%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%.9f,%.9f,%" PRId32 ",%.9f,0x%08x,%u,%u,%u,forced,0,1\n",
           ctx->idx, ticks, t_ns, ctx->error, ctx->ai, (int32_t)post,
           (double)(int32_t)post / 65536.0, wd, wd & 1u, wd >> 1, writes);
    fflush(stdout);
    ++*ctx->emitted;
    if (wd & 1u) {
        ++*ctx->timeouts;
        if (ctx->resume_mode && *ctx->edge_idx == UINT64_MAX && ctx->idx >= ctx->skip_at) {
            *ctx->edge_idx = ctx->idx;
            ++*ctx->trips_started;
        }
    }
}

#ifdef WD_NO_VBX
// Syntax-only host stub: never performs an inference or hardware access.
static int inference_init(const char *path) { (void)path; return -1; }
static int inference_run(trip_context_t *ctx) { (void)ctx; return -1; }
#else
static vbx_cnn_t *vbx;
static model_t *model;
static vbx_cnn_io_ptr_t io[MAX_IO_BUFFERS];
static int inference_init(const char *path)
{
    vbx = vbx_cnn_init(NULL);
    if (!vbx || !vbx->initialized) return -1;
    FILE *f = fopen(path, "rb");
    if (!f) { perror("model"); return -1; }
    if (fseek(f, 0, SEEK_END)) { fclose(f); return -1; }
    long size = ftell(f);
    if (size <= 0 || fseek(f, 0, SEEK_SET)) { fclose(f); return -1; }
    model_t *host = malloc((size_t)size);
    if (!host) { fclose(f); return -1; }
    if (fread(host, 1, (size_t)size, f) != (size_t)size) { free(host); fclose(f); return -1; }
    fclose(f);
    size_t alloc = model_get_allocate_bytes(host);
    model = vbx_allocate_dma_buffer(vbx, alloc, 0);
    if (!model) { free(host); return -1; }
    memcpy(model, host, model_get_data_bytes(host));
    free(host);
    size_t nin = model_get_num_inputs(model), nout = model_get_num_outputs(model);
    if (nin != 1 || nout < 1 || nin + nout > MAX_IO_BUFFERS) return -1;
    for (size_t i = 0; i < nin; ++i) {
        vbx_cnn_calc_type_e type = model_get_input_datatype(model, (int)i);
        size_t bytes = type == VBX_CNN_CALC_TYPE_INT16 ? 2 : type == VBX_CNN_CALC_TYPE_INT32 ? 4 : 1;
        size_t length = model_get_input_length(model, (int)i) * bytes;
        void *p = vbx_allocate_dma_buffer(vbx, length, 0);
        if (!p) return -1;
        memcpy(p, model_get_test_input(model, (int)i), length);
        io[i] = (vbx_cnn_io_ptr_t)(uintptr_t)p;
    }
    for (size_t i = 0; i < nout; ++i) {
        size_t length = model_get_output_length(model, (int)i) * sizeof(uint32_t);
        void *p = vbx_allocate_dma_buffer(vbx, length, 0);
        if (!p) return -1;
        memset(p, 0, length);
        io[nin + i] = (vbx_cnn_io_ptr_t)(uintptr_t)p;
    }
    return 0;
}
static int inference_run(trip_context_t *ctx)
{
    int status = vbx_cnn_model_start(vbx, model, io);
    if (status) return -1;
    int polls = 0;
    for (;;) {
        check_trip_start(ctx);
        status = vbx_cnn_model_poll(vbx);
        if (status <= 0) break;
        if (!running || ++polls > MAX_POLL_ITERS) return -1;
    }
    return status < 0 || vbx_cnn_get_error_val(vbx) ? -1 : 0;
}
#endif

static void usage(const char *name)
{
    fprintf(stderr, "usage: %s normal | skip-inference-after N | resume-after N M | gap-then-inference D_us [START_AT_us] [options]\n"
            "options: --model PATH --updates TOTAL --period-us P --gap-after N --repeat-trips N --kp X --ki X --kd X --out-min X --out-max X --inner-clamp X --error X --ai-amp X --ai-step X --trip-start --zero-and-exit\n", name);
}
int main(int argc, char **argv)
{
    enum { NORMAL, SKIP, RESUME, GAP } mode = NORMAL;
    uint64_t n = 5000, period_us = 300, skip_at = 3333, resume_after = 200;
    uint64_t gap_us = 2500, start_at_us = 0, gap_after = 3333, repeat_trips = 1;
    double kp = .8, ki = 0, kd = 0, out_min = -1, out_max = 1, clamp = .045;
    double error = .20, amp = .08, step = .0005;
    const char *model_path = "fcnn_v2_residual_dataset_a.vnnx";
    int zero = 0, trip_enabled = 0, positional = 0;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i];
        if (!strcmp(a, "--zero-and-exit")) { zero = 1; continue; }
        if (!strcmp(a, "--trip-start")) { trip_enabled = 1; continue; }
        if (a[0] == '-' && a[1] == '-') {
            if (i + 1 == argc) { usage(argv[0]); return 2; }
            const char *v = argv[++i];
            int ok = 1;
            if (!strcmp(a, "--model")) model_path = v;
            else if (!strcmp(a, "--updates")) ok = integer(v, &n);
            else if (!strcmp(a, "--period-us")) ok = integer(v, &period_us);
            else if (!strcmp(a, "--gap-after")) ok = integer(v, &gap_after);
            else if (!strcmp(a, "--repeat-trips")) ok = integer(v, &repeat_trips);
            else if (!strcmp(a, "--kp")) ok = number(v, &kp);
            else if (!strcmp(a, "--ki")) ok = number(v, &ki);
            else if (!strcmp(a, "--kd")) ok = number(v, &kd);
            else if (!strcmp(a, "--out-min")) ok = number(v, &out_min);
            else if (!strcmp(a, "--out-max")) ok = number(v, &out_max);
            else if (!strcmp(a, "--inner-clamp")) ok = number(v, &clamp);
            else if (!strcmp(a, "--error")) ok = number(v, &error);
            else if (!strcmp(a, "--ai-amp")) ok = number(v, &amp);
            else if (!strcmp(a, "--ai-step")) ok = number(v, &step);
            else ok = 0;
            if (!ok) { usage(argv[0]); return 2; }
        } else if (positional++ == 0) {
            if (!strcmp(a, "normal")) mode = NORMAL;
            else if (!strcmp(a, "skip-inference-after")) mode = SKIP;
            else if (!strcmp(a, "resume-after")) mode = RESUME;
            else if (!strcmp(a, "gap-then-inference")) mode = GAP;
            else { usage(argv[0]); return 2; }
        } else {
            uint64_t value;
            if (!integer(a, &value)) { usage(argv[0]); return 2; }
            if (mode == SKIP && positional == 2) skip_at = value;
            else if (mode == RESUME && positional == 2) skip_at = value;
            else if (mode == RESUME && positional == 3) resume_after = value;
            else if (mode == GAP && positional == 2) gap_us = value;
            else if (mode == GAP && positional == 3) start_at_us = value;
            else { usage(argv[0]); return 2; }
        }
    }
    if (!zero && (positional < 1 || (mode == SKIP && positional != 2) ||
                  (mode == RESUME && positional != 3) || (mode == GAP && positional < 2))) {
        usage(argv[0]); return 2;
    }
    if (n == 0 || period_us == 0 || period_us > 1000000 || gap_us > 1000000 || repeat_trips < 1 || repeat_trips > 10 ||
        (repeat_trips > 1 && mode != RESUME) ||
        (start_at_us && (mode != GAP || start_at_us >= gap_us)) ||
        out_min > out_max || amp <= 0 || step <= 0 || step > amp * 2 ||
        fabs(kp) > 32767 || fabs(ki) > 32767 || fabs(kd) > 32767 ||
        fabs(out_min) > 32767 || fabs(out_max) > 32767 || amp > 32767 || clamp < 0 || clamp > 32767 ||
        fabs(error) >= 8) { usage(argv[0]); return 2; }
    volatile uint32_t *pid = map_slot3();
    if (!pid) return 1;
    uint32_t version = rd(pid, R_CSR_VERSION);
    if (version != 0x00010000u) { fprintf(stderr, "unexpected csr_version=0x%08x\n", version); munmap((void *)pid, PAGE); return 1; }
    if (zero) {
        wr(pid, R_OUT_MIN, 0); wr(pid, R_OUT_MAX, 0); wr(pid, R_ACC_START, 1);
        uint32_t value = rd(pid, R_POST_CLAMP);
        printf("post_clamp_q16=%" PRId32 " post_clamp_f=%.9f\n", (int32_t)value, (double)(int32_t)value / 65536.0);
        munmap((void *)pid, PAGE);
        return value ? 1 : 0;
    }
    signal(SIGINT, stop); signal(SIGTERM, stop);
    wr(pid, R_OUT_MIN, q16(out_min)); wr(pid, R_OUT_MAX, q16(out_max));
    wr(pid, R_KP, q16(kp)); wr(pid, R_KI, q16(ki)); wr(pid, R_KD, q16(kd));
    wr(pid, R_INNER_CLAMP, q16(clamp));
    if (inference_init(model_path)) { fprintf(stderr, "VBX model initialization failed\n"); munmap((void *)pid, PAGE); return 1; }
    puts("idx,rdtime_ticks,t_ns,error,u_ai,post_clamp_q16,post_clamp_f,wd_raw,wd_timeout_bit,wd_trip_count,axi_write_count,mode_phase,overrun_ns,forced_start");
    uint32_t error_lo, error_hi;
    q34_30(error, &error_lo, &error_hi);
    printf("# mode=%s skip_at=%" PRIu64 " resume_after=%" PRIu64 " gap_us=%" PRIu64 " start_at_us=%" PRIu64 " gap_after=%" PRIu64 " repeat_trips=%" PRIu64 " updates=%" PRIu64 " period_us=%" PRIu64 " model=%s error=%.9f(0x60040810=0x%08x,0x60040814=0x%08x) ai_amp=%.9f ai_step=%.9f first_u_ai=0x%08x kp=%.9f(0x6004000c=0x%08x) ki=%.9f(0x60040010=0x%08x) kd=%.9f(0x60040014=0x%08x) out_min=%.9f(0x60040018=0x%08x) out_max=%.9f(0x6004001c=0x%08x) inner_clamp=%.9f(0x60040020=0x%08x) csr_version=0x%08x\n",
           mode == NORMAL ? "normal" : mode == SKIP ? "skip" : mode == RESUME ? "resume" : "gap",
           skip_at, resume_after, gap_us, start_at_us, gap_after, repeat_trips, n, period_us, model_path,
           error, error_lo, error_hi, amp, step, q16(-amp), kp, q16(kp), ki, q16(ki), kd, q16(kd), out_min, q16(out_min),
           out_max, q16(out_max), clamp, q16(clamp), version);
    fflush(stdout);
    uint64_t deadline = nsec_now(), overruns = 0, max_overrun = 0, timeouts = 0, emitted = 0;
    uint64_t edge_idx = UINT64_MAX, last_completion = 0, trips_started = 0;
    wd_trip_start_state trip = WD_TRIP_START_INIT;
    int gap_done = 0, direction = 1, rc = 0;
    double ai = -amp;
    for (uint64_t idx = 0; running && idx < n; ++idx) {
        if (mode == RESUME && trips_started < repeat_trips && edge_idx != UINT64_MAX &&
            idx >= edge_idx + 1012) { skip_at = idx; edge_idx = UINT64_MAX; }
        int gap_row = 0;
        if (mode == GAP && !gap_done && idx == gap_after && last_completion) {
            if (start_at_us) {
                uint64_t extra_deadline = last_completion + start_at_us * 1000;
                wait_until(extra_deadline);
                if (!running) break;
                uint64_t extra_now = nsec_now();
                uint64_t extra_overrun = extra_now > extra_deadline ? extra_now - extra_deadline : 0;
                if (extra_overrun) { ++overruns; if (extra_overrun > max_overrun) max_overrun = extra_overrun; }
                uint32_t lo, hi;
                q34_30(error, &lo, &hi);
                wr(pid, R_ERROR_LOW, lo); wr(pid, R_ERROR_HIGH, hi); wr(pid, R_U_AI, q16(ai));
                wr(pid, R_ACC_START, 1);
                uint32_t post = rd(pid, R_POST_CLAMP), wd = rd(pid, R_WATCHDOG);
                uint32_t writes = rd(pid, R_AXI_WRITE_COUNT);
                printf("%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%.9f,%.9f,%" PRId32 ",%.9f,0x%08x,%u,%u,%u,gap,%" PRIu64 ",0\n",
                       idx, rdtime_raw(), nsec_now(), error, ai, (int32_t)post,
                       (double)(int32_t)post / 65536.0, wd, wd & 1u, wd >> 1, writes, extra_overrun);
                fflush(stdout);
                ++emitted;
                if (wd & 1u) ++timeouts;
                ai += direction * step;
                if (ai >= amp) { ai = amp; direction = -1; }
                else if (ai <= -amp) { ai = -amp; direction = 1; }
                ++idx;
            }
            deadline = last_completion + gap_us * 1000;
            wait_until(deadline);
            if (!running) break;
            gap_done = 1; gap_row = !start_at_us;
        }
        wait_until(deadline);
        if (!running) break;
        uint64_t now = nsec_now();
        uint64_t overrun = now > deadline ? now - deadline : 0;
        if (overrun) { ++overruns; if (overrun > max_overrun) max_overrun = overrun; }
        uint32_t lo, hi;
        q34_30(error, &lo, &hi);
        wr(pid, R_ERROR_LOW, lo); wr(pid, R_ERROR_HIGH, hi); wr(pid, R_U_AI, q16(ai));
        int infer = mode == NORMAL || mode == GAP || idx < skip_at ||
                    (mode == RESUME && edge_idx != UINT64_MAX && idx > edge_idx + resume_after);
        const char *phase = gap_row ? "gap" : (mode == GAP && gap_done) ? "resume" :
                            !infer ? "skip" : (mode == RESUME && edge_idx != UINT64_MAX) ? "resume" : "normal";
        if (infer) {
            trip_context_t ctx = {pid, &trip, idx, (int64_t)(((uint64_t)hi << 32) | lo),
                                  q16(ai), error, ai, &emitted, &timeouts, &edge_idx,
                                  &trips_started, skip_at, mode == RESUME};
            if (trip_enabled) check_trip_start(&ctx);
            if (inference_run(trip_enabled ? &ctx : NULL)) {
                if (running) { fprintf(stderr, "inference failed at update %" PRIu64 "\n", idx); rc = 1; }
                break;
            }
            last_completion = nsec_now();
        }
        wr(pid, R_ACC_START, 1);
        uint32_t post = rd(pid, R_POST_CLAMP), wd = rd(pid, R_WATCHDOG);
        uint32_t writes = rd(pid, R_AXI_WRITE_COUNT);
        uint64_t ticks = rdtime_raw(), t_ns = nsec_now();
        if ((wd & 1u) && edge_idx == UINT64_MAX && mode == RESUME && idx >= skip_at) {
            edge_idx = idx; ++trips_started;
        }
        if (wd & 1u) ++timeouts;
        printf("%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%.9f,%.9f,%" PRId32 ",%.9f,0x%08x,%u,%u,%u,%s,%" PRIu64 ",0\n",
               idx, ticks, t_ns, error, ai, (int32_t)post, (double)(int32_t)post / 65536.0,
               wd, wd & 1u, wd >> 1, writes, phase, overrun);
        fflush(stdout);
        ++emitted;
        ai += direction * step;
        if (ai >= amp) { ai = amp; direction = -1; }
        else if (ai <= -amp) { ai = -amp; direction = 1; }
        deadline += period_us * 1000;
    }
    fprintf(stderr, "updates=%" PRIu64 " overruns=%" PRIu64 " max_overrun_ns=%" PRIu64 " timeouts_seen=%" PRIu64 "\n",
            emitted, overruns, max_overrun, timeouts);
    munmap((void *)pid, PAGE);
    return rc;
}
