"""Training module: losses, training loop, QAT, and physics-stratified validation."""

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
from tychon_odmr_ml.training.qat import (
    extract_clean_state_dict,
    load_clean_weights,
    make_int8_symmetric_qconfig,
    prepare_model_qat,
)

__all__ = [
    "CompositeAngularHuberLoss",
    "angular_error_deg",
    "component_error_nT",
    "TrainConfig",
    "init_weights_kaiming_he",
    "train",
    "validate_physics_regimes",
    "extract_clean_state_dict",
    "load_clean_weights",
    "make_int8_symmetric_qconfig",
    "prepare_model_qat",
]
