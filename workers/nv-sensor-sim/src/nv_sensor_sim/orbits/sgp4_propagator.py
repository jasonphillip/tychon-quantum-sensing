"""SGP4 propagator wrapper for the orbit benchmark.

Thin layer over the ``sgp4`` package's ``Satrec`` API that takes a TLE pair
plus a regular UT1 sample grid and returns ECI/TEME position and velocity
arrays in SI units, alongside the TLE epoch as a Julian date.

TEME ≈ ECI to within an arcsec for the purposes of LEO ADCS pointing rules
on the time scales this benchmark exercises; the approximation is
documented in the manifest (``sgp4.frame_note``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

try:
    from sgp4 import __version__ as SGP4_VERSION  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - exercised by ``pytest.importorskip``
    SGP4_VERSION = "unknown"

# ECI frame note carried into the manifest; keep it as a single source of truth.
FRAME_NOTE = (
    "ECI here is the SGP4 TEME output frame. TEME ≈ J2000 to ~arcsec; "
    "sufficient for LEO ADCS pointing rules at this benchmark's accuracy "
    "scale, insufficient for absolute astrometry."
)


@dataclass(frozen=True)
class PropagatedOrbit:
    """SGP4 output for a single TLE on a regular UT1 grid.

    Attributes
    ----------
    t_rel_s : np.ndarray
        Per-sample seconds since the TLE epoch (1-D, monotonic, float64).
    r_eci_m : np.ndarray
        ECI/TEME position vectors (N, 3) in meters.
    v_eci_mps : np.ndarray
        ECI/TEME velocity vectors (N, 3) in meters per second.
    epoch_utc : datetime
        TLE epoch as an aware UTC datetime.
    epoch_jd_ut1 : np.ndarray
        Per-sample UT1 Julian date (float64, broadcast for use with
        ``frames.gmst_rad`` / ``frames.eci_to_ecef``).
    """

    t_rel_s: np.ndarray
    r_eci_m: np.ndarray
    v_eci_mps: np.ndarray
    epoch_utc: datetime
    epoch_jd_ut1: np.ndarray


def propagate_tle(
    line1: str,
    line2: str,
    duration_s: float,
    dt_s: float,
) -> PropagatedOrbit:
    """Propagate a TLE pair on a regular grid.

    Parameters
    ----------
    line1, line2 : str
        TLE lines exactly as published; the SGP4 library handles checksum
        validation and gravity-constant selection (defaults to WGS-72).
    duration_s : float
        Trajectory length in seconds, starting at the TLE epoch.
    dt_s : float
        Sample cadence in seconds. Must divide ``duration_s`` evenly.

    Returns
    -------
    PropagatedOrbit
        Position/velocity arrays plus epoch metadata.
    """
    from sgp4.api import Satrec, jday  # local import; optional dependency

    sat = Satrec.twoline2rv(line1, line2)

    # Convert SGP4's epoch (jdsatepoch + jdsatepochF) back to a datetime so
    # we can attach absolute UTC to the trajectory.
    epoch_jd = sat.jdsatepoch + sat.jdsatepochF
    epoch_unix = (epoch_jd - 2440587.5) * 86400.0
    epoch_utc = datetime.fromtimestamp(epoch_unix, tz=timezone.utc)

    n_samples = int(round(duration_s / dt_s)) + 1
    t_rel = np.arange(n_samples, dtype=np.float64) * dt_s

    r_eci = np.empty((n_samples, 3), dtype=np.float64)
    v_eci = np.empty((n_samples, 3), dtype=np.float64)
    jd_ut1 = np.empty(n_samples, dtype=np.float64)

    for i, ts in enumerate(t_rel):
        sample_dt = epoch_utc + timedelta(seconds=float(ts))
        jd_full, fr = jday(
            sample_dt.year,
            sample_dt.month,
            sample_dt.day,
            sample_dt.hour,
            sample_dt.minute,
            sample_dt.second + sample_dt.microsecond * 1e-6,
        )
        err, r_km, v_kmps = sat.sgp4(jd_full, fr)
        if err != 0:
            raise RuntimeError(
                f"sgp4 propagation error code {err} at t={ts:.3f} s "
                "(see sgp4 documentation for code meanings)"
            )
        r_eci[i] = r_km
        v_eci[i] = v_kmps
        jd_ut1[i] = jd_full + fr

    # km → m, km/s → m/s
    r_eci *= 1000.0
    v_eci *= 1000.0

    return PropagatedOrbit(
        t_rel_s=t_rel,
        r_eci_m=r_eci,
        v_eci_mps=v_eci,
        epoch_utc=epoch_utc,
        epoch_jd_ut1=jd_ut1,
    )


__all__ = ["PropagatedOrbit", "propagate_tle", "FRAME_NOTE", "SGP4_VERSION"]
