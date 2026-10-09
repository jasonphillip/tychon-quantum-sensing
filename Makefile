VENV ?= .venv
PYTHON ?= $(VENV)/bin/python

.PHONY: bench
ifeq ($(BENCH_SKIP_INSTALL),1)
bench:
	$(PYTHON) bench/run_bench.py
else
bench: $(VENV)/.bench-ready
	$(PYTHON) bench/run_bench.py

$(VENV)/.bench-ready: Makefile workers/nv-sensor-sim/pyproject.toml workers/odmr-edge-ml/pyproject.toml
	python3.11 -m venv $(VENV)
	$(PYTHON) -m pip install torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
	$(PYTHON) -m pip install numpy==2.4.2 scipy==1.17.1 simos==0.2.3 qutip==5.2.3 h5py==3.14.0 -e workers/nv-sensor-sim -e workers/odmr-edge-ml
	touch $(VENV)/.bench-ready
endif
