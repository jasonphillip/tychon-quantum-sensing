"""Orbit-in-the-loop benchmark: SGP4 → IGRF-14 → nadir ADCS → payload B-vectors.

Conventions (locked to ``tychon_shared_data.orbit_in_the_loop`` ORBIT_SCHEMA):

- Quaternion is the source of truth for attitude. Scalar-first, ECI→body:
  ``v_body = q ⊗ v_eci ⊗ q*``. Components ordered ``(w, x, y, z)``.
- RPY is derived from the quaternion under ZYX intrinsic Tait-Bryan
  (yaw about Z, then pitch about new Y, then roll about new X). Radians.
- ``t`` is per-orbit relative seconds since that orbit's TLE epoch. Absolute
  UTC is recoverable via ``manifest['orbit_epochs_utc'][orbit_id] + t``.
- B-field columns are payload-frame Tesla.
"""
