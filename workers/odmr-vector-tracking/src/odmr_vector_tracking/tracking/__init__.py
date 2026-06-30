"""Trackers.

- ``classical`` — lock-in + per-line PID with nearest-peak association (the Γ/2-limited
  baseline that loses lock at inter-axis crossings). The bar the learned tracker must beat.
- ``learned`` — physics-informed recurrent tracker SKELETON with an explicit V250/MSS execution
  partition: a V250-targeted feedforward feature extractor + host-side recurrent core,
  data-association head, and fixed BLUE decode. Deployable-first and research variants of the
  core/association share one interface. APIs/shapes only — no training yet.
"""

from odmr_vector_tracking.tracking.classical import (
    ClassicalTracker,
    ClassicalTrackResult,
)
from odmr_vector_tracking.tracking.learned import (
    AssociationHead,
    AttentionAssociation,
    ExecutionTarget,
    FrameFeatureExtractor,
    GatedKalmanNetCore,
    GeometryDecoder,
    LearnedTracker,
    LearnedTrackerConfig,
    LearnedTrackerOutput,
    LinearScoreAssociation,
    RecurrentCore,
    ReLURecurrentCell,
    build_tracker,
    v250_targeted_modules,
)

__all__ = [
    "ClassicalTracker",
    "ClassicalTrackResult",
    "AssociationHead",
    "AttentionAssociation",
    "ExecutionTarget",
    "FrameFeatureExtractor",
    "GatedKalmanNetCore",
    "GeometryDecoder",
    "LearnedTracker",
    "LearnedTrackerConfig",
    "LearnedTrackerOutput",
    "LinearScoreAssociation",
    "RecurrentCore",
    "ReLURecurrentCell",
    "build_tracker",
    "v250_targeted_modules",
]
