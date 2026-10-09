// v250_pid_loop.c - on-kit V250 -> PID userspace loop for idfix2.
//
// Runs the deployed .vnnx model on the CoreVectorBlox V250, dequantizes out[0],
// scales it into the PID u_ai CSR, pulses the SmartHLS PID core, then reads the
// live M1 post_clamp actuator tap. This is the first step that makes the Icicle
// Linux process the loop driver instead of the dashboard/backend.
//
// Safety boundary:
//   - maps only the idfix2 SLAVE3 page at 0x60040000
//   - writes only M0 limits/gains/inner-clamp/start and M1 error/u_ai
//   - reads actuator/watchdog/status only from M1 pid_csr
//   - never touches the stale 0x60001000 address
//
// Input source: optional CSV rows of normalized ODMR spectrum + PID-anchor
// channel. If no CSV is provided, the model's embedded test input is copied
// into the DMA input buffer for backwards-compatible smoke testing.
//
// Build on bee:
//   make CROSS=riscv64-unknown-linux-gnu- VBX_SDK=/c/Microchip/VectorBlox-SDK v250_pid_loop
//
// Run on target:
//   ./v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 50 2 /root/bringup/odmr_v250_rows.csv
//   ./v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 120 2 /root/bringup/odmr_v250_rows.csv --daemon --state /tmp/v250_pid_loop_state.json

#define _GNU_SOURCE

#include <errno.h>
#include <ctype.h>
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

#include "vbx_cnn_api.h"
#include "wd_trip_start.h"

#define PAGE       0x1000UL
#define SLOT3_PAGE 0x60040000UL

#define R_ACC_START       0x60040008UL
#define R_KP              0x6004000CUL
#define R_KI              0x60040010UL
#define R_KD              0x60040014UL
#define R_OUT_MIN         0x60040018UL
#define R_OUT_MAX         0x6004001CUL
#define R_INNER_CLAMP     0x60040020UL
#define R_AXI_WRITE_COUNT 0x60040800UL
#define R_CSR_VERSION     0x60040804UL
#define R_ERROR_LOW       0x60040810UL
#define R_ERROR_HIGH      0x60040814UL
#define R_U_AI            0x60040818UL
#define R_POST_CLAMP      0x60040844UL
#define R_WATCHDOG        0x60040854UL

#define CSR_VERSION_EXPECT 0x00010000U
#define DEFAULT_U_SCALE    (1.0 / 64.0)
#define MAX_POLL_ITERS     10000000
#define MAX_CSV_LINE       16384
#define DEFAULT_STATE_PATH "/tmp/v250_pid_loop_state.json"

typedef struct {
    double *error;
    double *flat;
    size_t rows;
    size_t input_len;
} row_set_t;

typedef struct {
    uint8_t *buf;
    size_t input_len;
    size_t bytes;
    vbx_cnn_calc_type_e dtype;
    double scale;
    int zero_point;
} input0_t;

static volatile sig_atomic_t keep_running = 1;

static void on_signal(int sig)
{
    (void)sig;
    keep_running = 0;
}

static uint64_t nsec_now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static uint32_t f_to_q16(double v)
{
    return (uint32_t)(int32_t)llround(v * 65536.0);
}

static double q16_to_f(uint32_t raw)
{
    return (double)(int32_t)raw / 65536.0;
}

static int parse_double_full(const char *s, double *out)
{
    char *end = NULL;
    errno = 0;
    double v = strtod(s, &end);
    if (s == end || errno == ERANGE) {
        return 0;
    }
    while (end && isspace((unsigned char)*end)) {
        ++end;
    }
    if (end && *end != '\0') {
        return 0;
    }
    *out = v;
    return 1;
}

static int write_pid_file(const char *path)
{
    if (!path) {
        return 0;
    }
    FILE *f = fopen(path, "w");
    if (!f) {
        perror("fopen pid file");
        return -1;
    }
    fprintf(f, "%ld\n", (long)getpid());
    fclose(f);
    return 0;
}

static int write_state_json(const char *path, int running, uint64_t row, uint64_t t_ns,
                            uint64_t v250_ns, int polls, size_t input_row, double error,
                            double nn_out, int nn_q, double u_ai, double post_clamp,
                            uint32_t watchdog_raw, uint32_t axi_write_count, uint64_t forced_starts,
                            const char *input_source)
{
    if (!path) {
        return 0;
    }

    char tmp[512];
    snprintf(tmp, sizeof(tmp), "%s.tmp.%ld", path, (long)getpid());
    FILE *f = fopen(tmp, "w");
    if (!f) {
        return -1;
    }

    fprintf(f,
            "{\"running\":%s,\"pid\":%ld,\"row\":%" PRIu64
            ",\"t_ns\":%" PRIu64 ",\"v250_ns\":%" PRIu64
            ",\"polls\":%d,\"input_row\":%zu,\"error_in\":%.9f"
            ",\"nn_out0\":%.9f,\"nn_q\":%d,\"u_ai\":%.9f"
            ",\"post_clamp\":%.9f,\"watchdog_raw\":\"0x%08x\""
            ",\"watchdog_timeout\":%u,\"axi_write_count\":\"0x%08x\""
            ",\"forced_starts\":%" PRIu64
            ",\"input_source\":\"%s\",\"updated_ns\":%" PRIu64 "}\n",
            running ? "true" : "false", (long)getpid(), row, t_ns, v250_ns,
            polls, input_row, error, nn_out, nn_q, u_ai, post_clamp,
            watchdog_raw, watchdog_raw & 0x1u, axi_write_count, forced_starts,
            input_source ? input_source : "embedded_test_vector", nsec_now());
    if (fclose(f) != 0) {
        unlink(tmp);
        return -1;
    }
    if (rename(tmp, path) != 0) {
        unlink(tmp);
        return -1;
    }
    return 0;
}

static void f_to_q34_30(double v, uint32_t *lo, uint32_t *hi)
{
    int64_t raw = (int64_t)llround(v * (double)(1LL << 30));
    *lo = (uint32_t)(raw & 0xffffffffu);
    *hi = (uint32_t)((uint64_t)raw >> 32);
}

static void check_trip_start(volatile uint32_t *pid, wd_trip_start_state *trip,
                             int64_t error_q34_30, uint32_t last_u_ai,
                             uint64_t row, uint64_t t0)
{
    if (wd_trip_start(pid, trip, error_q34_30, last_u_ai)) {
        fprintf(stderr, "forced_start row=%" PRIu64 " t_ns=%" PRIu64 " watchdog_raw=0x%08x\n",
                row, nsec_now() - t0, trip->last_watchdog_raw);
    }
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
    if (fsz <= 0) {
        fclose(f);
        return NULL;
    }

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

static double output0(vbx_cnn_io_ptr_t *io, size_t nin, const model_t *model, int *q_out)
{
    int scale_fix16 = model_get_output_scale_fix16_value(model, 0);
    int zp = model_get_output_zeropoint(model, 0);
    int8_t *out = (int8_t *)(uintptr_t)io[nin];
    int q = (int)out[0];
    if (q_out) {
        *q_out = q;
    }
    return (q - zp) * (scale_fix16 / 65536.0);
}

static size_t dtype_bytes(vbx_cnn_calc_type_e dtype)
{
    switch (dtype) {
    case VBX_CNN_CALC_TYPE_UINT8:
    case VBX_CNN_CALC_TYPE_INT8:
        return 1;
    case VBX_CNN_CALC_TYPE_INT16:
        return 2;
    case VBX_CNN_CALC_TYPE_INT32:
        return 4;
    default:
        return 0;
    }
}

static int quantize_value(double x, double scale, int zero_point)
{
    if (scale <= 0.0) {
        return zero_point;
    }
    return (int)llround(x / scale + (double)zero_point);
}

static void quantize_flat_to_input(const double *flat, input0_t *in)
{
    size_t half = in->input_len / 2;
    for (size_t i = 0; i < half; ++i) {
        double vals[2] = {flat[i], flat[half + i]};
        for (size_t c = 0; c < 2; ++c) {
            size_t j = 2 * i + c;  // NHWC: spectrum_i, anchor_i
            int q = quantize_value(vals[c], in->scale, in->zero_point);
            switch (in->dtype) {
            case VBX_CNN_CALC_TYPE_UINT8:
                if (q < 0) q = 0;
                if (q > 255) q = 255;
                ((uint8_t *)in->buf)[j] = (uint8_t)q;
                break;
            case VBX_CNN_CALC_TYPE_INT8:
                if (q < -128) q = -128;
                if (q > 127) q = 127;
                ((int8_t *)in->buf)[j] = (int8_t)q;
                break;
            case VBX_CNN_CALC_TYPE_INT16:
                if (q < -32768) q = -32768;
                if (q > 32767) q = 32767;
                ((int16_t *)in->buf)[j] = (int16_t)q;
                break;
            case VBX_CNN_CALC_TYPE_INT32:
                ((int32_t *)in->buf)[j] = (int32_t)q;
                break;
            default:
                break;
            }
        }
    }
    __sync_synchronize();
}

static void free_rows(row_set_t *rows)
{
    free(rows->error);
    free(rows->flat);
    rows->error = NULL;
    rows->flat = NULL;
    rows->rows = 0;
    rows->input_len = 0;
}

static int append_row(row_set_t *rows, const double *vals, size_t nvals)
{
    double *new_error = (double *)realloc(rows->error, (rows->rows + 1) * sizeof(double));
    if (!new_error) {
        return -1;
    }
    rows->error = new_error;
    double *new_flat = (double *)realloc(rows->flat, (rows->rows + 1) * rows->input_len * sizeof(double));
    if (!new_flat) {
        return -1;
    }
    rows->flat = new_flat;
    rows->error[rows->rows] = vals[0];
    memcpy(&rows->flat[rows->rows * rows->input_len], &vals[1], rows->input_len * sizeof(double));
    ++rows->rows;
    (void)nvals;
    return 0;
}

static int load_rows_csv(const char *path, size_t input_len, row_set_t *rows)
{
    FILE *f = fopen(path, "r");
    if (!f) {
        perror("fopen input csv");
        return -1;
    }

    memset(rows, 0, sizeof(*rows));
    rows->input_len = input_len;

    char line[MAX_CSV_LINE];
    double *vals = (double *)malloc((input_len + 1) * sizeof(double));
    if (!vals) {
        fclose(f);
        return -1;
    }

    while (fgets(line, sizeof(line), f)) {
        char *p = line;
        while (isspace((unsigned char)*p)) {
            ++p;
        }
        if (*p == '\0' || *p == '#' || isalpha((unsigned char)*p)) {
            continue;
        }

        size_t n = 0;
        while (*p && n < input_len + 1) {
            char *end = NULL;
            vals[n] = strtod(p, &end);
            if (p == end) {
                break;
            }
            ++n;
            p = end;
            while (*p && *p != ',') {
                ++p;
            }
            if (*p == ',') {
                ++p;
            }
        }

        if (n < input_len + 1) {
            fprintf(stderr, "bad input csv row %zu: expected at least %zu numeric fields, got %zu\n",
                    rows->rows, input_len + 1, n);
            free(vals);
            fclose(f);
            free_rows(rows);
            return -1;
        }
        if (append_row(rows, vals, n) != 0) {
            free(vals);
            fclose(f);
            free_rows(rows);
            return -1;
        }
    }

    free(vals);
    fclose(f);
    if (rows->rows == 0) {
        fprintf(stderr, "input csv has no data rows: %s\n", path);
        return -1;
    }
    return 0;
}

static int run_v250(vbx_cnn_t *vbx, model_t *model, vbx_cnn_io_ptr_t *io, int *polls_out,
                    volatile uint32_t *pid, wd_trip_start_state *trip, int trip_enabled,
                    int64_t error_q34_30, uint32_t last_u_ai, uint64_t row, uint64_t t0)
{
    int status = vbx_cnn_model_start(vbx, model, io);
    if (status != 0) {
        fprintf(stderr, "model_start ret=%d err=%d\n", status, (int)vbx_cnn_get_error_val(vbx));
        return -1;
    }

    int p = 1;
    int polls = 0;
    for (;;) {
        if (trip_enabled)
            check_trip_start(pid, trip, error_q34_30, last_u_ai, row, t0);
        p = vbx_cnn_model_poll(vbx);
        if (p <= 0)
            break;
        ++polls;
        if (polls > MAX_POLL_ITERS) {
            fprintf(stderr, "poll timeout err=%d\n", (int)vbx_cnn_get_error_val(vbx));
            return -1;
        }
    }
    if (p < 0 || vbx_cnn_get_error_val(vbx)) {
        fprintf(stderr, "poll ret=%d err=%d\n", p, (int)vbx_cnn_get_error_val(vbx));
        return -1;
    }
    if (polls_out) {
        *polls_out = polls;
    }
    return 0;
}

static int init_model_io(vbx_cnn_t *vbx, model_t *model, vbx_cnn_io_ptr_t *io, size_t *nin_out,
                         input0_t *input0)
{
    size_t nin = model_get_num_inputs(model);
    size_t nout = model_get_num_outputs(model);
    if (nin + nout > MAX_IO_BUFFERS) {
        fprintf(stderr, "too many model IO buffers: inputs=%zu outputs=%zu\n", nin, nout);
        return -1;
    }
    if (nout < 1 || model_get_output_datatype(model, 0) != VBX_CNN_CALC_TYPE_INT8) {
        fprintf(stderr, "expected at least one INT8 output\n");
        return -1;
    }
    if (nin != 1) {
        fprintf(stderr, "expected exactly one model input, got %zu\n", nin);
        return -1;
    }

    for (size_t i = 0; i < nin; ++i) {
        vbx_cnn_calc_type_e dtype = model_get_input_datatype(model, (int)i);
        size_t elems = model_get_input_length(model, (int)i);
        size_t bytes = dtype_bytes(dtype);
        if (bytes == 0 || elems == 0) {
            fprintf(stderr, "unsupported input %zu datatype=%d length=%zu\n", i, (int)dtype, elems);
            return -1;
        }
        void *ib = vbx_allocate_dma_buffer(vbx, elems * bytes, 0);
        if (!ib) {
            fprintf(stderr, "alloc input %zu failed\n", i);
            return -1;
        }
        memcpy(ib, model_get_test_input(model, (int)i), elems * bytes);
        io[i] = (vbx_cnn_io_ptr_t)(uintptr_t)ib;
        if (i == 0) {
            input0->buf = (uint8_t *)ib;
            input0->input_len = elems;
            input0->bytes = bytes;
            input0->dtype = dtype;
            input0->scale = model_get_input_scale_fix16_value(model, 0) / 65536.0;
            input0->zero_point = model_get_input_zeropoint(model, 0);
        }
    }
    for (size_t o = 0; o < nout; ++o) {
        size_t n = model_get_output_length(model, (int)o);
        void *ob = vbx_allocate_dma_buffer(vbx, n * sizeof(uint32_t), 0);
        if (!ob) {
            fprintf(stderr, "alloc output %zu failed\n", o);
            return -1;
        }
        memset(ob, 0, n * sizeof(uint32_t));
        io[nin + o] = (vbx_cnn_io_ptr_t)(uintptr_t)ob;
    }
    *nin_out = nin;
    return 0;
}

static void usage(const char *argv0)
{
    fprintf(stderr,
            "usage: %s [model.vnnx] [rows 1..10000] [warmup 0..1000] "
            "[input.csv | error_start] [error_step] [u_scale] [sleep_us] [input.csv] "
            "[--daemon] [--state path] [--pid-file path] [--no-trip-start]\n"
            "default: model=fcnn_v2_residual_dataset_a.vnnx rows=50 warmup=2 "
            "error_start=0.20 error_step=0.001 u_scale=1/64 sleep_us=0 input=embedded_test_vector\n"
            "input.csv rows: error_in,spectrum_0..spectrum_99,anchor_0..anchor_99\n",
            argv0);
}

int main(int argc, char **argv)
{
    const char *pos[12];
    int npos = 0;
    int daemon_mode = 0;
    int trip_enabled = 1;
    const char *state_path = NULL;
    const char *pid_file = NULL;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--daemon") == 0) {
            daemon_mode = 1;
        } else if (strcmp(argv[i], "--no-trip-start") == 0) {
            trip_enabled = 0;
        } else if (strcmp(argv[i], "--state") == 0 && i + 1 < argc) {
            state_path = argv[++i];
        } else if (strcmp(argv[i], "--pid-file") == 0 && i + 1 < argc) {
            pid_file = argv[++i];
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        } else if (npos < (int)(sizeof(pos) / sizeof(pos[0]))) {
            pos[npos++] = argv[i];
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    const char *vnnx = (npos > 0) ? pos[0] : "fcnn_v2_residual_dataset_a.vnnx";
    int rows = (npos > 1) ? atoi(pos[1]) : 50;
    int warmup = (npos > 2) ? atoi(pos[2]) : 2;
    double error_start = 0.20;
    double error_step = 0.001;
    double u_scale = DEFAULT_U_SCALE;
    int sleep_us = 0;
    const char *input_csv = NULL;

    if (npos > 3) {
        double parsed = 0.0;
        if (parse_double_full(pos[3], &parsed)) {
            error_start = parsed;
            error_step = (npos > 4) ? strtod(pos[4], NULL) : error_step;
            u_scale = (npos > 5) ? strtod(pos[5], NULL) : u_scale;
            sleep_us = (npos > 6) ? atoi(pos[6]) : sleep_us;
            input_csv = (npos > 7) ? pos[7] : NULL;
        } else {
            input_csv = pos[3];
            error_step = (npos > 4) ? strtod(pos[4], NULL) : error_step;
            u_scale = (npos > 5) ? strtod(pos[5], NULL) : u_scale;
            sleep_us = (npos > 6) ? atoi(pos[6]) : sleep_us;
        }
    }
    if (daemon_mode && !state_path) {
        state_path = DEFAULT_STATE_PATH;
    }

    if (rows < 1 || rows > 10000 || warmup < 0 || warmup > 1000 || sleep_us < 0) {
        usage(argv[0]);
        return 2;
    }
    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);
    if (write_pid_file(pid_file) != 0) {
        return 1;
    }

    volatile uint32_t *pid = map_slot3();
    if (!pid) {
        return 1;
    }

    uint32_t csr_version = rd(pid, R_CSR_VERSION);
    uint32_t watchdog_before = rd(pid, R_WATCHDOG);
    if (csr_version != CSR_VERSION_EXPECT) {
        fprintf(stderr, "unexpected csr_version=0x%08x, expected 0x%08x\n",
                csr_version, CSR_VERSION_EXPECT);
        munmap((void *)pid, PAGE);
        return 1;
    }

    wr(pid, R_OUT_MIN, f_to_q16(-1.0));
    wr(pid, R_OUT_MAX, f_to_q16(1.0));
    wr(pid, R_KP, f_to_q16(0.8));
    wr(pid, R_KI, f_to_q16(0.0));
    wr(pid, R_KD, f_to_q16(0.0));
    wr(pid, R_INNER_CLAMP, f_to_q16(0.045));

    vbx_cnn_t *vbx = vbx_cnn_init(NULL);
    if (!vbx || !vbx->initialized) {
        fprintf(stderr, "vbx_cnn_init failed\n");
        munmap((void *)pid, PAGE);
        return 1;
    }

    model_t *model = read_model_file(vbx, vnnx);
    if (!model) {
        fprintf(stderr, "read_model_file(%s) failed\n", vnnx);
        munmap((void *)pid, PAGE);
        return 1;
    }

    size_t nin = 0;
    vbx_cnn_io_ptr_t io[MAX_IO_BUFFERS];
    input0_t input0 = {0};
    if (init_model_io(vbx, model, io, &nin, &input0) != 0) {
        munmap((void *)pid, PAGE);
        return 1;
    }
    if (input0.input_len == 0 || input0.input_len % 2 != 0) {
        fprintf(stderr, "expected even input length for spectrum+anchor, got %zu\n", input0.input_len);
        munmap((void *)pid, PAGE);
        return 1;
    }

    row_set_t row_inputs = {0};
    if (input_csv && load_rows_csv(input_csv, input0.input_len, &row_inputs) != 0) {
        munmap((void *)pid, PAGE);
        return 1;
    }

    printf("v250_pid_loop model=%s rows=%d warmup=%d u_scale=%.9f daemon=%d "
           "csr_version=0x%08x watchdog_before=0x%08x model_inputs=%zu model_outputs=%zu "
           "input_len=%zu input_dtype=%d input_scale=%.9f input_zp=%d input_source=%s input_rows=%zu state=%s\n",
           vnnx, rows, warmup, u_scale, daemon_mode, csr_version, watchdog_before,
           model_get_num_inputs(model), model_get_num_outputs(model),
           input0.input_len, (int)input0.dtype, input0.scale, input0.zero_point,
           input_csv ? input_csv : "embedded_test_vector", row_inputs.rows,
           state_path ? state_path : "");
    printf("row,t_ns,v250_ns,polls,input_row,error_in,nn_out0,nn_q,u_ai,post_clamp,watchdog_raw,watchdog_timeout,axi_write_count\n");

    uint64_t t0 = nsec_now();
    wd_trip_start_state trip = WD_TRIP_START_INIT;
    uint32_t last_u_ai = rd(pid, R_U_AI);
    uint64_t iter = 0;
    uint64_t emitted = 0;
    while (keep_running && (daemon_mode || emitted < (uint64_t)rows)) {
        int emitting = iter >= (uint64_t)warmup;
        size_t src_row = 0;
        uint64_t logical_row = emitting ? emitted : iter;
        double err = error_start + error_step * (double)(logical_row % 97u);
        if (row_inputs.rows > 0) {
            src_row = (size_t)(logical_row % row_inputs.rows);
            quantize_flat_to_input(&row_inputs.flat[src_row * row_inputs.input_len], &input0);
            err = row_inputs.error[src_row];
        }

        uint32_t lo, hi;
        f_to_q34_30(err, &lo, &hi);
        int64_t error_q34_30 = (int64_t)(((uint64_t)hi << 32) | lo);
        if (trip_enabled)
            check_trip_start(pid, &trip, error_q34_30, last_u_ai, logical_row, t0);

        int polls = 0;
        uint64_t v0 = nsec_now();
        if (run_v250(vbx, model, io, &polls, pid, &trip, trip_enabled,
                     error_q34_30, last_u_ai, logical_row, t0) != 0) {
            free_rows(&row_inputs);
            munmap((void *)pid, PAGE);
            return 1;
        }
        uint64_t v1 = nsec_now();

        int q = 0;
        double nn_out = output0(io, nin, model, &q);
        double u_ai = nn_out * u_scale;
        wr(pid, R_ERROR_LOW, lo);
        wr(pid, R_ERROR_HIGH, hi);
        last_u_ai = f_to_q16(u_ai);
        wr(pid, R_U_AI, last_u_ai);
        wr(pid, R_ACC_START, 1);

        uint32_t post = rd(pid, R_POST_CLAMP);
        uint32_t wd = rd(pid, R_WATCHDOG);
        uint32_t writes = rd(pid, R_AXI_WRITE_COUNT);

        if (emitting) {
            uint64_t elapsed = nsec_now() - t0;
            printf("%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%d,%zu,%.9f,%.9f,%d,%.9f,%.9f,0x%08x,%u,0x%08x\n",
                   emitted, elapsed, v1 - v0, polls, src_row, err, nn_out, q, u_ai,
                   q16_to_f(post), wd, wd & 0x1u, writes);
            fflush(stdout);
            write_state_json(state_path, 1, emitted, elapsed, v1 - v0, polls, src_row,
                             err, nn_out, q, u_ai, q16_to_f(post), wd, writes,
                             trip.forced_starts,
                             input_csv ? input_csv : "embedded_test_vector");
            ++emitted;
        }

        if (sleep_us > 0) {
            usleep((useconds_t)sleep_us);
        }
        ++iter;
    }

    if (state_path) {
        write_state_json(state_path, 0, emitted, nsec_now() - t0, 0, 0, 0, 0.0,
                         0.0, 0, 0.0, 0.0, rd(pid, R_WATCHDOG),
                         rd(pid, R_AXI_WRITE_COUNT), trip.forced_starts,
                         input_csv ? input_csv : "embedded_test_vector");
    }
    free_rows(&row_inputs);
    if (pid_file) {
        unlink(pid_file);
    }
    munmap((void *)pid, PAGE);
    return 0;
}
