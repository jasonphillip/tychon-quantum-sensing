"""Tests for the training loop and physics-stratified validation."""

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from tychon_odmr_ml.training.loop import (
    TrainConfig,
    init_weights_kaiming_he,
    train,
    validate_physics_regimes,
)


def _make_synthetic_loader(n: int = 64, batch_size: int = 16) -> DataLoader:
    """Create a DataLoader with dict batches of synthetic data."""
    spectra = torch.randn(n, 100)
    # Simple linear relationship so network can learn it
    true_w = torch.randn(100, 3) * 0.01
    labels = spectra @ true_w

    class DictDataset(torch.utils.data.Dataset):
        def __init__(self, s, l):
            self.s = s
            self.l = l

        def __len__(self):
            return len(self.s)

        def __getitem__(self, idx):
            return {"spectra": self.s[idx], "b_field_uT": self.l[idx]}

    return DataLoader(DictDataset(spectra, labels), batch_size=batch_size)


def _make_synthetic_loader_with_meta(
    n: int = 64, batch_size: int = 16
) -> DataLoader:
    """Create a DataLoader with dict batches including corruption_params meta."""
    spectra = torch.randn(n, 100)
    true_w = torch.randn(100, 3) * 0.01
    labels = spectra @ true_w
    corruption = torch.rand(n, 4)
    # Ensure some samples exceed thresholds for stratification
    corruption[:n // 4, 2] = 0.2  # b1_gradient > 0.1
    corruption[:n // 4, 3] = 2e-5  # b_perp > 1e-5

    class DictDatasetMeta(torch.utils.data.Dataset):
        def __init__(self, s, l, c):
            self.s = s
            self.l = l
            self.c = c

        def __len__(self):
            return len(self.s)

        def __getitem__(self, idx):
            return {
                "spectra": self.s[idx],
                "b_field_uT": self.l[idx],
                "meta": {"corruption_params": self.c[idx]},
            }

    def collate(batch):
        spectra = torch.stack([b["spectra"] for b in batch])
        labels = torch.stack([b["b_field_uT"] for b in batch])
        meta = {"corruption_params": torch.stack([b["meta"]["corruption_params"] for b in batch])}
        return {"spectra": spectra, "b_field_uT": labels, "meta": meta}

    return DataLoader(DictDatasetMeta(spectra, labels, corruption), batch_size=batch_size, collate_fn=collate)


class TinyMLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(100, 32), nn.ReLU(), nn.Linear(32, 3)
        )

    def forward(self, x):
        return self.net(x)


def test_kaiming_he_changes_weights_zeros_biases():
    model = TinyMLP()
    # Record original weights
    orig_weight = model.net[0].weight.data.clone()
    orig_bias = model.net[0].bias.data.clone()

    init_weights_kaiming_he(model)

    # Weights should change (extremely unlikely to be identical)
    assert not torch.equal(model.net[0].weight.data, orig_weight)
    # Biases should be zero
    assert torch.equal(model.net[0].bias.data, torch.zeros_like(orig_bias))
    assert torch.equal(model.net[2].bias.data, torch.zeros(3))


def test_train_runs_5_epochs():
    model = TinyMLP()
    loader = _make_synthetic_loader(n=32, batch_size=16)
    config = TrainConfig(epochs=5, val_every=5, batch_size=16)
    device = torch.device("cpu")

    result = train(model, loader, None, config, device)

    assert "final_train_loss" in result
    assert "training_time_s" in result
    assert len(result["epoch_history"]) == 5
    assert result["final_train_loss"] < float("inf")


def test_loss_decreases_over_50_epochs():
    torch.manual_seed(42)
    model = TinyMLP()
    init_weights_kaiming_he(model)
    loader = _make_synthetic_loader(n=64, batch_size=32)
    config = TrainConfig(epochs=50, val_every=100, lr=1e-3, batch_size=32)
    device = torch.device("cpu")

    result = train(model, loader, None, config, device)

    history = result["epoch_history"]
    first_loss = history[0]["train_loss"]
    last_loss = history[-1]["train_loss"]
    assert last_loss < first_loss, f"Loss did not decrease: {first_loss} → {last_loss}"


def test_train_without_val_loader():
    model = TinyMLP()
    loader = _make_synthetic_loader(n=32, batch_size=16)
    config = TrainConfig(epochs=3, batch_size=16)
    device = torch.device("cpu")

    result = train(model, loader, None, config, device)

    assert result["best_val_angle_err"] == float("inf")
    assert result["final_val_metrics"] == {}


def test_validate_physics_regimes_returns_expected_keys():
    model = TinyMLP()
    loader = _make_synthetic_loader_with_meta(n=32, batch_size=16)
    device = torch.device("cpu")

    metrics = validate_physics_regimes(model, loader, device)

    expected_keys = {
        "angle_err_deg",
        "bx_err_nT",
        "by_err_nT",
        "bz_err_nT",
        "magnitude_err_nT",
        "fano_bias_nT",
        "heading_bias_deg",
    }
    assert set(metrics.keys()) == expected_keys

    for k, v in metrics.items():
        assert isinstance(v, float), f"{k} is not float"
        assert v >= 0, f"{k} is negative: {v}"
        assert torch.isfinite(torch.tensor(v)), f"{k} is not finite"
