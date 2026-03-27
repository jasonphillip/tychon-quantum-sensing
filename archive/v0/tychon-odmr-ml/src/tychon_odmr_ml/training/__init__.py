"""Training module: losses, training loop, and physics-stratified validation."""

from tychon_odmr_ml.training.losses import (
    CompositeAngularHuberLoss,
    angular_error_deg,
    component_error_nT,
)
from tychon_odmr_ml.training.loop import (
    TrainConfig,
    init_weights_kaiming_he,
    train,
    validate_physics_regimes,
)

__all__ = [
    "CompositeAngularHuberLoss",
    "angular_error_deg",
    "component_error_nT",
    "TrainConfig",
    "init_weights_kaiming_he",
    "train",
    "validate_physics_regimes",
]
