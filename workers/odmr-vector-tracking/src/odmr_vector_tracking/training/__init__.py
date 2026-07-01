"""Training harness for the learned through-crossing tracker (Increment 2).

- :mod:`~odmr_vector_tracking.training.targets` — supervision targets from v1-contract arrays.
- :mod:`~odmr_vector_tracking.training.losses` — association CE / position Huber / projection MSE.
- :mod:`~odmr_vector_tracking.training.loop` — full-BPTT loop, early stopping, checkpointing.
"""

from odmr_vector_tracking.training.loop import (
    SplitTensors,
    TrainResult,
    TrainSettings,
    anchor_assoc_accuracy,
    build_split_tensors,
    set_seed,
    train,
)
from odmr_vector_tracking.training.losses import (
    association_loss,
    compute_losses,
    position_loss,
    projection_loss,
)
from odmr_vector_tracking.training.targets import (
    association_targets,
    normalize_freqs,
    projection_labels,
)

__all__ = [
    "SplitTensors",
    "TrainResult",
    "TrainSettings",
    "anchor_assoc_accuracy",
    "association_loss",
    "association_targets",
    "build_split_tensors",
    "compute_losses",
    "normalize_freqs",
    "position_loss",
    "projection_labels",
    "projection_loss",
    "set_seed",
    "train",
]
