// Passive slot-3 observer. Never touch 0x60001000.
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

#define PAGE 0x1000UL
#define SLOT3_PAGE 0x60040000UL
#define R_AXI_WRITE_COUNT 0x60040800UL
#define R_CSR_VERSION 0x60040804UL
#define R_POST_CLAMP 0x60040844UL
#define R_WATCHDOG 0x60040854UL

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
static volatile uint32_t *map_slot3(void)
{
    int fd = open("/dev/mem", O_RDONLY | O_SYNC);
    if (fd < 0) { perror("open /dev/mem"); return NULL; }
    volatile uint32_t *p = mmap(NULL, PAGE, PROT_READ, MAP_SHARED, fd, (off_t)SLOT3_PAGE);
    close(fd);
    if (p == MAP_FAILED) { perror("mmap slot3"); return NULL; }
    return p;
}
static uint32_t rd(volatile uint32_t *base, unsigned long addr)
{
    uint32_t v = base[(addr - SLOT3_PAGE) / 4];
    __sync_synchronize();
    return v;
}
int main(int argc, char **argv)
{
    double duration_s = 0;
    int read_version = 0, read_watchdog = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--duration-s") && i + 1 < argc) {
            char *end;
            errno = 0;
            duration_s = strtod(argv[++i], &end);
            if (errno || *end || duration_s < 0 || duration_s > 86400) return 2;
        } else if (!strcmp(argv[i], "--read-csr-version")) read_version = 1;
        else if (!strcmp(argv[i], "--read-watchdog")) read_watchdog = 1;
        else { fprintf(stderr, "usage: %s [--duration-s 0..86400] [--read-csr-version|--read-watchdog]\n", argv[0]); return 2; }
    }
    volatile uint32_t *base = map_slot3();
    if (!base) return 1;
    uint32_t version = rd(base, R_CSR_VERSION);
    if (read_version || read_watchdog) {
        if (read_version) printf("0x%08x\n", version);
        if (read_watchdog) printf("0x%08x\n", rd(base, R_WATCHDOG));
        munmap((void *)base, PAGE);
        return 0;
    }
    if (version != 0x00010000u) {
        fprintf(stderr, "unexpected csr_version=0x%08x\n", version);
        munmap((void *)base, PAGE);
        return 1;
    }
    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    puts("rdtime_ticks,t_ns,wd_raw,wd_timeout_bit,wd_trip_count,axi_write_count,post_clamp_q16,poll_gap_max_ns");
    uint64_t begin = nsec_now(), last_poll = begin, max_gap = 0;
    uint32_t prev_wd = UINT32_MAX, prev_writes = UINT32_MAX, prev_post = UINT32_MAX;
    while (running) {
        uint32_t wd = rd(base, R_WATCHDOG);
        uint32_t writes = rd(base, R_AXI_WRITE_COUNT);
        uint32_t post = rd(base, R_POST_CLAMP);
        uint64_t ticks = rdtime_raw(), now = nsec_now();
        uint64_t gap = now - last_poll;
        if (gap > max_gap) max_gap = gap;
        last_poll = now;
        if (wd != prev_wd || writes != prev_writes || post != prev_post) {
            printf("%" PRIu64 ",%" PRIu64 ",0x%08x,%u,%u,%u,%" PRId32 ",%" PRIu64 "\n",
                   ticks, now, wd, wd & 1u, wd >> 1, writes, (int32_t)post, max_gap);
            fflush(stdout);
            prev_wd = wd; prev_writes = writes; prev_post = post; max_gap = 0;
        }
        if (duration_s > 0 && (double)(now - begin) >= duration_s * 1e9) break;
    }
    munmap((void *)base, PAGE);
    return 0;
}
