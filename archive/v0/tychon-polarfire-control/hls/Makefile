# SmartHLS Makefile for NV-Magnetometer PID Controller
#
# NOTE: These targets run on Beelink (x86 with SmartHLS installed),
#       NOT on DGX Spark (ARM64). SmartHLS is x86-only.
#
# Standard SmartHLS Makefile structure:
#   sw_run  — Compile and run C++ software testbench
#   hw      — Generate RTL (Verilog) from C++ via SmartHLS
#   cosim   — Co-simulation (ModelSim/QuestaSim cycle-accurate verification)
#   clean   — Remove all generated files

SRCS = src/nv_pid.cpp
TB_SRCS = tb/tb_bumpless.cpp
INCLUDES = -Iinclude -Isrc

# SmartHLS program name
NAME = nv_pid_top

.PHONY: sw_run hw cosim clean

# Software testbench: compile as standard C++ and run
sw_run:
	shls sw_run

# RTL generation: C++ → Verilog with AXI interfaces
hw:
	shls hw

# Co-simulation: verify RTL matches software behavior
cosim:
	shls cosim

# Clean all SmartHLS-generated artifacts
clean:
	shls clean
