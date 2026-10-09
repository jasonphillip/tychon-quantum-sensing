"""Reference-frame and attitude utilities for the orbit benchmark.

Conventions
-----------
- **Quaternion** is the source-of-truth attitude representation. Scalar-first
  ``q = (w, x, y, z)`` with ECI→body active rotation: ``v_body = q ⊗ v_eci ⊗ q*``.
- **Euler angles** are ZYX intrinsic Tait-Bryan (yaw about Z, then pitch about
  new Y, then roll about new X). All angles in radians. Singular at
  ``pitch = ±π/2``; producers must avoid those poses.
- **Frames**: ECI ≡ TEME (TEME ≈ ECI to arcsec for LEO ADCS purposes; the
  approximation is documented and propagated downstream via the manifest).
  ECEF rotates from ECI by Greenwich Mean Sidereal Time about Z.
  Local ENU at (lat, lon) is the standard tangent plane on the WGS-84 ellipsoid.
- **Units**: angles in radians, distances in meters unless explicitly noted.

scipy convention bridge: ``scipy.spatial.transform.Rotation`` uses scalar-LAST
quaternions ``(x, y, z, w)``. The helpers below translate to scalar-first.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


# WGS-84 constants
_WGS84_A = 6378137.0          # semi-major axis [m]
_WGS84_F = 1.0 / 298.257223563  # flattening
_WGS84_E2 = _WGS84_F * (2.0 - _WGS84_F)  # first eccentricity squared


# ----------------------------------------------------------------------------
# Quaternion ↔ rotation matrix ↔ RPY helpers (scalar-first, ECI→body)
# ----------------------------------------------------------------------------

def _scalar_first_to_scipy(q: np.ndarray) -> np.ndarray:
    """Translate (w, x, y, z) → scipy's (x, y, z, w)."""
    q = np.asarray(q, dtype=np.float64)
    return np.stack([q[..., 1], q[..., 2], q[..., 3], q[..., 0]], axis=-1)


def _scipy_to_scalar_first(q_xyzw: np.ndarray) -> np.ndarray:
    """Translate scipy's (x, y, z, w) → (w, x, y, z)."""
    q = np.asarray(q_xyzw, dtype=np.float64)
    return np.stack([q[..., 3], q[..., 0], q[..., 1], q[..., 2]], axis=-1)


def quat_to_R(q: np.ndarray) -> np.ndarray:
    """Convert scalar-first quaternion (w, x, y, z) → 3×3 rotation matrix.

    The returned matrix R satisfies ``v_body = R @ v_eci``.
    """
    return Rotation.from_quat(_scalar_first_to_scipy(q)).as_matrix()


def R_to_quat(R: np.ndarray) -> np.ndarray:
    """Convert 3×3 rotation matrix → scalar-first quaternion (w, x, y, z).

    Returned quaternion has unit norm and uses the ``w >= 0`` hemisphere
    convention so that small rotations stay near identity ``(1, 0, 0, 0)``.
    """
    q_xyzw = Rotation.from_matrix(np.asarray(R, dtype=np.float64)).as_quat()
    q = _scipy_to_scalar_first(q_xyzw)
    # Hemisphere fix: enforce non-negative scalar component.
    if q.ndim == 1:
        if q[0] < 0:
            q = -q
    else:
        flip = q[..., 0] < 0
        q[flip] = -q[flip]
    return q


def quat_to_rpy(q: np.ndarray) -> tuple[float, float, float] | np.ndarray:
    """Convert scalar-first quaternion → (roll, pitch, yaw) under ZYX intrinsic.

    For a single quaternion returns a tuple; for batched input returns an
    ``(N, 3)`` array of ``(roll, pitch, yaw)`` rows.
    """
    rot = Rotation.from_quat(_scalar_first_to_scipy(q))
    # scipy 'ZYX' intrinsic returns angles in ZYX order: [yaw, pitch, roll]
    angles = rot.as_euler("ZYX")
    if angles.ndim == 1:
        yaw, pitch, roll = float(angles[0]), float(angles[1]), float(angles[2])
        return roll, pitch, yaw
    return np.stack([angles[..., 2], angles[..., 1], angles[..., 0]], axis=-1)


def rpy_to_quat(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Convert (roll, pitch, yaw) under ZYX intrinsic → scalar-first quaternion.

    Inputs are radians. Returns a unit quaternion ``(w, x, y, z)`` in the
    ``w >= 0`` hemisphere.
    """
    rot = Rotation.from_euler("ZYX", [yaw, pitch, roll])
    q = _scipy_to_scalar_first(rot.as_quat())
    if q[0] < 0:
        q = -q
    return q


# ----------------------------------------------------------------------------
# Earth-frame transforms
# ----------------------------------------------------------------------------

def gmst_rad(jd_ut1: float) -> float:
    """Greenwich Mean Sidereal Time (radians) from UT1 Julian date.

    IAU 1982 polynomial; sufficient for ~1 arcsec accuracy over decades, far
    below the ADEV signal scales relevant to this benchmark.
    """
    t = (jd_ut1 - 2451545.0) / 36525.0
    gmst_sec = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t * t * t
    )
    gmst_sec = gmst_sec % 86400.0
    return (gmst_sec / 86400.0) * 2.0 * np.pi


def eci_to_ecef(r_eci: np.ndarray, jd_ut1: float) -> np.ndarray:
    """Rotate ECI/TEME → ECEF by GMST about z. ``r_eci`` shape (..., 3)."""
    theta = gmst_rad(jd_ut1)
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    return r_eci @ R.T


def ecef_to_eci(r_ecef: np.ndarray, jd_ut1: float) -> np.ndarray:
    theta = gmst_rad(jd_ut1)
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return r_ecef @ R.T


def ecef_to_geodetic(r_ecef: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ECEF (m) → (lat, lon, alt) on WGS-84. lat/lon in radians, alt in meters.

    Bowring's closed-form approximation with one Newton iteration; accuracy
    well under 1 m for altitudes 0–2000 km.
    """
    r = np.asarray(r_ecef, dtype=np.float64)
    x, y, z = r[..., 0], r[..., 1], r[..., 2]
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    a = _WGS84_A
    e2 = _WGS84_E2
    b = a * np.sqrt(1.0 - e2)
    ep2 = (a * a - b * b) / (b * b)
    theta = np.arctan2(z * a, p * b)
    sin_t, cos_t = np.sin(theta), np.cos(theta)
    lat = np.arctan2(z + ep2 * b * sin_t**3, p - e2 * a * cos_t**3)
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    N = a / np.sqrt(1.0 - e2 * sin_lat * sin_lat)
    # Use whichever form is numerically dominant: away from the poles
    # ``p / cos_lat - N`` is well-conditioned; near the poles
    # ``z / sin_lat - N (1 - e²)`` is.
    use_polar = np.abs(sin_lat) > np.abs(cos_lat)
    alt_polar = z / np.where(sin_lat == 0.0, 1.0, sin_lat) - N * (1.0 - e2)
    alt_equator = p / np.where(cos_lat == 0.0, 1.0, cos_lat) - N
    alt = np.where(use_polar, alt_polar, alt_equator)
    return lat, lon, alt


def ned_to_payload(b_ned: np.ndarray, R_eci_to_body: np.ndarray, R_eci_to_ned: np.ndarray) -> np.ndarray:
    """Rotate a NED vector → body/payload frame.

    ``v_body = R_eb @ R_en.T @ v_ned``. Per-row arrays accepted.
    """
    R_nb = R_eci_to_body @ R_eci_to_ned.transpose(0, 2, 1) if R_eci_to_body.ndim == 3 else R_eci_to_body @ R_eci_to_ned.T
    if b_ned.ndim == 1:
        return R_nb @ b_ned
    return np.einsum("nij,nj->ni", R_nb, b_ned)


def R_eci_to_ned(r_eci: np.ndarray, jd_ut1: float) -> np.ndarray:
    """Build the rotation that maps an ECI vector at this position into local NED.

    Single position: returns (3, 3). Batched: returns (N, 3, 3).
    """
    r_ecef = eci_to_ecef(r_eci, jd_ut1)
    lat, lon, _ = ecef_to_geodetic(r_ecef)
    sin_lat, cos_lat = np.sin(lat), np.cos(lat)
    sin_lon, cos_lon = np.sin(lon), np.cos(lon)
    # ECEF→NED rotation at (lat, lon)
    R_ecef_to_ned = np.stack(
        [
            np.stack([-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat], axis=-1),
            np.stack([-sin_lon, cos_lon, np.zeros_like(sin_lon)], axis=-1),
            np.stack([-cos_lat * cos_lon, -cos_lat * sin_lon, -sin_lat], axis=-1),
        ],
        axis=-2,
    )
    # Compose: ECI → ECEF → NED
    theta = gmst_rad(jd_ut1)
    c, s = np.cos(theta), np.sin(theta)
    R_eci_to_ecef = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    if R_ecef_to_ned.ndim == 3:
        return np.einsum("nij,jk->nik", R_ecef_to_ned, R_eci_to_ecef)
    return R_ecef_to_ned @ R_eci_to_ecef


__all__ = [
    "quat_to_R",
    "R_to_quat",
    "quat_to_rpy",
    "rpy_to_quat",
    "gmst_rad",
    "eci_to_ecef",
    "ecef_to_eci",
    "ecef_to_geodetic",
    "R_eci_to_ned",
    "ned_to_payload",
]
