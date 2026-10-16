VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
# Python 3.11 is the CI route. See docs/reproduce-evidence.md for tested versions.
BENCH_PY ?= $(shell command -v python3.11 2>/dev/null || command -v python3)
EVIDENCE_PY ?= $(PYTHON)
KIT_EVIDENCE_DIR ?=
EVIDENCE_OUT ?=

# Official macOS CPU wheels have no +cpu local-version suffix.
ifeq ($(shell uname -s),Darwin)
TORCH_PIN := torch==2.11.0
else
TORCH_PIN := torch==2.11.0+cpu
endif

.PHONY: bench install smoke install-evidence verify-evidence test-reproduction
install: $(VENV)/.bench-ready

ifeq ($(BENCH_SKIP_INSTALL),1)
bench:
	"$(PYTHON)" bench/run_bench.py
smoke:
	"$(PYTHON)" -B scripts/smoke_install.py
else
bench: install
	"$(PYTHON)" bench/run_bench.py
smoke: install
	"$(PYTHON)" -B scripts/smoke_install.py
endif

$(VENV)/.bench-ready: Makefile workers/nv-sensor-sim/pyproject.toml workers/odmr-edge-ml/pyproject.toml
	@$(BENCH_PY) -c 'import sys; assert (3, 11) <= sys.version_info[:2] <= (3, 13), "Use Python 3.11 (CI), 3.12, or 3.13; set BENCH_PY=/path/to/python3.11"'
	$(BENCH_PY) -m venv "$(VENV)"
	"$(PYTHON)" -m pip install "$(TORCH_PIN)" --index-url https://download.pytorch.org/whl/cpu
	"$(PYTHON)" -m pip install numpy==2.4.2 scipy==1.17.1 simos==0.2.3 qutip==5.2.3 h5py==3.14.0 -e workers/nv-sensor-sim -e workers/odmr-edge-ml
	touch "$(VENV)/.bench-ready"

install-evidence: $(VENV)/.evidence-ready
$(VENV)/.evidence-ready: requirements-evidence.txt
	@$(BENCH_PY) -c 'import sys; assert (3, 11) <= sys.version_info[:2] <= (3, 13), "Use Python 3.11, 3.12, or 3.13; set BENCH_PY=/path/to/python3.11"'
	$(BENCH_PY) -m venv "$(VENV)"
	"$(PYTHON)" -m pip install -r requirements-evidence.txt
	touch "$(VENV)/.evidence-ready"

# Deliberately has no install dependency: verification is offline.
verify-evidence:
	"$(EVIDENCE_PY)" -B scripts/verify_evidence.py --kit-evidence-dir "$(KIT_EVIDENCE_DIR)" $(if $(EVIDENCE_OUT),--out "$(EVIDENCE_OUT)",)

test-reproduction:
	"$(BENCH_PY)" -B -m unittest discover -s scripts/tests -p 'test_reproduction.py' -v
