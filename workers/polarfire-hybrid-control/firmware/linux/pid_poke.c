// pid_poke.c — read/write the fabric PID registers via /dev/mem (Linux userspace).
// Target: MPFS250T Icicle Kit, seed_7 bitstream, Linux on the U54 cores.
// Part of the 2026-06-15 Linux/Yocto bring-up path (docs/track0_bringup_runbook.md).
//
// PID slot = FIC_0_PERIPHERALS_1.AXI4mslave0 @ 0x60001000 (4 KB window).
// Real AXI slave that returns RDATA is nv_pid_top_top.axi4target. Its offsets
// (per docs/fic_0_address_map_2026-05-18.md / docs/seed_7_register_map_2026-05-04.md):
//   0x08 acc_start (RW: write 1 = start)   0x0C Kp (RW Q16.16)   0x10 Ki (RW Q16.16)
//   0x14 Kd (RW Q16.16)                    0x18 out_min (RW)     0x1C out_max (RW)
//
// EAVESDROPPER CAVEAT: pid_io_block shares this window but its read path is severed
// (tied to an LED OR-tap), so ALL reads land on nv_pid_top_top. Writes to 0x08/0x0C/0x10
// ALSO drive pid_io_block inputs (acc_start->error_low, Kp->error_high, Ki->u_ai_in) —
// a write-collision. The CLEAN write->read loopback addresses (touch exactly one reg)
// are 0x14 (Kd) / 0x18 (out_min) / 0x1C (out_max). Prefer those for liveness checks.
//
// Q16.16: raw = lround(f * 65536); f = (int32_t)raw / 65536.0  (signed).
//   0x00001000 = 0.0625   0x00010000 = 1.0
//
// Build (on bee): riscv64-unknown-linux-gnu-gcc -O2 -Wall -static pid_poke.c -o pid_poke -lm
// Usage:
//   ./pid_poke r    0x14            # read Kd, print hex + float
//   ./pid_poke w    0x14 0.0625     # write Kd = 0.0625  (-> 0x00001000)
//   ./pid_poke wraw 0x08 0x1        # write raw u32 (e.g. acc_start = 1)
//
// NOTE: needs /dev/mem with the 0x60001000 range accessible. If the kernel was built
// with CONFIG_STRICT_DEVMEM and blocks it, add a generic-uio DT node for 0x60001000
// (see firmware/linux/seed7_vbx_pid.dtso) and mmap /dev/uioN instead.

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

#define PID_BASE 0x60001000UL
#define PID_SPAN 0x1000UL          // 4 KB window (page-aligned)

static double q16_to_float(uint32_t raw) { return (double)(int32_t)raw / 65536.0; }
static uint32_t float_to_q16(double v)   { return (uint32_t)(int32_t)llround(v * 65536.0); }

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr,
            "usage: %s r <off> | w <off> <float> | wraw <off> <hexval>\n"
            "  off in [0x08,0x0C,0x10,0x14,0x18,0x1C]; clean loopback: 0x14/0x18/0x1C\n",
            argv[0]);
        return 2;
    }

    unsigned long off = strtoul(argv[2], NULL, 0);
    if (off >= PID_SPAN || (off & 0x3)) {
        fprintf(stderr, "offset 0x%lx out of range or unaligned\n", off);
        return 2;
    }

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("open /dev/mem"); return 1; }

    volatile uint32_t *map = mmap(NULL, PID_SPAN, PROT_READ | PROT_WRITE,
                                  MAP_SHARED, fd, (off_t)PID_BASE);
    if (map == MAP_FAILED) { perror("mmap"); close(fd); return 1; }
    volatile uint32_t *reg = map + (off / 4);   // word-indexed

    int rc = 0;
    if (!strcmp(argv[1], "r")) {
        uint32_t v = *reg;
        printf("0x%04lx = 0x%08x  (%.6f)\n", off, v, q16_to_float(v));
    } else if (!strcmp(argv[1], "w")) {
        if (argc < 4) { fprintf(stderr, "need value\n"); rc = 2; goto out; }
        uint32_t v = float_to_q16(strtod(argv[3], NULL));
        *reg = v;
        printf("wrote 0x%04lx = 0x%08x  (%.6f)\n", off, v, q16_to_float(v));
    } else if (!strcmp(argv[1], "wraw")) {
        if (argc < 4) { fprintf(stderr, "need value\n"); rc = 2; goto out; }
        uint32_t v = (uint32_t)strtoul(argv[3], NULL, 0);
        *reg = v;
        printf("wrote 0x%04lx = 0x%08x\n", off, v);
    } else {
        fprintf(stderr, "unknown op %s\n", argv[1]); rc = 2;
    }

out:
    munmap((void *)map, PID_SPAN);
    close(fd);
    return rc;
}
