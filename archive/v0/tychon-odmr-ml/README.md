# tychon-odmr-ml

Neural network training, INT8 quantization, and evaluation for NV-diamond ODMR magnetometry. Part of the Tychon AI 90-day plan (Deliverable 2).

Consumes synthetic ODMR datasets from [`tychon-nv-sim`](https://github.com/tychon-ai/tychon-nv-sim) and produces model artifact bundles for downstream FPGA deployment.

## Quick Start

```bash
pip install -e ".[dev]"
make test
```

## Spec

See `docs/phase1-context/repo2-odmr-ml-spec.md`.
