"""File-free checks for external validation rows."""

from __future__ import annotations

import numpy as np

from scripts.validate_external_datasets import (
    ROW_KEYS,
    _is_zenodo_ml_scan_spectrum,
    build_comparison_row,
)


def _spectrum(freq_hz: np.ndarray) -> np.ndarray:
    width = 4e6
    return 1 - 0.1 * width**2 / ((freq_hz - 2.87e9) ** 2 + width**2)


def _simulate(_adapter, _field, *, freq_range, n_points):
    freq_hz = np.linspace(*freq_range, n_points)
    return freq_hz, _spectrum(freq_hz)


def test_zenodo_ml_scan_name_filter_drops_frequency_axes_and_bad_shapes():
    freq = np.arange(4)
    signal = np.ones(4)
    for name in ("freqs", "freq", "req"):
        assert not _is_zenodo_ml_scan_spectrum(name, freq, signal)
    assert not _is_zenodo_ml_scan_spectrum("x_1", freq, signal.reshape(2, 2))
    assert not _is_zenodo_ml_scan_spectrum("x_1", freq, signal[:3])
    assert _is_zenodo_ml_scan_spectrum("x_1", freq, signal)


def test_build_rows_from_two_synthetic_arrays():
    freq_mhz = np.linspace(2840, 2900, 101)
    exp = _spectrum(freq_mhz * 1e6)
    for item, signal in (("first", exp), ("second", 1 - 2 * (1 - exp))):
        row = build_comparison_row(
            "synthetic", item, freq_mhz, signal, None,
            B_lab_T=np.zeros(3), sim_field_source="zero", simulate=_simulate,
        )
        assert set(row) == set(ROW_KEYS)
        assert row["comparable"] is True
        assert row["overlap_ok"] is True
        assert row["n_points"] == len(exp)
        assert row["shape_mse"] < 1e-12
        assert row["B_lab_mT"] == [0.0, 0.0, 0.0]
