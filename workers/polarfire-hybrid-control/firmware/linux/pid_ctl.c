// pid_ctl.c — read/write the two-slot PID fabric slaves via /dev/mem.
// Target: MPFS250T Icicle Kit, two-slot bitstream, Linux on the U54 cores.
//
// Both sub-slaves live in the one free crossbar slot SLAVE3 (page 0x60040000),
// split by pid_subsystem's axi4_demux2 (both respond cleanly — no severed read):
//   nv_pid_top.axi4target  @ 0x60040000  (SmartHLS gains; clean R/W)
//     0x60040008 acc_start  0x6004000C Kp  0x60040010 Ki  0x60040014 Kd
//     0x60040018 out_min    0x6004001C out_max               (all Q16.16)
//   pid_csr  @ 0x60040800  (clean hand-written CSR, AXI4-Lite-via-bridge)
//     0x60040800 axi_write_count RO   0x60040804 csr_version RO (=0x00010000)
//     0x60040810 error_low RW  0x60040814 error_high RW  0x60040818 u_ai RW (Q16.16)
//     0x60040820 Kp_shdw .. 0x60040834 inner_clamp_shdw  RW (Q16.16)
//     0x60040844 post_clamp RO (actuator, Q16.16, LIVE)
//     0x60040854 watchdog_csr RO (bit0 timeout, LIVE) ; other taps tied 0 (disclosed)
// (0x60001000 is the DMA-controller CTRL, NOT the PID — do not poke it.)
//
// error is Q34.30 (64-bit, split low/high); gains/u_ai/actuator are Q16.16.
// Q16.16: raw = lround(f*65536); f = (int32_t)raw / 65536.0.
//
// Build (bee): riscv64-unknown-linux-gnu-gcc -O2 -Wall -static pid_ctl.c -o pid_ctl -lm
// Usage:
//   ./pid_ctl r    0x60040004           # read csr_version (hex + Q16.16 float)
//   ./pid_ctl w    0x60040020 0.5       # write Kp_shadow = 0.5 (Q16.16)
//   ./pid_ctl wraw 0x60040010 0x12345678# write raw u32 (e.g. error_low half)
//   ./pid_ctl repl                      # stdin lines: "r A", "w A f", "wraw A x", "q"
//                                       # one result line per command (for the harness)
//
// Addresses are restricted to the two known 4 KiB slot pages unless --any is given,
// so a stray poke cannot wander into another peripheral.

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

#define PAGE       0x1000UL
#define SLOT3_PAGE 0x60040000UL   // SLAVE3 page: gains @ +0x000, pid_csr @ +0x800

static int allow_any = 0;

static double q16_to_float(uint32_t raw) { return (double)(int32_t)raw / 65536.0; }
static uint32_t float_to_q16(double v)   { return (uint32_t)(int32_t)llround(v * 65536.0); }

static int addr_ok(unsigned long addr)
{
    if (addr & 0x3UL) return 0;
    if (allow_any) return 1;
    return ((addr & ~(PAGE - 1)) == SLOT3_PAGE);
}

// Lazy page cache (repl mode reuses mappings).
#define MAXMAPS 4
static struct { unsigned long base; volatile uint32_t *m; } maps[MAXMAPS];
static int nmaps = 0;

static volatile uint32_t *word_ptr(int fd, unsigned long addr)
{
    unsigned long base = addr & ~(PAGE - 1);
    for (int i = 0; i < nmaps; i++)
        if (maps[i].base == base)
            return maps[i].m + ((addr - base) / 4);
    if (nmaps >= MAXMAPS) return NULL;
    volatile uint32_t *m = mmap(NULL, PAGE, PROT_READ | PROT_WRITE,
                                MAP_SHARED, fd, (off_t)base);
    if (m == MAP_FAILED) return NULL;
    maps[nmaps].base = base;
    maps[nmaps].m = m;
    nmaps++;
    return m + ((addr - base) / 4);
}

// Execute one op; returns 0 ok, nonzero error. Prints a result line.
static int do_op(int fd, const char *op, unsigned long addr, const char *valstr)
{
    if (!addr_ok(addr)) {
        printf("ERR addr 0x%lx out-of-slot-or-unaligned\n", addr);
        return 2;
    }
    volatile uint32_t *reg = word_ptr(fd, addr);
    if (!reg) { printf("ERR mmap 0x%lx\n", addr); return 1; }

    if (!strcmp(op, "r")) {
        uint32_t v = *reg;
        printf("0x%08lx = 0x%08x  (%.6f)\n", addr, v, q16_to_float(v));
    } else if (!strcmp(op, "w")) {
        if (!valstr) { printf("ERR need value\n"); return 2; }
        uint32_t v = float_to_q16(strtod(valstr, NULL));
        *reg = v;
        printf("wrote 0x%08lx = 0x%08x  (%.6f)\n", addr, v, q16_to_float(v));
    } else if (!strcmp(op, "wraw")) {
        if (!valstr) { printf("ERR need value\n"); return 2; }
        uint32_t v = (uint32_t)strtoul(valstr, NULL, 0);
        *reg = v;
        printf("wrote 0x%08lx = 0x%08x\n", addr, v);
    } else {
        printf("ERR unknown op %s\n", op);
        return 2;
    }
    fflush(stdout);
    return 0;
}

int main(int argc, char **argv)
{
    int ai = 1;
    if (argc > 1 && !strcmp(argv[1], "--any")) { allow_any = 1; ai = 2; }
    if (argc <= ai) {
        fprintf(stderr,
            "usage: %s [--any] r <addr> | w <addr> <float> | wraw <addr> <hex> | repl\n",
            argv[0]);
        return 2;
    }

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("open /dev/mem"); return 1; }

    int rc = 0;
    if (!strcmp(argv[ai], "repl")) {
        char line[128];
        while (fgets(line, sizeof line, stdin)) {
            char op[16] = {0}, a[32] = {0}, v[48] = {0};
            int n = sscanf(line, "%15s %31s %47s", op, a, v);
            if (n < 1) continue;
            if (!strcmp(op, "q") || !strcmp(op, "quit")) break;
            if (n < 2) { printf("ERR\n"); fflush(stdout); continue; }
            do_op(fd, op, strtoul(a, NULL, 0), n >= 3 ? v : NULL);
        }
    } else {
        unsigned long addr = strtoul(argv[ai + 1], NULL, 0);
        const char *val = (argc > ai + 2) ? argv[ai + 2] : NULL;
        rc = do_op(fd, argv[ai], addr, val);
    }

    for (int i = 0; i < nmaps; i++) munmap((void *)maps[i].m, PAGE);
    close(fd);
    return rc;
}
