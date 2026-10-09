# PolarFire Hybrid Control — Top-Level Makefile
#
# Orchestrates builds across the HLS and Libero subsystems and the local
# corpus-grounded verification harness.
#
# - HLS testbench (`hls-test`) runs on a host with SmartHLS installed.
# - HLS testbench shim (`hls-test-local`) runs anywhere with g++.
# - Libero synthesis is host-side; remote runs use `beelink-verify`.

.PHONY: hls-test hls-test-local hls-test-cascade-local tb-actuator-local clean help \
        audit-reports audit-reports-strict audit-citations \
        verify-local verify-strict beelink-verify

REPORT_DIRS ?= libero/reports
TAG ?=
BEE_REMOTE ?= bee
BEE_REPO ?= ~/dev/projects/polarfire-hybrid-control

# ---------------------------------------------------------------------------
# HLS
# ---------------------------------------------------------------------------

# Run SmartHLS C++ software testbench (requires shls on PATH).
hls-test:
	cd hls && shls sw_run

# Compile and run the bumpless testbench against the checked-in ap_fixpt
# software shim. No SmartHLS required. Used by `verify-local`.
hls-test-local:
	@mkdir -p .build
	g++ -std=c++17 -O0 -g -Wall -Wno-unknown-pragmas \
		-Ihls/include -Ihls/src \
		hls/tb/tb_bumpless.cpp \
		hls/src/nv_pid.cpp hls/src/safety_clamps.cpp hls/src/watchdog.cpp \
		-o .build/tb_bumpless_local
	.build/tb_bumpless_local

# Compile and run the cascade composition + safety-pipeline-survival
# testbench. Same shim path as hls-test-local. No SmartHLS required.
# Reads fixture from hls/tb/stimulus/cascade_synthetic_v1/ — must be invoked
# from the repo root (which is what `make` does by default).
hls-test-cascade-local:
	@mkdir -p .build
	g++ -std=c++17 -O0 -g -Wall -Wno-unknown-pragmas \
		-Ihls/include -Ihls/src \
		hls/tb/tb_cascade.cpp \
		hls/src/nv_pid.cpp hls/src/safety_clamps.cpp hls/src/watchdog.cpp \
		-o .build/tb_cascade_local
	.build/tb_cascade_local

# Simulate the two-slot actuator datapath against generated SmartHLS RTL (iverilog >= 12).
# The RTL is produced by SmartHLS on the build host and is not checked in, so this target
# is not part of verify-local; run it where hls/hls_output/rtl/ exists.
tb-actuator-local:
	@test -f hls/hls_output/rtl/nv_pid_top_nv_pid_top.v || \
		{ echo "SmartHLS RTL required: hls/hls_output/rtl/nv_pid_top_nv_pid_top.v"; exit 1; }
	@mkdir -p .build
	iverilog -g2012 -s tb_actuator -o .build/tb_actuator \
		hls/hls_output/rtl/*.v \
		libero/hdl/axi4_demux2.v libero/hdl/pid_csr_block.v \
		libero/hdl/pid_csr_axi4_wrap.v libero/hdl/vbx_pulse_gen.v \
		libero/hdl/watchdog_timer.v libero/hdl/pid_subsystem.v \
		tests/two_slot_sim/tb_actuator.v
	vvp .build/tb_actuator

clean:
	rm -rf .build
	-cd hls && shls clean

# ---------------------------------------------------------------------------
# Corpus-grounded audit
# ---------------------------------------------------------------------------

audit-reports:
	python3 tools/audit_libero_reports.py $(REPORT_DIRS)

audit-reports-strict:
	python3 tools/audit_libero_reports.py --strict $(REPORT_DIRS)

audit-citations:
	python3 tools/audit_corpus_citations.py docs/ libero/ tools/ Makefile README.md

verify-local: hls-test-local hls-test-cascade-local audit-reports audit-citations

verify-strict: hls-test-local hls-test-cascade-local audit-reports-strict audit-citations

# ---------------------------------------------------------------------------
# Remote (Beelink) synthesis closure
# ---------------------------------------------------------------------------
# Captures `shls sw_run`, full Libero closure, report extraction, and audit
# into libero/reports/$(TAG)/. TAG is required.
beelink-verify:
	@if [ -z "$(TAG)" ]; then echo "TAG=<dated-tag> is required"; exit 2; fi
	bash tools/run_beelink_verification.sh "$(TAG)" "$(BEE_REMOTE)" "$(BEE_REPO)"

help:
	@echo "PolarFire Hybrid Control — Make Targets"
	@echo "  hls-test            Run SmartHLS C++ testbench (needs shls)"
	@echo "  hls-test-local      Run bumpless testbench via ap_fixpt shim (no shls)"
	@echo "  hls-test-cascade-local  Run cascade testbench (Phase II P3-11B)"
	@echo "  tb-actuator-local  Run two-slot actuator RTL bench (needs generated SmartHLS RTL)"
	@echo "  audit-reports       Audit Libero report bundles vs corpus"
	@echo "  audit-reports-strict  Same, fail-fast on critical pruning"
	@echo "  audit-citations     Verify corpus citations resolve"
	@echo "  verify-local        HLS tests + actuator RTL bench + report/citation audits"
	@echo "  verify-strict       hls-test-local + audit-reports-strict + audit-citations"
	@echo "  beelink-verify TAG=<tag>  Run full closure on Beelink, capture into libero/reports/<tag>/"
	@echo "  clean               Remove build artifacts"
