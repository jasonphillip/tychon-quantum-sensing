"""Small synthetic run checks exported validation measurements."""

import numpy as np
import pytest
import torch

from odmr_edge_ml.cascade.train_stage import (
    _ResidualTensorDataset,
    _collate,
    _validate_scalar,
    train_stage,
)
from odmr_edge_ml.models.fcnn_v2 import OdmrFCNNv2
from odmr_edge_ml.training.qat import prepare_model_qat
from torch.utils.data import DataLoader


def test_stage_reports_export_mae_and_matches_reloaded_checkpoint(tmp_path):
    pytest.importorskip("tensorflow")
    rng = np.random.default_rng(4)
    input_dim = 40
    train_x = rng.uniform(-1, 1, (64, input_dim)).astype(np.float32)
    val_x = rng.uniform(-1, 1, (32, input_dim)).astype(np.float32)
    train_bins = rng.integers(4, input_dim - 4, 64).astype(np.float32)
    val_bins = rng.integers(4, input_dim - 4, 32).astype(np.float32)
    train_y = rng.uniform(400, 600, 64).astype(np.float32)
    val_y = rng.uniform(400, 600, 32).astype(np.float32)

    result = train_stage(
        name="tiny", train_spectra_norm=train_x, train_lock_bins=train_bins,
        train_labels_uT=train_y, val_spectra_norm=val_x,
        val_lock_bins=val_bins, val_labels_uT=val_y,
        output_dir=tmp_path, device=torch.device("cpu"), input_dim=input_dim,
        epochs=1, batch_size=32, use_compile=False, num_workers=0,
    )
    assert set(result.export_val_mae_uT) == {"float", "int8"}
    assert all(np.isfinite(value) for value in result.export_val_mae_uT.values())

    checkpoint = torch.load(tmp_path / "checkpoints/best_model.pt", map_location="cpu",
                            weights_only=True)
    reloaded = prepare_model_qat(
        OdmrFCNNv2(input_dim=input_dim, output_dim=1),
        example_input=torch.randn(1, input_dim + 1),
    )
    reloaded.load_state_dict(checkpoint["model_state_dict"])
    combined = np.concatenate([val_x, val_bins[:, None]], axis=1)
    dataset = _ResidualTensorDataset(
        torch.from_numpy(combined), torch.from_numpy(val_y[:, None]),
    )
    loader = DataLoader(dataset, batch_size=32, collate_fn=_collate, num_workers=0)
    checkpoint_mae = _validate_scalar(reloaded, loader, torch.device("cpu"))["mae_uT"]
    assert result.export_val_mae_uT["float"] == pytest.approx(checkpoint_mae, rel=1e-3)
