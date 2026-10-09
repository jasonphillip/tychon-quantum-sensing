"""Tests for physics-informed composite loss functions."""

import torch

from odmr_edge_ml.training.losses import (
    CompositeAngularHuberLoss,
    angular_error_deg,
    component_error_nT,
)


# --- CompositeAngularHuberLoss ---


def test_perfect_prediction_gives_near_zero_loss():
    criterion = CompositeAngularHuberLoss()
    b = torch.tensor([[0.0, 0.0, 10000.0], [0.0, 0.0, 5000.0]])
    result = criterion(b, b)
    assert result["loss"].item() < 1e-6
    assert result["angular"].item() < 1e-6
    assert result["huber"].item() < 1e-6


def test_orthogonal_vectors_angular_loss_near_one():
    criterion = CompositeAngularHuberLoss(alpha=1.0)
    pred = torch.tensor([[1.0, 0.0, 0.0]])
    true = torch.tensor([[0.0, 1.0, 0.0]])
    result = criterion(pred, true)
    assert abs(result["angular"].item() - 1.0) < 0.01


def test_antiparallel_vectors_angular_loss_near_two():
    criterion = CompositeAngularHuberLoss(alpha=1.0)
    pred = torch.tensor([[0.0, 0.0, 1.0]])
    true = torch.tensor([[0.0, 0.0, -1.0]])
    result = criterion(pred, true)
    assert abs(result["angular"].item() - 2.0) < 0.01


def test_scaled_parallel_gives_near_zero_angular():
    criterion = CompositeAngularHuberLoss(alpha=1.0)
    pred = torch.tensor([[0.0, 0.0, 100.0]])
    true = torch.tensor([[0.0, 0.0, 10000.0]])
    result = criterion(pred, true)
    assert result["angular"].item() < 1e-5


def test_loss_is_differentiable():
    criterion = CompositeAngularHuberLoss()
    pred = torch.randn(8, 3, requires_grad=True)
    true = torch.randn(8, 3)
    result = criterion(pred, true)
    result["loss"].backward()
    assert pred.grad is not None
    assert torch.isfinite(pred.grad).all()


def test_huber_bounds_gradients_on_outliers():
    criterion = CompositeAngularHuberLoss(alpha=0.0, huber_delta=1.0)
    pred = torch.tensor([[1500.0, 0.0, 0.0]], requires_grad=True)
    true = torch.tensor([[0.0, 0.0, 0.0]])
    result = criterion(pred, true)
    result["loss"].backward()
    # Huber gradient saturates at delta for large residuals
    assert pred.grad is not None
    assert pred.grad.abs().max().item() < 2.0


def test_alpha_one_gives_pure_angular():
    criterion = CompositeAngularHuberLoss(alpha=1.0)
    pred = torch.tensor([[1.0, 0.0, 0.0]])
    true = torch.tensor([[0.0, 1.0, 0.0]])
    result = criterion(pred, true)
    assert abs(result["loss"].item() - result["angular"].item()) < 1e-6


def test_various_batch_sizes():
    criterion = CompositeAngularHuberLoss()
    for bs in [1, 4, 16, 64]:
        pred = torch.randn(bs, 3)
        true = torch.randn(bs, 3)
        result = criterion(pred, true)
        assert torch.isfinite(result["loss"])


# --- angular_error_deg ---


def test_angular_error_identical_near_zero():
    b = torch.tensor([[0.0, 0.0, 10000.0]])
    err = angular_error_deg(b, b)
    assert err.item() < 0.01


def test_angular_error_orthogonal_near_90():
    pred = torch.tensor([[1.0, 0.0, 0.0]])
    true = torch.tensor([[0.0, 1.0, 0.0]])
    err = angular_error_deg(pred, true)
    assert abs(err.item() - 90.0) < 0.1


def test_angular_error_antiparallel_near_180():
    pred = torch.tensor([[0.0, 0.0, 1.0]])
    true = torch.tensor([[0.0, 0.0, -1.0]])
    err = angular_error_deg(pred, true)
    assert abs(err.item() - 180.0) < 0.1


# --- component_error_nT ---


def test_component_error_known_difference():
    pred = torch.tensor([[0.0, 0.0, 10.001]])  # 10.001 µT
    true = torch.tensor([[0.0, 0.0, 10.000]])  # 10.000 µT
    err = component_error_nT(pred, true)
    # 0.001 µT = 1 nT
    assert abs(err[0, 2].item() - 1.0) < 0.1
    assert err[0, 0].item() < 0.01
    assert err[0, 1].item() < 0.01
