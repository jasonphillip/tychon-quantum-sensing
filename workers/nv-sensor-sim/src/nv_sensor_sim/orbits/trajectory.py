"""Trajectory orchestrator: SGP4 → IGRF-14 → nadir ADCS → payload-frame B.

Emits one ``TrajectoryBatch`` per ``orbit_id``, where a ``TrajectoryBatch`` is
a ``Mapping[str, np.ndarray]`` matching exactly the 15 columns of the shipped
``tychon_shared_data.orbit_in_the_loop.ORBIT_COLUMNS`` contract.

Conventions
-----------
- ``t`` is **per-orbit relative seconds** since this batch's TLE epoch. Absolute
  UTC is recoverable via ``manifest['orbit_epochs_utc'][orbit_id] + t``.
- Quaternion is the source-of-truth attitude representation (scalar-first,
  ECI→body). RPY (roll, pitch, yaw) is **derived** from the quaternion under
  ZYX intrinsic Tait-Bryan; producers must never invert RPY back to ``q``.
- All float columns are float64; ``orbit_id`` is int32.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from .adcs import (
    ADCS_RULE_ID,
    ADCS_RULE_VERSION,
    QUATERNION_CONVENTION,
    nadir_v1,
)
from .frames import (
    ecef_to_geodetic,
    gmst_rad,
    quat_to_rpy,
)
from .igrf_field import IGRF_MODEL_VERSION, igrf_ned
from .sgp4_propagator import FRAME_NOTE, propagate_tle


# Match the shipped tychon_shared_data ORBIT_COLUMNS tuple verbatim.
TRAJECTORY_COLUMNS: tuple[str, ...] = (
    "t",
    "lat",
    "lon",
    "alt",
    "roll",
    "pitch",
    "yaw",
    "q_eb_w",
    "q_eb_x",
    "q_eb_y",
    "q_eb_z",
    "B_payload_x",
    "B_payload_y",
    "B_payload_z",
    "orbit_id",
)


@dataclass(frozen=True)
class OrbitSpec:
    """One orbit's input parameters for the benchmark."""

    orbit_id: int
    line1: str
    line2: str
    duration_s: float
    dt_s: float


def _R_eci_to_ned_array(r_eci: np.ndarray, jd_ut1: np.ndarray) -> np.ndarray:
    """Per-row ECI→NED rotation matrix.

    Parameters
    ----------
    r_eci : (N, 3) float64
    jd_ut1 : (N,) float64
    """
    n = jd_ut1.shape[0]

    # ECI → ECEF rotation per row from per-row GMST.
    thetas = np.array([gmst_rad(float(jd)) for jd in jd_ut1])
    c, s = np.cos(thetas), np.sin(thetas)
    R_eci_ecef = np.zeros((n, 3, 3), dtype=np.float64)
    R_eci_ecef[:, 0, 0] = c
    R_eci_ecef[:, 0, 1] = s
    R_eci_ecef[:, 1, 0] = -s
    R_eci_ecef[:, 1, 1] = c
    R_eci_ecef[:, 2, 2] = 1.0

    # Apply to each ECI position.
    r_ecef = np.einsum("nij,nj->ni", R_eci_ecef, r_eci)

    # ECEF → geodetic; broadcast version is built-in.
    lat, lon, _alt = ecef_to_geodetic(r_ecef)

    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    sin_lon = np.sin(lon)
    cos_lon = np.cos(lon)

    R_ecef_ned = np.zeros((n, 3, 3), dtype=np.float64)
    R_ecef_ned[:, 0, 0] = -sin_lat * cos_lon
    R_ecef_ned[:, 0, 1] = -sin_lat * sin_lon
    R_ecef_ned[:, 0, 2] = cos_lat
    R_ecef_ned[:, 1, 0] = -sin_lon
    R_ecef_ned[:, 1, 1] = cos_lon
    # row 1, col 2 is 0
    R_ecef_ned[:, 2, 0] = -cos_lat * cos_lon
    R_ecef_ned[:, 2, 1] = -cos_lat * sin_lon
    R_ecef_ned[:, 2, 2] = -sin_lat

    return np.einsum("nij,njk->nik", R_ecef_ned, R_eci_ecef)


def build_trajectory_batch(
    spec: OrbitSpec,
    igrf_date: datetime,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Propagate one orbit and assemble the 15-column batch + per-orbit meta.

    Returns
    -------
    batch : dict[str, np.ndarray]
        15 keys matching ``TRAJECTORY_COLUMNS``; 14 float64 1-D arrays of
        length ``n_samples`` plus ``orbit_id`` int32 of the same length.
    orbit_meta : dict
        Per-orbit metadata for the producer-side manifest:
        ``orbit_id``, ``tle_epoch_utc``, ``n_samples``.
    """
    propagated = propagate_tle(
        spec.line1,
        spec.line2,
        duration_s=spec.duration_s,
        dt_s=spec.dt_s,
    )
    n = propagated.t_rel_s.shape[0]

    # ECI → ECEF per-row → geodetic
    R_en = _R_eci_to_ned_array(propagated.r_eci_m, propagated.epoch_jd_ut1)
    # Recompute (lat, lon, alt) directly to populate output columns.
    thetas = np.array([gmst_rad(float(jd)) for jd in propagated.epoch_jd_ut1])
    c, s = np.cos(thetas), np.sin(thetas)
    R_eci_ecef = np.zeros((n, 3, 3), dtype=np.float64)
    R_eci_ecef[:, 0, 0] = c
    R_eci_ecef[:, 0, 1] = s
    R_eci_ecef[:, 1, 0] = -s
    R_eci_ecef[:, 1, 1] = c
    R_eci_ecef[:, 2, 2] = 1.0
    r_ecef = np.einsum("nij,nj->ni", R_eci_ecef, propagated.r_eci_m)
    lat_rad, lon_rad, alt_m = ecef_to_geodetic(r_ecef)
    lat_deg = np.rad2deg(lat_rad)
    lon_deg = np.rad2deg(lon_rad)

    # IGRF-14 in NED (single epoch covers the trajectory; secular variation is
    # negligible at sub-day scales).
    B_ned = igrf_ned(lat_deg, lon_deg, alt_m, igrf_date)  # (N, 3) Tesla

    # nadir_v1 quaternion per row (ECI → body).
    q_eb = nadir_v1(propagated.r_eci_m, propagated.v_eci_mps)  # (N, 4)
    rpy = np.asarray(quat_to_rpy(q_eb))  # (N, 3) → (roll, pitch, yaw)

    # Build R_eci_to_body from quaternion via the same scipy path used in
    # frames; ``v_body = R_eb @ v_eci``.
    from .frames import quat_to_R  # local import to avoid mutual reference

    R_eb = quat_to_R(q_eb)  # (N, 3, 3)

    # B_payload = R_eb @ R_en^T @ B_ned
    B_eci = np.einsum("nij,nj->ni", R_en.transpose(0, 2, 1), B_ned)
    B_payload = np.einsum("nij,nj->ni", R_eb, B_eci)

    batch: dict[str, np.ndarray] = {
        "t": np.ascontiguousarray(propagated.t_rel_s, dtype=np.float64),
        "lat": np.ascontiguousarray(lat_deg, dtype=np.float64),
        "lon": np.ascontiguousarray(lon_deg, dtype=np.float64),
        "alt": np.ascontiguousarray(alt_m, dtype=np.float64),
        "roll": np.ascontiguousarray(rpy[:, 0], dtype=np.float64),
        "pitch": np.ascontiguousarray(rpy[:, 1], dtype=np.float64),
        "yaw": np.ascontiguousarray(rpy[:, 2], dtype=np.float64),
        "q_eb_w": np.ascontiguousarray(q_eb[:, 0], dtype=np.float64),
        "q_eb_x": np.ascontiguousarray(q_eb[:, 1], dtype=np.float64),
        "q_eb_y": np.ascontiguousarray(q_eb[:, 2], dtype=np.float64),
        "q_eb_z": np.ascontiguousarray(q_eb[:, 3], dtype=np.float64),
        "B_payload_x": np.ascontiguousarray(B_payload[:, 0], dtype=np.float64),
        "B_payload_y": np.ascontiguousarray(B_payload[:, 1], dtype=np.float64),
        "B_payload_z": np.ascontiguousarray(B_payload[:, 2], dtype=np.float64),
        "orbit_id": np.full(n, spec.orbit_id, dtype=np.int32),
    }

    orbit_meta = {
        "orbit_id": int(spec.orbit_id),
        "tle_epoch_utc": propagated.epoch_utc.isoformat(timespec="seconds"),
        "n_samples": n,
    }
    return batch, orbit_meta


__all__ = [
    "ADCS_RULE_ID",
    "ADCS_RULE_VERSION",
    "FRAME_NOTE",
    "IGRF_MODEL_VERSION",
    "OrbitSpec",
    "QUATERNION_CONVENTION",
    "TRAJECTORY_COLUMNS",
    "build_trajectory_batch",
]
