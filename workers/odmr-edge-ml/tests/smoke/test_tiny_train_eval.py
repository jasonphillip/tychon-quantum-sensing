"""Smoke tests: CPU-only end-to-end with golden dataset.

Loads golden data, runs forward passes through MLP and CNN,
and runs PID baseline. Verifies output shapes and finite values.
"""

from pathlib import Path

import torch
import pytest

from odmr_edge_ml.baselines.pid_proxy import PidProxy
from odmr_edge_ml.data.loaders import DatasetLoader
from odmr_edge_ml.models.cnn1d import OdmrCNN1D
from odmr_edge_ml.models.mlp import OdmrMLP

GOLDEN_DIR = Path(__file__).resolve().parent.parent.parent / "data/golden"

pytestmark = pytest.mark.skipif(
    not (GOLDEN_DIR / "manifest.json").exists(),
    reason="Golden dataset not available",
)


@pytest.fixture
def loader() -> DatasetLoader:
    return DatasetLoader(GOLDEN_DIR, normalize=True)


def test_load_golden_and_forward_mlp(loader):
    """Load golden dataset, normalize, MLP forward pass, check output shape."""
    ds = loader.to_torch("test")
    spectra, labels = ds[:]
    assert spectra.shape == (20, 100)
    assert labels.shape == (20, 3)

    model = OdmrMLP()
    model.eval()
    with torch.no_grad():
        out = model(spectra)
    assert out.shape == (20, 3)
    assert torch.isfinite(out).all()


def test_load_golden_and_forward_cnn(loader):
    """Load golden dataset, normalize, CNN forward pass, check output shape."""
    ds = loader.to_torch("test")
    spectra, _ = ds[:]

    model = OdmrCNN1D()
    model.eval()
    with torch.no_grad():
        out = model(spectra)
    assert out.shape == (20, 3)
    assert torch.isfinite(out).all()


def test_pid_baseline_on_golden(loader):
    """Run PID proxy on golden test split, verify output shape."""
    ds = loader.load_split("test")
    manifest = loader.manifest
    freq_range = tuple(manifest["freq_range_Hz"])

    pid = PidProxy(
        n_freq_points=manifest["n_freq_points"],
        freq_range_hz=freq_range,
    )
    estimates = pid.estimate_batch(ds.spectra)
    assert estimates.shape == (20, 3)
    # Bx, By should be 0 (PID is single-axis)
    assert (estimates[:, 0] == 0.0).all()
    assert (estimates[:, 1] == 0.0).all()
