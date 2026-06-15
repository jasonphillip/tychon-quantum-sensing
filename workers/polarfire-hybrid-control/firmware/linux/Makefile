# firmware/linux/Makefile — cross-build the Icicle Linux userspace bring-up tools.
#
# Per the 2026-06-15 Linux/Yocto decision (docs/track0_bringup_runbook.md): the MSS
# side runs Linux, so these are glibc RISC-V userspace binaries, NOT bare-metal.
#
# Toolchain: SmartHLS-bundled glibc RISC-V GCC (present on bee at
#   /c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/swtools/binutils/riscv-gnu-toolchain/bin/).
# Put that bin on PATH, or pass CROSS=<prefix>.
#
# Build on bee (source of truth is spark1; copy/pull then build):
#   make CROSS=riscv64-unknown-linux-gnu- VBX_SDK=/c/Microchip/VectorBlox-SDK
#
# Targets:
#   pid_poke    — /dev/mem MMIO poke of the FIC_0 PID slot (no SDK deps; static).
#   vnnx_smoke  — V250 inference smoke test against the VBX 2.0.3 SoC runtime.

CROSS   ?= riscv64-unknown-linux-gnu-
CC      := $(CROSS)gcc
CFLAGS  ?= -O2 -Wall

VBX_SDK ?= /c/Microchip/VectorBlox-SDK
VBX_DRV := $(VBX_SDK)/drivers/vectorblox
VBX_FIX := $(VBX_SDK)/example/postprocess/libfixmath

all: pid_poke vnnx_smoke

# Standalone; static so it does not depend on the target rootfs glibc version.
pid_poke: pid_poke.c
	$(CC) $(CFLAGS) -static $< -o $@ -lm

# Icicle runtime = poll mode (USE_INTERRUPTS=0) + MSS-DDR udmabuf (MSS_DDR).
# Pulls the VBX runtime + model parser from the SDK tree on bee.
VNNX_DEFS := -DVBX_SOC_DRIVER -DMSS_DDR -DUSE_INTERRUPTS=0
VNNX_INC  := -I$(VBX_DRV) -I$(VBX_FIX)
VNNX_SRC  := vnnx_smoke.c $(VBX_DRV)/vbx_cnn_api.c $(VBX_DRV)/vbx_cnn_model.c

vnnx_smoke: vnnx_smoke.c
	$(CC) $(CFLAGS) $(VNNX_DEFS) $(VNNX_INC) $(VNNX_SRC) -o $@ -lm -lpthread

clean:
	rm -f pid_poke vnnx_smoke

.PHONY: all clean
