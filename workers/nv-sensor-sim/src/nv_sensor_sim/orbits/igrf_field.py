"""IGRF-14 magnetic-field evaluator wrapping ``ppigrf``.

ppigrf ≥2.0.0 ships IGRF-14 coefficients by default (validity 2020–2030).
This module returns NED-frame magnetic field in **Tesla** to match the rest
of the simulator's unit convention; ppigrf itself returns nanotesla.
"""

from __future__ import annotations

from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

import numpy as np


# IGRF-14 official validity window. Used by callers to flag/suppress the
# extrapolation_note manifest field.
IGRF_MODEL_VERSION = "14"
IGRF_VALID_FROM = 2020.0
IGRF_VALID_TO = 2030.0


def _ppigrf_version() -> str:
    try:
        return version("ppigrf")
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


def igrf_ned(
    lat_deg: np.ndarray | float,
    lon_deg: np.ndarray | float,
    alt_m: np.ndarray | float,
    date: datetime,
) -> np.ndarray:
    """Evaluate IGRF-14 in NED frame at one or more geodetic points.

    Parameters
    ----------
    lat_deg, lon_deg : array-like or float
        Geodetic latitude and longitude in degrees. Broadcastable.
    alt_m : array-like or float
        Geodetic altitude in **meters** (converted to km internally).
    date : datetime
        Single date at which to evaluate IGRF coefficients. For LEO benchmarks
        the secular variation across a multi-hour trajectory is negligible
        (< nT) so a single epoch is the standard convention; downstream
        ``manifest['igrf']['epoch_decimal_year']`` records it.

    Returns
    -------
    np.ndarray
        Shape ``(..., 3)`` of NED ``(N, E, D)`` magnetic-field vectors in Tesla.
    """
    import ppigrf  # local import; optional dependency

    lat = np.asarray(lat_deg, dtype=np.float64)
    lon = np.asarray(lon_deg, dtype=np.float64)
    alt_km = np.asarray(alt_m, dtype=np.float64) / 1000.0

    # ppigrf compares ``date`` against tz-naive pandas Timestamps in its
    # coefficient table, so it cannot accept tz-aware datetimes. Strip tz.
    naive_date = date.replace(tzinfo=None) if date.tzinfo is not None else date
    Be, Bn, Bu = ppigrf.igrf(lon, lat, alt_km, naive_date)
    # ppigrf returns shape (N_dates, ...coord_shape); single date → squeeze axis 0.
    Be = np.asarray(Be).squeeze(axis=0)
    Bn = np.asarray(Bn).squeeze(axis=0)
    Bu = np.asarray(Bu).squeeze(axis=0)

    # NED = (North, East, Down). Bu is upward, so D = -Bu.
    ned_nT = np.stack([Bn, Be, -Bu], axis=-1)
    return ned_nT * 1e-9  # nT → T


def epoch_decimal_year(t: datetime) -> float:
    """Convert a datetime to a decimal year (fractional days/year)."""
    year_start = datetime(t.year, 1, 1, tzinfo=t.tzinfo)
    next_year_start = datetime(t.year + 1, 1, 1, tzinfo=t.tzinfo)
    fraction = (t - year_start) / (next_year_start - year_start)
    return float(t.year + fraction)


__all__ = [
    "IGRF_MODEL_VERSION",
    "IGRF_VALID_FROM",
    "IGRF_VALID_TO",
    "igrf_ned",
    "epoch_decimal_year",
    "_ppigrf_version",
]
