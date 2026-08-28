"""Unit tests for the external (real, downloaded) dataset loaders.

Each test skips with "dataset not downloaded" if its ``data/experimental/``
directory is absent (see ``external_datasets._require_dir``); on a machine
where the data is present (as it is here), the tests run for real against the
actual downloaded files and check non-empty, finite arrays with a plausible
ODMR frequency range where a frequency axis is meaningful.
"""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.datasets import external_datasets as ed

# Loose "near the 2870 MHz NV zero-field splitting" window shared by every
# dataset here (each dataset's own axis is narrower; this just catches gross
# unit/parsing errors, e.g. accidentally returning Hz or GHz instead of MHz).
_ODMR_MHZ_LO, _ODMR_MHZ_HI = 2400.0, 3400.0


def _assert_plausible_odmr_freq_mhz(freq_MHz: np.ndarray) -> None:
    assert freq_MHz.size > 0
    assert np.isfinite(freq_MHz).all()
    assert _ODMR_MHZ_LO <= freq_MHz.min() <= freq_MHz.max() <= _ODMR_MHZ_HI


# ---------------------------------------------------------------------------
# zenodo_ml_scan_7481960
# ---------------------------------------------------------------------------


def test_zenodo_ml_scan_spectrum_x1():
    try:
        spectrum = ed.load_zenodo_ml_scan_spectrum("x_1")
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert spectrum.freq_MHz.shape == spectrum.signal.shape
    assert spectrum.signal.size > 0
    assert np.isfinite(spectrum.signal).all()
    _assert_plausible_odmr_freq_mhz(spectrum.freq_MHz)


@pytest.mark.parametrize("name", ["x_2", "x_2_1", "x_2_10", "req", "freqs"])
def test_zenodo_ml_scan_spectrum_all_names(name):
    try:
        spectrum = ed.load_zenodo_ml_scan_spectrum(name)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert spectrum.freq_MHz.size > 0
    assert spectrum.freq_MHz.shape == spectrum.signal.shape
    assert np.isfinite(spectrum.freq_MHz).all()
    assert np.isfinite(spectrum.signal).all()
    _assert_plausible_odmr_freq_mhz(spectrum.freq_MHz)


def test_zenodo_ml_scan_spectrum_registry_covers_all_listed_names():
    try:
        names = ed.list_zenodo_ml_scan_spectra()
    except Exception:  # noqa: BLE001 - list_* doesn't touch disk, but be safe
        pytest.skip("dataset not downloaded")
    for name in names:
        try:
            spectrum = ed.load_zenodo_ml_scan_spectrum(name)
        except FileNotFoundError:
            pytest.skip("dataset not downloaded")
        assert spectrum.signal.size > 0
        assert np.isfinite(spectrum.signal).all()


def test_zenodo_ml_scan_field_positions():
    try:
        field_vals, noise = ed.load_zenodo_ml_scan_field_positions("x")
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert field_vals.ndim == 2
    assert field_vals.shape[1] == 3
    assert field_vals.shape[0] == noise.shape[0]
    assert field_vals.size > 0
    assert np.isfinite(field_vals).all()
    assert np.isfinite(noise).all()


def test_zenodo_ml_scan_field_positions_z_axis_base_only():
    try:
        field_vals, noise = ed.load_zenodo_ml_scan_field_positions("z")
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert field_vals.shape[0] == noise.shape[0] > 0
    with pytest.raises(FileNotFoundError):
        ed.load_zenodo_ml_scan_field_positions("z", repeat=2)


def test_zenodo_ml_scan_unknown_spectrum_name_raises():
    if not (ed.DATA_DIR / ed._ZENODO_ML_SCAN_DIR).is_dir():
        pytest.skip("dataset not downloaded")
    with pytest.raises(ValueError):
        ed.load_zenodo_ml_scan_spectrum("not-a-real-name")


# ---------------------------------------------------------------------------
# zenodo_zerofield_10629041
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preprocessed", [True, False])
def test_zenodo_zerofield_odmr(preprocessed):
    try:
        data = ed.load_zenodo_zerofield_odmr(preprocessed=preprocessed)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert data.signal.shape[0] == data.freq_MHz.shape[0]
    assert data.signal.shape[1] == len(data.position_labels) == 47
    assert data.signal.size > 0
    assert np.isfinite(data.signal).all()
    _assert_plausible_odmr_freq_mhz(data.freq_MHz)


# ---------------------------------------------------------------------------
# harvard_lowfield_6TFFPG
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_label", ["0.5mT", "1mT"])
def test_harvard_lowfield_odmr(field_label):
    try:
        grid = ed.load_harvard_lowfield_odmr(field_label)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert grid.signal.shape == (grid.freq_MHz.shape[0], grid.sweep_axis.shape[0])
    assert grid.signal.size > 0
    assert np.isfinite(grid.freq_MHz).all()
    assert np.isfinite(grid.sweep_axis).all()
    assert np.isfinite(grid.signal).all()
    _assert_plausible_odmr_freq_mhz(grid.freq_MHz)


def test_harvard_lowfield_unknown_field_label_raises():
    if not (ed.DATA_DIR / ed._HARVARD_DIR).is_dir():
        pytest.skip("dataset not downloaded")
    with pytest.raises(ValueError):
        ed.load_harvard_lowfield_odmr("3mT")


# ---------------------------------------------------------------------------
# darus_gradiometry_2817 (not ODMR spectra; see module docstring)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(ed._DARUS_SUPPORTED_TABLES))
def test_darus_gradiometry_table_all_supported(name):
    try:
        table = ed.load_darus_gradiometry_table(name)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert len(table) > 0
    for col, values in table.items():
        assert values.size > 0, f"empty column {col!r} in {name}"
        finite_values = values[~np.isnan(values)]
        assert finite_values.size > 0, f"all-NaN column {col!r} in {name}"
        assert np.isfinite(finite_values).all(), f"non-finite (inf) value in column {col!r} of {name}"


def test_darus_gradiometry_table_fig3a_unsupported():
    try:
        ed._require_dir(ed._DARUS_DIR)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    with pytest.raises(ValueError):
        ed.load_darus_gradiometry_table("fig3a")


def test_darus_gradiometry_table_unknown_name_raises():
    try:
        ed._require_dir(ed._DARUS_DIR)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    with pytest.raises(ValueError):
        ed.load_darus_gradiometry_table("not-a-real-figure")


# ---------------------------------------------------------------------------
# borealis_sbquantum_DRTLGW (the star dataset: real rotation sweep)
# ---------------------------------------------------------------------------


def test_borealis_rotation_sequence_ordering_and_content():
    try:
        sequence = ed.load_borealis_rotation_sequence()
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")

    assert len(sequence) > 1

    angles = [frame.angle_deg for frame in sequence]
    assert len(set(angles)) > 1, "expected more than one distinct rotation angle"
    assert angles == sorted(angles), "sequence must be ordered by ascending angle"

    freq_shape = sequence[0].freq_MHz.shape
    for frame in sequence:
        assert frame.freq_MHz.shape == frame.signal.shape == freq_shape
        assert frame.signal.size > 0
        assert np.isfinite(frame.freq_MHz).all()
        assert np.isfinite(frame.signal).all()
        _assert_plausible_odmr_freq_mhz(frame.freq_MHz)

    # Every frame shares the same frequency axis (verified against the raw
    # CSVs — see module docstring), so stacking reproduces a (T, F) matrix
    # mirroring dynamics.render.render_sequence's ``spectra``.
    stacked = np.stack([frame.signal for frame in sequence])
    assert stacked.shape == (len(sequence), freq_shape[0])


def test_borealis_rotation_angles_match_sequence():
    try:
        angles_listed = ed.list_borealis_rotation_angles()
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    sequence = ed.load_borealis_rotation_sequence()
    assert angles_listed == sorted(angles_listed)
    assert [int(frame.angle_deg) for frame in sequence] == angles_listed


def test_borealis_angle_rabi_map_raw_cube():
    try:
        angles = ed.list_borealis_rotation_angles()
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    freq_MHz, duration_ns, pl = ed.load_borealis_angle_rabi_map(angles[0])
    assert pl.shape == (freq_MHz.shape[0], duration_ns.shape[0])
    assert pl.size > 0
    assert np.isfinite(pl).all()
    assert np.isfinite(duration_ns).all()
    assert (duration_ns > 0).all()
    _assert_plausible_odmr_freq_mhz(freq_MHz)


def test_borealis_angle_rabi_map_unknown_angle_raises():
    try:
        ed._require_dir(ed._BOREALIS_DIR)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    with pytest.raises(FileNotFoundError):
        ed.load_borealis_angle_rabi_map(999)


def test_borealis_detuning_scan():
    try:
        files = ed.list_borealis_detuning_scan_files()
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert len(files) > 0
    columns = ed.load_borealis_detuning_scan(files[0])
    assert set(columns) == {
        "Pulse duration (ns)",
        "Interpulse duration (ns)",
        "Photoluminescence (Arb. Units)",
        "Detuning",
        "Coil voltage",
    }
    for name, values in columns.items():
        assert values.size > 0, f"empty column {name!r}"
        assert np.isfinite(values).all(), f"non-finite value in column {name!r}"
    # Detuning and coil voltage are each constant within one file (verified
    # against the raw CSVs — see module docstring / list_* helper docstring).
    assert np.unique(columns["Detuning"]).size == 1
    assert np.unique(columns["Coil voltage"]).size == 1


def test_borealis_detuning_scan_invalid_filename_raises():
    try:
        ed._require_dir(ed._BOREALIS_DIR)
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    with pytest.raises(ValueError):
        ed.load_borealis_detuning_scan("05degrees.csv")  # a rotation file, not a detuning scan


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_EXPECTED_REGISTRY_KEYS = {
    "zenodo_ml_scan",
    "zenodo_zerofield",
    "harvard_lowfield",
    "darus_gradiometry",
    "borealis_sbquantum",
}


def test_registry_has_expected_keys():
    assert set(ed.EXTERNAL_DATASETS) == _EXPECTED_REGISTRY_KEYS


@pytest.mark.parametrize("name", sorted(_EXPECTED_REGISTRY_KEYS))
def test_registry_loaders_are_zero_arg_callable(name):
    loader = ed.EXTERNAL_DATASETS[name]
    try:
        result = loader()
    except FileNotFoundError:
        pytest.skip("dataset not downloaded")
    assert result is not None
