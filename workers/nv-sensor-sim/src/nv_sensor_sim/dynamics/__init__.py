"""Time-series ("dynamic") ODMR generation.

A field trajectory B(t) (static bias + swept external field) is rendered into a
per-frame multi-axis ODMR time-series with ground-truth resonance positions,
per-line axis/transition identity, and collision labels — the data a vector
tracker needs to hold per-axis identity through inter-axis crossings.

Physics is reused from ``physics/`` (lineshape, hamiltonian, parameters) and the
SimOS adapter; this package adds only the time axis, association, and labelling.
"""

from __future__ import annotations

from nv_sensor_sim.dynamics.field_trajectory import (
    orbit_trajectory,
    ramp_crossing_trajectory,
    static_bias_vector,
)
from nv_sensor_sim.dynamics.render import render_multi_axis_frame, render_sequence
from nv_sensor_sim.dynamics.resonances import (
    GAMMA_HZ_PER_T,
    analytic_centers,
    associate_axis_centers,
    axis_transition_labels,
    collision_labels,
    reference_zfs_hz,
)

__all__ = [
    "GAMMA_HZ_PER_T",
    "analytic_centers",
    "associate_axis_centers",
    "axis_transition_labels",
    "collision_labels",
    "orbit_trajectory",
    "ramp_crossing_trajectory",
    "reference_zfs_hz",
    "render_multi_axis_frame",
    "render_sequence",
    "static_bias_vector",
]
