"""Regression tests for the shared Bz target convention."""

import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from odmr_edge_ml.data.targets import canonical_vector_target
from odmr_edge_ml.training.loop import TrainConfig, fold_bz_sign, train


class FixedPrediction(nn.Module):
    def __init__(self, target: torch.Tensor):
        super().__init__()
        self.prediction = nn.Parameter(target.clone())

    def forward(self, spectra: torch.Tensor) -> torch.Tensor:
        return self.prediction.expand(spectra.shape[0], -1)


class CaptureTarget(nn.Module):
    def __init__(self):
        super().__init__()
        self.target = None

    def forward(self, pred: torch.Tensor, true: torch.Tensor) -> dict:
        self.target = true.detach().clone()
        zero = pred.sum() * 0.0
        return {"loss": zero, "angular": zero, "huber": zero}


def _original_fold_bz_sign(b_field: torch.Tensor) -> torch.Tensor:
    """The pre-A6 implementation, retained as a scalar-path byte baseline."""
    if b_field.shape[1] < 3:
        return b_field
    neg_mask = b_field[:, 2] < 0
    if neg_mask.any():
        b_field = b_field.clone()
        b_field[neg_mask] *= -1.0
    return b_field


def _run_one_step(target, prediction, fold_sign, tmp_path, val=True):
    loader = DataLoader(
        [{"spectra": torch.tensor([0.0]), "b_field_uT": target[0]}],
        batch_size=1,
    )
    criterion = CaptureTarget()
    result = train(
        FixedPrediction(prediction[0]),
        loader,
        loader if val else None,
        TrainConfig(
            epochs=1, val_every=1, lr=0.0, fold_sign=fold_sign,
            checkpoint_dir=str(tmp_path),
        ),
        torch.device("cpu"),
        criterion=criterion,
        val_fn="default" if val else None,
    )
    return criterion.target, result


@pytest.mark.parametrize("fold_sign", [True, False])
def test_training_and_validation_use_one_vector_target(fold_sign, tmp_path):
    raw = torch.tensor([[3.0, 4.0, -12.0]])
    expected = torch.tensor([[-3.0, -4.0, 12.0]]) if fold_sign else raw
    assert torch.equal(canonical_vector_target(raw, fold_sign), expected)
    assert torch.equal(fold_bz_sign(raw), torch.tensor([[-3.0, -4.0, 12.0]]))

    trained_target, result = _run_one_step(raw, expected, fold_sign, tmp_path)
    assert torch.equal(trained_target, expected)
    metrics = result["final_val_metrics"]
    assert metrics["angle_err_deg"] < 0.05
    assert metrics["bx_err_nT"] == 0.0
    assert metrics["by_err_nT"] == 0.0
    assert metrics["bz_err_nT"] == 0.0


@pytest.mark.parametrize("fold_sign", [True, False])
def test_scalar_training_target_matches_original_bytes(fold_sign, tmp_path):
    raw = torch.tensor([[-7.25]], dtype=torch.float32)
    original = _original_fold_bz_sign(raw)
    expected_bytes = original.numpy().tobytes()
    assert fold_bz_sign(raw).numpy().tobytes() == expected_bytes
    assert canonical_vector_target(raw, fold_sign).numpy().tobytes() == expected_bytes

    trained_target, _ = _run_one_step(raw, raw, fold_sign, tmp_path, val=False)
    assert trained_target.numpy().tobytes() == expected_bytes
