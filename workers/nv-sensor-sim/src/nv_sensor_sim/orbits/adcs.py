"""ADCS pointing rules.

Each rule is a pure function that, given an ECI position and velocity,
returns a scalar-first ``(w, x, y, z)`` quaternion ``q_eci_to_body`` such
that ``v_body = q ⊗ v_eci ⊗ q*``. The quaternion is the source of truth;
RPY columns in the parquet schema are derived from it via
``frames.quat_to_rpy``.

``nadir_v1`` is the LVLH-aligned nadir-pointing rule:

- payload **+Z** aligned with **-r̂** (toward Earth's center)
- payload **+X** in the orbital plane, in the direction of velocity
- payload **+Y** completes the right-handed frame (anti-orbit-normal)

For a circular equatorial prograde orbit:

- ``+X_body`` ≡ ``+v̂_eci``
- ``-Z_body`` ≡ ``+r̂_eci``
- ``+Y_body`` ≡ ``-ĥ_eci``  (where h = r × v)
"""

from __future__ import annotations

import numpy as np

from .frames import R_to_quat


ADCS_RULE_VERSION = "nadir_v1"
ADCS_RULE_ID = "nadir"
QUATERNION_CONVENTION = "scalar_first_eci_to_body"


def nadir_v1(r_eci: np.ndarray, v_eci: np.ndarray) -> np.ndarray:
    """Build the ECI→body quaternion for an LVLH-aligned nadir-pointing payload.

    Parameters
    ----------
    r_eci : np.ndarray
        Spacecraft position in ECI (meters). Shape ``(3,)`` or ``(N, 3)``.
    v_eci : np.ndarray
        Spacecraft velocity in ECI (m/s). Same shape as ``r_eci``.

    Returns
    -------
    np.ndarray
        Scalar-first quaternion ``(w, x, y, z)`` of shape ``(4,)`` or
        ``(N, 4)`` matching the input batch shape.
    """
    r = np.asarray(r_eci, dtype=np.float64)
    v = np.asarray(v_eci, dtype=np.float64)
    if r.shape != v.shape:
        raise ValueError(f"r_eci shape {r.shape} != v_eci shape {v.shape}")
    single = r.ndim == 1
    if single:
        r = r[None, :]
        v = v[None, :]

    r_norm = np.linalg.norm(r, axis=-1, keepdims=True)
    if np.any(r_norm == 0.0):
        raise ValueError("r_eci has zero magnitude; cannot build nadir frame")
    r_hat = r / r_norm

    # Detect radial trajectories early for a clean error.
    h_norm = np.linalg.norm(np.cross(r, v), axis=-1, keepdims=True)
    if np.any(h_norm == 0.0):
        raise ValueError("r × v is zero (radial trajectory); nadir frame undefined")

    z_b = -r_hat
    # x_body: velocity projected into the local horizontal plane (perpendicular
    # to r̂), normalized. For a circular orbit v ⊥ r so this == v̂.
    v_horiz = v - np.sum(v * r_hat, axis=-1, keepdims=True) * r_hat
    x_b = v_horiz / np.linalg.norm(v_horiz, axis=-1, keepdims=True)
    y_b = np.cross(z_b, x_b)

    # R_eb has body unit vectors as rows expressed in ECI:
    # ``v_body = R_eb @ v_eci``.
    R_eb = np.stack([x_b, y_b, z_b], axis=-2)  # shape (N, 3, 3)

    q = R_to_quat(R_eb)
    return q[0] if single else q


__all__ = [
    "ADCS_RULE_VERSION",
    "ADCS_RULE_ID",
    "QUATERNION_CONVENTION",
    "nadir_v1",
]
