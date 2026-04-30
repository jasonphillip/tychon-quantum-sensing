# PolarFire Hybrid Control — Top-Level Makefile
#
# This orchestrates builds across the HLS and Libero subsystems.
# HLS testbench runs on x86 (SmartHLS requirement). Libero synthesis
# requires Libero SoC installed on the build host.

.PHONY: hls-test hls-test-local audit-reports audit-reports-strict verify-local verify-strict beelink-verify clean help

# Run SmartHLS C++ software testbench (x86 only)
hls-test:
	cd hls && shls sw_run

# Run the HLS testbench with the checked-in software-only ap_fixpt shim.
# This is a local behavioral smoke test; SmartHLS remains authoritative.
hls-test-local:
	g++ -std=c++17 -Ihls/include -Ihls/src hls/src/nv_pid.cpp hls/src/safety_clamps.cpp hls/tb/tb_bumpless.cpp -o /tmp/polarfire_tb_bumpless
	/tmp/polarfire_tb_bumpless

# Audit archived Libero/Synplify reports for timing and PID survival evidence.
audit-reports:
	python3 tools/audit_libero_reports.py

# Strict audit: applies fail-fast corpus gates (CL189/CL260 coefficient
# pruning, CoreVectorBlox output_valid wiring, positive timing slack) to
# bundles whose names match pid-real$, ^overnight-, or -strict$. Used by
# the overnight scheduled agents to fail their commit if synthesis comes
# back broken. Argument REPORT_DIRS optional (defaults to the three
# canonical bundles); pass to scope to a single overnight tag, e.g.:
#   make audit-reports-strict REPORT_DIRS=libero/reports/overnight-r1
audit-reports-strict:
	python3 tools/audit_libero_reports.py --strict $(REPORT_DIRS)

verify-local: hls-test-local audit-reports

verify-strict: hls-test-local audit-reports-strict

# Run the noninteractive Beelink verification wrapper. Optional:
#   make beelink-verify TAG=2026-04-30-corpus
beelink-verify:
	tools/run_beelink_verification.sh $(TAG)

# Clean all build artifacts
clean:
	cd hls && shls clean

# Show available targets
help:
	@echo "PolarFire Hybrid Control — Make Targets"
	@echo "  hls-test   Run SmartHLS C++ software testbench (x86 only)"
	@echo "  hls-test-local"
	@echo "             Run local g++ testbench with software ap_fixpt shim"
	@echo "  audit-reports"
	@echo "             Audit archived Libero/Synplify report bundles"
	@echo "  audit-reports-strict [REPORT_DIRS=...]"
	@echo "             Strict audit: corpus-backed fail-fast gates on "
	@echo "             pid-real / overnight-* / *-strict bundles"
	@echo "  verify-local"
	@echo "             Run local testbench and report audit"
	@echo "  verify-strict"
	@echo "             Run local testbench and STRICT report audit"
	@echo "  beelink-verify"
	@echo "             Run noninteractive Beelink SmartHLS/Libero verification"
	@echo "  clean      Remove all build artifacts"
	@echo "  help       Show this message"
	@echo ""
	@echo "NOTE: SmartHLS and Libero targets require x86 host with Microchip tools installed."
	@echo "Libero Tcl scripts are in libero/scripts/ — run via Libero Tcl console."
