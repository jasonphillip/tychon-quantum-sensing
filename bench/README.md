# Synthetic ODMR CPU benchmark

`make bench` produced 10.53 µT mean field error against a 12.26 µT training-mean baseline on 200 synthetic test spectra, using FP32 CPU inference. Jason directed the coding agents and checked claims with local critics. Run the command at the monorepo root from a clean checkout. It creates `.venv`, installs CPU PyTorch and both workers, then runs the benchmark. Later runs reuse the venv.
Python 3.11 (the CI route), 3.12 or 3.13 and pip access to PyPI and the PyTorch CPU wheel index are required
(the Makefile uses `python3.11` when present, otherwise `python3`; override with `BENCH_PY=`).
CI runs it on Python 3.11; the reference values in `bench/expected.json` were measured with 3.13.11.
Platform note: `simos==0.2.3` is pure Python. The pinned `qutip==5.2.3` has binary wheels for Python 3.11 on
Linux x86-64, macOS (x86-64 and arm64) and Windows, but not on Linux aarch64 (PyPI file list, checked 2026-10-15).
There, and on other interpreter versions, pip builds qutip from source and needs the Python headers (`python3-dev`)
and a C compiler. If `make bench` fails at that step, install those build dependencies, or on x86-64 use
`BENCH_PY=python3.11`. The committed reference and tolerances (`bench/README.md`, `bench/expected.json`) and the
CI run logs remain the record when a local run is not possible.

```sh
make bench
```

For installation without training, use `make install BENCH_PY=python3.11`, then `make smoke`.
The smoke check imports dependencies and generates four disposable spectra.
Linux installs `torch==2.11.0+cpu`; macOS installs the official `torch==2.11.0` wheel without that suffix.
To verify published saved metrics without training, use the separate
[`make verify-evidence` guide](../docs/reproduce-evidence.md).
It requires pinned public kit records and uses only NumPy and SciPy.

The simulator generates 1,000 training, 200 validation, and 200 test spectra with
master seed 12345 and a 2.866–2.874 GHz sweep. Splits have disjoint seeds and
share the same parameter ranges. The benchmark trains
a 10,689-parameter scalar `OdmrMLP` (100→64→64→1) on CPU for 1,000 full-batch epochs with seed
20261009. It reports magnetic field magnitude error in microtesla. It also
reports a training-mean baseline and the worker's derivative zero-crossing PID
proxy on the same 200 test spectra. The training-mean baseline predicts the
mean training label for every test spectrum. The PID proxy estimates field
magnitude from zero crossings of the spectrum derivative; it is not a closed-loop
controller. MAE is mean absolute error; RMSE is root mean squared error.
Validation MAE is measured on the validation split; all other errors use the
test split. The model is trained during each run; no
checkpoint is loaded. `bench/results.json` records metrics and a data digest.
The command exits nonzero when a metric exceeds its absolute tolerance in
`bench/expected.json`, the model beats the training mean by less than 1.00 µT,
or its test MAE is not lower than the PID-proxy MAE. The relational checks use
the measured baselines, so a model worse than the mean cannot pass on tolerance
alone.

The fixed-seed reference test MAE is 10.5303 µT. The training-mean test MAE is
12.2623 µT, a 1.7321 µT gain (14.1% of baseline MAE). The PID-proxy test MAE
is 25.9310 µT, a 15.4008 µT gain. On this host, two same-seed runs produced
byte-identical results. To set absolute tolerances, we also ran five different
paired data/model seeds (12345–12349 and 20261009–20261013). The full ranges
were 1.9034 µT for validation MAE, 0.8854 for test MAE, 0.8733 for test RMSE,
0.5787 for training-mean MAE, and 2.2322 for PID-proxy MAE. We rounded each
range up to 2.00, 1.00, 1.00, 0.65, and 2.50 µT respectively. These ranges
reflect different synthetic draws and initial weights, not same-seed numerical
variation or measured cross-platform drift. The relational checks remain
mandatory even when an absolute tolerance passes.

This is a reproducibility check on synthetic data. It does not measure real sensor
data, hardware accuracy, INT8 export or equivalence, FPGA execution, or a vendor
toolchain. Its metrics do not reproduce the separate 4.90% INT8 versus PID
experiment, which used another dataset and a trained production checkpoint.
