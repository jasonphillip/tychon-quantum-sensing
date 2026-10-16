#!/usr/bin/env python3
"""Check CPU imports and four disposable synthetic spectra. No model inference."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import tempfile

for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[name] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import h5py
import numpy as np
import torch
from nv_sensor_sim.pipelines.batch_generate import generate_dataset

torch.set_num_threads(1)
with tempfile.TemporaryDirectory(prefix="tychon-install-smoke-") as directory:
    generate_dataset(directory, n_train=2, n_val=1, n_test=1, master_seed=20261016, n_freq_points=512)
    output = Path(directory)
    if not (output / "dataset.h5").is_file() or not (output / "manifest.json").is_file():
        raise RuntimeError("Simulator did not create the documented outputs")
    with h5py.File(output / "dataset.h5", "r") as data:
        # DatasetWriter stores each split in its own HDF5 group.
        for split, count in (("train", 2), ("val", 1), ("test", 1)):
            values = data[f"{split}/spectra"][()]
            frequencies = data[f"{split}/frequencies"][()]
            if values.shape != (count, 512) or not np.isfinite(values).all():
                raise RuntimeError(f"Expected {count} finite 512-point spectra in {split}")
            if frequencies.shape != (512,) or not np.isfinite(frequencies).all() or not np.all(np.diff(frequencies) > 0):
                raise RuntimeError(f"Invalid frequency axis in {split}")
print(json.dumps({
    "status": "PASS",
    "scope": "CPU imports and four temporary synthetic spectra; no training or inference",
    "platform": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
    "packages": {name: importlib.metadata.version(name) for name in
                 ("torch", "numpy", "scipy", "simos", "qutip", "h5py")},
}, indent=2))
