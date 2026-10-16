# Batched vector inversion qualification

This package prepares an ideal eight-line Hamiltonian and strong batched classical references.
No neural advantage or numerical validation is claimed yet.
See [protocol.md](protocol.md) and [config.json](config.json).

Configure absolute paths to an approved source checkout, existing Python, approval, and a new output directory.
The accounting supervisor must launch the exact command.
Do not run it outside that supervisor.

```sh
"$PYTHON" "$SOURCE/experiments/vector_direct_screen/qualify.py" \
  --gate "$GATE" --approval-sha256 "$GATE_SHA256" --out "$NEW_OUTPUT" \
  --phase fixtures --backend numpy --device cpu --dtype float64 --variant affine --batch 64
```

Other separately approved phases are fidelity, solver, and profile.
The approval pins the exact phase, backend, device, dtype, variant, and batch.
GPU commands use the same absolute Python and script form with backend torch and device cuda.
This package creates no subprocesses.
NumPy, SciPy, and PyTorch are dependencies; no installation is authorized.
Root must pin all package Python, JSON, and Markdown files before execution.

No hardware, FPGA compilation, Beelink access, or old experiment is part of this package.
