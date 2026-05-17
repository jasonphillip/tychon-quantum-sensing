"""Vector-readout module.

Currently exposes the BLUE projection that turns 8 per-resonance scalar
ΔB residuals into one lab-frame 3D B-field vector. The 8-FCNN training
scaffold and per-axis vector-residual evals will land here as the
`production_50k_v3_vector` dataset becomes available.
"""

from odmr_edge_ml.vector.blue_projection import (
    BluePosteriorVariance,
    blue_project,
    nv_axis_geometry_matrix,
)

__all__ = [
    "BluePosteriorVariance",
    "blue_project",
    "nv_axis_geometry_matrix",
]
