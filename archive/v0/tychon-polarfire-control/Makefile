# Tychon PolarFire Control — Top-Level Makefile
#
# This orchestrates builds across the HLS and Libero subsystems.
# Source is edited on DGX Spark (ARM64). SmartHLS/Libero synthesis
# runs on Beelink (x86) only.

.PHONY: hls-test clean help

# Run SmartHLS C++ software testbench (Beelink x86 only)
hls-test:
	cd hls && shls sw_run

# Clean all build artifacts
clean:
	cd hls && shls clean

# Show available targets
help:
	@echo "Tychon PolarFire Control — Make Targets"
	@echo "  hls-test   Run SmartHLS C++ software testbench (Beelink only)"
	@echo "  clean      Remove all build artifacts"
	@echo "  help       Show this message"
	@echo ""
	@echo "NOTE: SmartHLS and Libero targets run on Beelink (x86), not Spark (ARM64)."
	@echo "Libero Tcl scripts are in libero/scripts/ — run via Libero on Beelink."
