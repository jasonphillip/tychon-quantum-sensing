"""Vector readout: vendored NV geometry + physics constants and BLUE inversion.

- ``geometry`` — fixed crystal/physics constants (``NV_AXES_UNIT``, ``nv_geometry_matrix``,
  gyromagnetic ratio, zero-field splitting, ``compute_linewidth``), vendored from
  ``nv_sensor_sim`` with a parity test (TODO: import once the dependency is wired).
- ``blue`` — Best Linear Unbiased Estimator from per-resonance shifts to a 3D lab-frame
  vector + covariance.
"""

from odmr_vector_tracking.vector.blue import (
    BluePosteriorVariance,
    blue_invert_field,
    blue_project,
)
from odmr_vector_tracking.vector.geometry import (
    DD_DT_HZ_PER_K,
    GAMMA_E_HZ_PER_T,
    LINE_AXIS_8,
    LINE_SIGN_8,
    LINE_TRANSITION_8,
    N_AXES,
    N_LINES_ELECTRONIC,
    NV_AXES_UNIT,
    ZFS_D_HZ,
    axis_projections_from_resonances,
    common_mode_shift,
    compute_linewidth,
    nv_geometry_matrix,
    project_field_onto_axes,
    resonance_frequencies,
    resonance_frequencies_diagonalized,
)

__all__ = [
    "BluePosteriorVariance",
    "blue_invert_field",
    "blue_project",
    "DD_DT_HZ_PER_K",
    "GAMMA_E_HZ_PER_T",
    "LINE_AXIS_8",
    "LINE_SIGN_8",
    "LINE_TRANSITION_8",
    "N_AXES",
    "N_LINES_ELECTRONIC",
    "NV_AXES_UNIT",
    "ZFS_D_HZ",
    "axis_projections_from_resonances",
    "common_mode_shift",
    "compute_linewidth",
    "nv_geometry_matrix",
    "project_field_onto_axes",
    "resonance_frequencies",
    "resonance_frequencies_diagonalized",
]
