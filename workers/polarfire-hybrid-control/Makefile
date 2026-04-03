# PolarFire Hybrid Control — Top-Level Makefile
#
# This orchestrates builds across the HLS and Libero subsystems.
# HLS testbench runs on x86 (SmartHLS requirement). Libero synthesis
# requires Libero SoC installed on the build host.

.PHONY: hls-test clean help

# Run SmartHLS C++ software testbench (x86 only)
hls-test:
	cd hls && shls sw_run

# Clean all build artifacts
clean:
	cd hls && shls clean

# Show available targets
help:
	@echo "PolarFire Hybrid Control — Make Targets"
	@echo "  hls-test   Run SmartHLS C++ software testbench (x86 only)"
	@echo "  clean      Remove all build artifacts"
	@echo "  help       Show this message"
	@echo ""
	@echo "NOTE: SmartHLS and Libero targets require x86 host with Microchip tools installed."
	@echo "Libero Tcl scripts are in libero/scripts/ — run via Libero Tcl console."
