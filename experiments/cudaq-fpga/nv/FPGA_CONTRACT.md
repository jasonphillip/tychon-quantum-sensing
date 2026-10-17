# NV synthetic finite-pulse estimator contract

This document defines the portable C/Python arithmetic interface. See the parent experiment README for recorded FPGA integration evidence.

Input is 128 signed 16-bit values, 14 fractional bits. Logical layout is `[quadrature,delay]` flattened in row order.
There are 64 uniform delays from zero to four microseconds.
Quadrature zero is `(counts_phase0-counts_phase_pi)/2800`.
Quadrature one is `(counts_phase_pi2-counts_phase_3pi2)/2800`.
The denominator is the assumed 20,000 repetitions times 0.14 photons of bright/dark contrast.
It is fixed calibration, never a true label.
Each input summarizes 5,120,000 assumed repetitions. Inference time is separate from acquisition time, which has not been measured.
Quantization uses nearest-even rounding, scale 16384, and saturation to [-32768,32767]. Any saturation must set a host warning.
The binary artifact uses little-endian signed integers. The C function receives native integer arrays after transport conversion.
Finite-value validation and quantization occur upstream. Raw photon counting is not implemented on the board.

Templates: 121 rows of 128 signed 16-bit integers, same scaling and layout. Total ROM data: 30,976 bytes.
Template index `k` maps to `detuning_hz = -750000 + 12500*k` for `0 <= k <= 120`.
This is signed model detuning, not a calibrated magnetic-field measurement.
The selected transition's rotating-frame sign is defined in README.md and nv_model.py.

Compute sum of 128 squared signed differences per template. Select the smallest sum; ties select the lowest index.
There are 15,488 distance terms per sample. This counts operations, not clocks or throughput.
The worst possible score is `128 * 65535^2 = 549739036800`. A 32-bit accumulator is insufficient.
The reference uses 64-bit intermediate differences, products, and unsigned accumulation.
It verifies the maximum score with extreme input values and checks tie behavior.

Output: unsigned 16-bit template index and unsigned 64-bit distance score.
Distance is not a calibrated confidence or anomaly probability. A rejection threshold is not established.

`nv_match.c` is the bounded loop implementation used by the authored HLS wrapper.
The compact template method does not require a neural model or `.vnnx` compilation.
The stress replay uses the same Q14 format with known repetition counts and nominal contrast.
For those inputs, divide quadrature count differences by `repetitions * 0.14`, not always 2800.
The parent experiment contains the separate board interface and execution evidence.
