# firmware/linux/Makefile — cross-build the Icicle Linux userspace bring-up tools.
#
# Per the 2026-06-15 Linux/Yocto decision (docs/track0_bringup_runbook.md): the MSS
# side runs Linux, so these are glibc RISC-V userspace binaries, NOT bare-metal.
#
# Toolchain: SmartHLS-bundled glibc RISC-V GCC (present on bee at
#   $SHLS/swtools/binutils/riscv-gnu-toolchain/bin/, SHLS=/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS).
#
# GOTCHA (verified 2026-06-15): that GCC is a CYGWIN build. Run standalone it
# silently fails to start with exit 127 unless cygwin1.dll is on PATH. Set PATH
# before invoking make (toolchain bin FIRST, then the cygwin runtime dir):
#   SHLS=/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS
#   export PATH="$SHLS/swtools/binutils/riscv-gnu-toolchain/bin:$SHLS/dependencies/lib/cygwin:$PATH"
#   make CROSS=riscv64-unknown-linux-gnu- VBX_SDK=/c/Microchip/VectorBlox-SDK
#
# Verified output: pid_poke = static RISC-V ELF; vnnx_smoke = dynamic RISC-V ELF
# (interp /lib/ld-linux-riscv64-lp64d.so.1), both "for GNU/Linux".
#
# Targets:
#   pid_poke      — /dev/mem MMIO poke of the FIC_0 PID slot (no SDK deps; static).
#   pid_latency   — idfix2 PID M0 start -> M1 post_clamp timing probe (static).
#   vnnx_smoke    — V250 inference smoke test against the VBX 2.0.3 SoC runtime.
#   vnnx_latency  — V250 start/poll latency probe with rdcycle + monotonic timing.
#   v250_pid_loop — on-kit V250 output -> M1 u_ai -> M0 PID pulse loop.

CROSS   ?= riscv64-unknown-linux-gnu-
CC      := $(CROSS)gcc
CFLAGS  ?= -O2 -Wall

VBX_SDK ?= /c/Microchip/VectorBlox-SDK
VBX_DRV := $(VBX_SDK)/drivers/vectorblox
VBX_FIX := $(VBX_SDK)/example/postprocess/libfixmath

all: pid_poke pid_latency vnnx_smoke vnnx_latency v250_pid_loop

# Standalone; static so it does not depend on the target rootfs glibc version.
pid_poke: pid_poke.c
	$(CC) $(CFLAGS) -static $< -o $@ -lm

pid_latency: pid_latency.c
	$(CC) $(CFLAGS) -static $< -o $@ -lm

# Icicle runtime = poll mode (USE_INTERRUPTS=0) + MSS-DDR udmabuf (MSS_DDR).
# Pulls the VBX runtime + model parser from the SDK tree on bee.
VNNX_DEFS := -DVBX_SOC_DRIVER -DMSS_DDR -DUSE_INTERRUPTS=0
VNNX_INC  := -I$(VBX_DRV) -I$(VBX_FIX)
VNNX_RT   := $(VBX_DRV)/vbx_cnn_api.c $(VBX_DRV)/vbx_cnn_model.c

vnnx_smoke: vnnx_smoke.c
	$(CC) $(CFLAGS) $(VNNX_DEFS) $(VNNX_INC) $< $(VNNX_RT) -o $@ -lm -lpthread

vnnx_latency: vnnx_latency.c
	$(CC) $(CFLAGS) $(VNNX_DEFS) $(VNNX_INC) $< $(VNNX_RT) -o $@ -lm -lpthread

v250_pid_loop: v250_pid_loop.c
	$(CC) $(CFLAGS) $(VNNX_DEFS) $(VNNX_INC) $< $(VNNX_RT) -o $@ -lm -lpthread

clean:
	rm -f pid_poke pid_latency vnnx_smoke vnnx_latency v250_pid_loop

.PHONY: all clean
