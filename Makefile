VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
# Interpreter used to create the venv: python3.11 when present (the CI route), otherwise any python3 of 3.11 or newer.
BENCH_PY ?= $(shell command -v python3.11 2>/dev/null || command -v python3)

.PHONY: bench
ifeq ($(BENCH_SKIP_INSTALL),1)
bench:
	$(PYTHON) bench/run_bench.py
else
bench: $(VENV)/.bench-ready
	$(PYTHON) bench/run_bench.py

$(VENV)/.bench-ready: Makefile workers/nv-sensor-sim/pyproject.toml workers/odmr-edge-ml/pyproject.toml
	@$(BENCH_PY) -c 'import sys; v=sys.version_info; assert v >= (3, 11), "make bench needs Python 3.11 or newer; found %s (set BENCH_PY=/path/to/python3.11)" % sys.version.split()[0]'
	$(BENCH_PY) -m venv $(VENV)
	$(PYTHON) -m pip install torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
	$(PYTHON) -m pip install numpy==2.4.2 scipy==1.17.1 simos==0.2.3 qutip==5.2.3 h5py==3.14.0 -e workers/nv-sensor-sim -e workers/odmr-edge-ml
	touch $(VENV)/.bench-ready
endif
