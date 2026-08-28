"""Loaders for external (real, downloaded) ODMR reference datasets.

Five third-party research datasets live under ``data/experimental/`` alongside
the repo's existing ``zenodo_odmr`` reference set (see
``nv_sensor_sim.validation.reference_comparison``). Unlike ``zenodo_odmr``,
these five directories are gitignored raw research-data dumps (each fetched
by hand from its DOI; see the ``_zenodo_metadata.json`` /
``_dataverse_metadata.json`` sidecar in each directory for provenance) and are
not guaranteed to be present on every checkout. Every loader below therefore
raises ``FileNotFoundError`` with a clear "not downloaded" message when its
directory is absent or empty, so importing this module never fails even on a
machine without the data (see ``tests/unit/test_external_datasets.py``, which
``pytest.skip()``s per dataset in that case).

Unit convention: every frequency array returned from this module is in **MHz**
(unlike ``reference_comparison.load_experimental_odmr``, which returns Hz —
that function pre-dates this module and its convention is left as-is). This
follows the task's explicit ``freq_array_MHz`` naming for the Borealis
rotation sequence and is applied consistently to the other four loaders too,
since every dataset's native frequency axis is already MHz-scale (or trivially
converted from GHz/kHz).

Investigated formats (2026-08-28, against the actual downloaded files):

- ``zenodo_ml_scan_7481960``: MATLAB ``.mat`` files, mostly v5
  (``scipy.io.loadmat``) but ``freq.mat`` is v7.3 / HDF5 and needs ``h5py``.
  Frequency axes and their matching normalized spectra were identified by
  matching array length *and* MHz range (all cluster around the 2870 MHz
  ODMR line): ``freq.mat`` (600 pts, 2530-3250 MHz) pairs with
  ``norm_x_1.mat`` / ``norm_x_2.mat`` / ``norm_x_2_1..10.mat``; ``req.mat``
  (300 pts, 2730-3030 MHz) pairs with ``norm.mat``; ``freqs.mat`` (270 pts,
  2730-3000 MHz) pairs with ``normalized.mat``. ``field_vals_{x,y,z}[_2,_3].mat``
  / ``noiseVec_{x,y,z}[_2,_3].mat`` hold per-scan-point field vectors and a
  noise metric (units undocumented upstream — passed through unconverted).
- ``zenodo_zerofield_10629041``: tab-separated ``.txt``, header
  ``#MW frequency (GHz)`` + ``Position 1..47`` (47 spatial positions along a
  waveguide, per the Zenodo description). ``Raw_data.txt`` (201 rows) and
  ``Preprocessed_data.txt`` (130 rows) share the same layout.
- ``harvard_lowfield_6TFFPG``: comma-separated ``.csv``. This loader targets
  specifically the two files the task calls out — ``Fig.4c_ODMR_0.5mT_2D.csv``
  / ``Fig.4c_ODMR_1mT_2D.csv`` — a 2D grid: row index = MW frequency in MHz
  (confirmed 2820-2920 MHz / 2865-2877 MHz), column header = a second swept
  parameter whose physical meaning is not stated in the file (no rationale
  invented here; returned as an opaque ``sweep_axis``). The directory holds
  many other Fig2/Fig3/Fig5/FigS* CSVs with different, per-figure axis
  conventions not covered by this loader.
- ``darus_gradiometry_2817``: **not ODMR spectra** — Allan-deviation /
  sensitivity and recovery-time curves for the paper's magnetometer and
  gradiometer (``cw_odmr.m`` in the same directory is a MATLAB sensitivity
  *simulation*, not a data loader). Tab-separated ``.tab`` files parse
  cleanly as all-numeric tables with a single header row, **except**
  ``fig3a.tab``, which uses an irregular two-row header (a wide Rabi x
  integration-time sensitivity map) that ``pandas`` cannot parse as a plain
  table — left unsupported, same as the redundant ``.xlsx`` copies (also
  irregular multi-row headers; ``openpyxl``/``pd.read_excel`` are not a
  declared project dependency either way, so they are not used here).
- ``borealis_sbquantum_DRTLGW``: the star dataset, two distinct CSV families
  confirmed by inspecting columns and per-file unique() values (not
  assumption):

  1. ``{angle}degrees.csv`` (23 files, angles 5-355 deg): columns
     ``Frequency (kHz)``, ``Pulse duration (ns)``, ``Photoluminescence``. Every
     file sweeps the *same* 40 MW frequencies (2860000-2879500 kHz, i.e.
     2860-2879.5 MHz — verified identical across files) x 997 pulse
     durations (100-29980 ns): a per-angle pulsed-Rabi map. This is the
     rotation sweep; see ``load_borealis_rotation_sequence``.
  2. ``{idx}_{detuning_hz}[-repeat].csv`` (~230 files): columns
     ``Pulse duration (ns)``, ``Interpulse duration (ns)``,
     ``Photoluminescence (Arb. Units)``, ``Detuning``, ``Coil voltage``.
     ``Detuning`` and ``Coil voltage`` are each a *single constant value*
     within a file (verified via ``.unique()`` over the full column, not just
     a header peek) — this family is a pulse/coil-voltage calibration scan at
     one fixed MW detuning, not a frequency sweep, so it is intentionally
     *not* folded into ``load_borealis_rotation_sequence``. See
     ``load_borealis_detuning_scan``.

  The many ``.py`` files alongside the CSVs (``abstract_ensemble.py``,
  ``master_equation_solver.py``, etc.) are the paper's own simulation
  codebase, not data files, and are not touched by this module.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

# src/nv_sensor_sim/datasets/external_datasets.py -> parents[3] is the repo
# root, matching the depth used by nv_sensor_sim.orbits.benchmark._REPO_ROOT.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = _REPO_ROOT / "data" / "experimental"


def _require_dir(name: str) -> Path:
    """Return ``DATA_DIR / name``, raising a clear error if not downloaded."""
    d = DATA_DIR / name
    if not d.is_dir() or not any(d.iterdir()):
        raise FileNotFoundError(
            f"External dataset '{name}' is not downloaded: expected data at {d}. "
            "This directory is gitignored and must be fetched separately — see "
            "its _zenodo_metadata.json / _dataverse_metadata.json sidecar (once "
            "present) for the source DOI."
        )
    return d


def _require_file(path: Path, context: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{context}: expected file not found at {path}.")


# ---------------------------------------------------------------------------
# zenodo_ml_scan_7481960 — NV ODMR ML-training scan data (Haim & Bar-Gill)
# ---------------------------------------------------------------------------

_ZENODO_ML_SCAN_DIR = "zenodo_ml_scan_7481960"

# name -> (freq_file, freq_key, signal_file, signal_key). Pairings verified by
# matching array length and MHz range (see module docstring).
_ZENODO_ML_SCAN_SPECTRA: dict[str, tuple[str, str, str, str]] = {
    "x_1": ("freq.mat", "freq", "norm_x_1.mat", "norm"),
    "x_2": ("freq.mat", "freq", "norm_x_2.mat", "norm"),
    **{f"x_2_{i}": ("freq.mat", "freq", f"norm_x_2_{i}.mat", "norm") for i in range(1, 11)},
    "req": ("req.mat", "x", "norm.mat", "y"),
    "freqs": ("freqs.mat", "x", "normalized.mat", "y"),
}


def list_zenodo_ml_scan_spectra() -> list[str]:
    """Names accepted by ``load_zenodo_ml_scan_spectrum``."""
    return sorted(_ZENODO_ML_SCAN_SPECTRA)


class ZenodoScanSpectrum(NamedTuple):
    """One ODMR spectrum recovered from the Zenodo ML-scan .mat dump."""

    freq_MHz: np.ndarray
    signal: np.ndarray


def _load_mat_vector(path: Path, key: str) -> np.ndarray:
    """Load one 1D variable from a .mat file, v5 (scipy) or v7.3 (h5py)."""
    import scipy.io as sio

    try:
        data = sio.loadmat(path)
        return np.asarray(data[key], dtype=np.float64).reshape(-1)
    except NotImplementedError:
        # scipy.io.loadmat raises NotImplementedError for v7.3/HDF5 .mat files
        # (verified: freq.mat in this dataset is v7.3) and points at h5py.
        import h5py

        with h5py.File(path, "r") as f:
            return np.asarray(f[key][:], dtype=np.float64).reshape(-1)


def load_zenodo_ml_scan_spectrum(name: str = "x_1") -> ZenodoScanSpectrum:
    """Load one (frequency, signal) ODMR spectrum from the ML-scan dump.

    Parameters
    ----------
    name : str
        One of ``list_zenodo_ml_scan_spectra()`` (default ``"x_1"``).

    Returns
    -------
    ZenodoScanSpectrum
        ``freq_MHz`` and ``signal`` are equal-length 1D arrays.
    """
    d = _require_dir(_ZENODO_ML_SCAN_DIR)
    if name not in _ZENODO_ML_SCAN_SPECTRA:
        raise ValueError(f"Unknown spectrum {name!r}; choose one of {list_zenodo_ml_scan_spectra()}")
    freq_file, freq_key, sig_file, sig_key = _ZENODO_ML_SCAN_SPECTRA[name]
    freq_path, sig_path = d / freq_file, d / sig_file
    _require_file(freq_path, f"zenodo_ml_scan spectrum {name!r}")
    _require_file(sig_path, f"zenodo_ml_scan spectrum {name!r}")
    freq_MHz = _load_mat_vector(freq_path, freq_key)
    signal = _load_mat_vector(sig_path, sig_key)
    return ZenodoScanSpectrum(freq_MHz=freq_MHz, signal=signal)


def load_zenodo_ml_scan_field_positions(
    axis: str = "x", repeat: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Field vectors and per-point noise for one x/y/z scan-position sweep.

    Parameters
    ----------
    axis : str
        ``"x"``, ``"y"``, or ``"z"``.
    repeat : int, optional
        ``None``/``1`` for the base file, ``2`` or ``3`` for a repeat scan.
        Only ``x`` and ``y`` have repeats 2/3 on disk; ``z`` has only the base.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(field_vals (N, 3), noise (N,))``. Units are as recorded in the
        source .mat files — undocumented upstream, so none is assumed here.
    """
    if axis not in ("x", "y", "z"):
        raise ValueError(f"axis must be 'x', 'y', or 'z', got {axis!r}")
    d = _require_dir(_ZENODO_ML_SCAN_DIR)
    suffix = "" if repeat in (None, 1) else f"_{repeat}"
    field_path = d / f"field_vals_{axis}{suffix}.mat"
    noise_path = d / f"noiseVec_{axis}{suffix}.mat"
    _require_file(field_path, f"zenodo_ml_scan field positions axis={axis!r} repeat={repeat!r}")
    _require_file(noise_path, f"zenodo_ml_scan field positions axis={axis!r} repeat={repeat!r}")
    import scipy.io as sio

    field_vals = np.asarray(
        sio.loadmat(field_path)[f"field_vals_{axis}{suffix}"], dtype=np.float64
    )
    noise = np.asarray(
        sio.loadmat(noise_path)[f"noiseVec_{axis}{suffix}"], dtype=np.float64
    ).reshape(-1)
    return field_vals, noise


# ---------------------------------------------------------------------------
# zenodo_zerofield_10629041 — zero-field ODMR strain-components dataset
# ---------------------------------------------------------------------------

_ZENODO_ZEROFIELD_DIR = "zenodo_zerofield_10629041"


class ZeroFieldODMR(NamedTuple):
    """Multi-position zero-field ODMR spectra (diamond waveguide)."""

    freq_MHz: np.ndarray
    signal: np.ndarray  # shape (len(freq_MHz), len(position_labels))
    position_labels: list[str]


def load_zenodo_zerofield_odmr(preprocessed: bool = True) -> ZeroFieldODMR:
    """Load the zero-field ODMR dataset (47 spatial positions per frequency).

    Parameters
    ----------
    preprocessed : bool
        ``True`` (default) loads ``Preprocessed_data.txt``; ``False`` loads
        ``Raw_data.txt``. Both share the same
        ``#MW frequency (GHz)`` + ``Position 1..47`` layout.
    """
    d = _require_dir(_ZENODO_ZEROFIELD_DIR)
    fname = "Preprocessed_data.txt" if preprocessed else "Raw_data.txt"
    path = d / fname
    _require_file(path, "zenodo_zerofield ODMR data")
    df = pd.read_csv(path, sep="\t")
    freq_col = df.columns[0]
    freq_MHz = df[freq_col].to_numpy(dtype=np.float64) * 1000.0  # GHz -> MHz
    position_cols = list(df.columns[1:])
    signal = df[position_cols].to_numpy(dtype=np.float64)
    return ZeroFieldODMR(freq_MHz=freq_MHz, signal=signal, position_labels=position_cols)


# ---------------------------------------------------------------------------
# harvard_lowfield_6TFFPG — all-optical PL spectra of NV ensembles at low B
# ---------------------------------------------------------------------------

_HARVARD_DIR = "harvard_lowfield_6TFFPG"
_HARVARD_FIELD_FILES = {
    "0.5mT": "Fig.4c_ODMR_0.5mT_2D.csv",
    "1mT": "Fig.4c_ODMR_1mT_2D.csv",
}


class HarvardODMRGrid(NamedTuple):
    """A 2D ODMR grid: MW frequency x a second (undocumented) swept axis."""

    freq_MHz: np.ndarray
    sweep_axis: np.ndarray  # opaque second axis (meaning not stated upstream)
    signal: np.ndarray  # shape (len(freq_MHz), len(sweep_axis))


def load_harvard_lowfield_odmr(field_label: str = "0.5mT") -> HarvardODMRGrid:
    """Load the Fig.4c ODMR-vs-frequency grid at a fixed low bias field.

    Parameters
    ----------
    field_label : str
        ``"0.5mT"`` (default) or ``"1mT"``.
    """
    d = _require_dir(_HARVARD_DIR)
    if field_label not in _HARVARD_FIELD_FILES:
        raise ValueError(
            f"field_label must be one of {sorted(_HARVARD_FIELD_FILES)}, got {field_label!r}"
        )
    path = d / _HARVARD_FIELD_FILES[field_label]
    _require_file(path, f"harvard_lowfield ODMR grid field_label={field_label!r}")
    df = pd.read_csv(path, index_col=0)
    freq_MHz = df.index.to_numpy(dtype=np.float64)
    sweep_axis = df.columns.to_numpy(dtype=np.float64)
    signal = df.to_numpy(dtype=np.float64)
    return HarvardODMRGrid(freq_MHz=freq_MHz, sweep_axis=sweep_axis, signal=signal)


# ---------------------------------------------------------------------------
# darus_gradiometry_2817 — magnetometer/gradiometer sensitivity curves
# (NOT ODMR frequency-sweep spectra — see module docstring)
# ---------------------------------------------------------------------------

_DARUS_DIR = "darus_gradiometry_2817"

# Filenames (case-sensitive, matching disk) of the .tab files that parse as
# clean single-header-row numeric tables. "fig3a.tab" is deliberately
# excluded (see module docstring); .xlsx copies are not read at all.
_DARUS_SUPPORTED_TABLES = (
    "Fig3b",
    "Fig3c",
    "fig3d",
    "Fig4a",
    "Fig4b",
    "Fig4c",
    "Fig4d",
    "Fig5",
    "recovery2",
)
_DARUS_UNSUPPORTED_TABLES = ("fig3a",)  # irregular two-row header; see docstring


def list_darus_gradiometry_tables() -> list[str]:
    """Table names accepted by ``load_darus_gradiometry_table``."""
    return sorted(_DARUS_SUPPORTED_TABLES)


def load_darus_gradiometry_table(name: str = "Fig5") -> dict[str, np.ndarray]:
    """Load one DaRUS gradiometry ``.tab`` measurement table by figure name.

    Not ODMR spectra: these are Allan-deviation/sensitivity, linewidth-vs-Rabi,
    or recovery-time curves (see module docstring for what each figure holds).
    Returned columns may contain NaN where the source table is ragged (some
    sub-columns end before others); this is not stripped here.

    Parameters
    ----------
    name : str
        One of ``list_darus_gradiometry_tables()`` (default ``"Fig5"``, the
        OPM/diamond-magnetometer/gradiometer comparison). ``"fig3a"`` (a
        Rabi x integration-time sensitivity map with an irregular two-row
        header) is deliberately unsupported — raises ``ValueError``.

    Returns
    -------
    dict[str, np.ndarray]
        Column name -> 1D float array, one entry per CSV column.
    """
    d = _require_dir(_DARUS_DIR)
    if name in _DARUS_UNSUPPORTED_TABLES:
        raise ValueError(
            f"DaRUS table {name!r} is unsupported: it uses an irregular two-row "
            "header (a wide sensitivity map) that does not parse as a plain "
            f"table. Supported tables: {list_darus_gradiometry_tables()}"
        )
    if name not in _DARUS_SUPPORTED_TABLES:
        raise ValueError(f"Unknown DaRUS table {name!r}; choose one of {list_darus_gradiometry_tables()}")
    path = d / f"{name}.tab"
    _require_file(path, f"darus_gradiometry table {name!r}")
    df = pd.read_csv(path, sep="\t")
    return {col: df[col].to_numpy(dtype=np.float64) for col in df.columns}


# ---------------------------------------------------------------------------
# borealis_sbquantum_DRTLGW — bias-field-free NV vector magnetometry
# (the star dataset: a real rotation sweep)
# ---------------------------------------------------------------------------

_BOREALIS_DIR = "borealis_sbquantum_DRTLGW"
_ANGLE_FILE_RE = re.compile(r"^(\d+)degrees\.csv$")
_DETUNING_FILE_RE = re.compile(r"^\d+_\d+(?:-\d+)?\.csv$")


def _borealis_angle_files(d: Path) -> dict[int, Path]:
    """angle_deg (int) -> path, built from the files actually on disk."""
    out: dict[int, Path] = {}
    for p in d.glob("*degrees.csv"):
        m = _ANGLE_FILE_RE.match(p.name)
        if m:
            out[int(m.group(1))] = p
    return out


def list_borealis_rotation_angles() -> list[int]:
    """Integer rotation angles (degrees) present on disk, ascending."""
    d = _require_dir(_BOREALIS_DIR)
    return sorted(_borealis_angle_files(d))


def load_borealis_angle_rabi_map(angle_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Raw (frequency, pulse-duration, PL) Rabi cube for one rotation angle.

    This is the un-reduced measurement behind one frame of
    ``load_borealis_rotation_sequence`` — every MW frequency has a full Rabi
    (PL vs pulse-duration) curve, not just a single value.

    Parameters
    ----------
    angle_deg : float
        Rotation angle in degrees; rounded to the nearest integer to match
        the files on disk (see ``list_borealis_rotation_angles``).

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray]
        ``(freq_MHz (40,), duration_ns (997,), pl (40, 997))``.
    """
    d = _require_dir(_BOREALIS_DIR)
    angle_files = _borealis_angle_files(d)
    key = int(round(angle_deg))
    if key not in angle_files:
        raise FileNotFoundError(
            f"No Borealis rotation-sweep file for angle={angle_deg} deg in {d}. "
            f"Available angles (deg): {sorted(angle_files)}"
        )
    df = pd.read_csv(angle_files[key], index_col=0)
    freqs_khz = np.sort(df["Frequency (kHz)"].unique())
    durations_ns = np.sort(df["Pulse duration (ns)"].unique())
    pivot = df.pivot(index="Frequency (kHz)", columns="Pulse duration (ns)", values="Photoluminescence")
    pivot = pivot.reindex(index=freqs_khz, columns=durations_ns)
    pl = pivot.to_numpy(dtype=np.float64)
    return freqs_khz.astype(np.float64) / 1000.0, durations_ns.astype(np.float64), pl


class BorealisRotationFrame(NamedTuple):
    """One rotation angle's reduced ODMR-like spectrum.

    Mirrors the per-timestep element of the ``(T, F)`` ``spectra`` array
    (paired with the ``(F,)`` ``frequencies`` array) returned by
    ``nv_sensor_sim.dynamics.render.render_sequence`` for a swept-field
    time-series: here each "frame" is one rotation angle instead of one
    timestep, and ``freq_MHz`` / ``signal`` play the role of that function's
    ``frequencies`` / ``spectra[t]``. Every angle file shares an identical
    40-point frequency axis (verified against the raw CSVs), so
    ``np.stack([f.signal for f in sequence])`` reproduces a ``(T, F)`` matrix
    exactly like ``render_sequence``'s ``spectra``.
    """

    angle_deg: float
    freq_MHz: np.ndarray
    signal: np.ndarray


def load_borealis_rotation_sequence() -> list[BorealisRotationFrame]:
    """Load the Borealis rotation sweep as an angle-ascending sequence.

    ``signal`` is the pulse-duration-averaged photoluminescence at each of
    the 40 swept MW frequencies (a plain mean over the 997 recorded Rabi
    durations per frequency) — a derived, ODMR-like reduction of the raw
    pulsed-Rabi cube, not a raw measurement. No physics-motivated reduction
    (e.g. a specific duration slice or oscillation contrast) is assumed here;
    see ``load_borealis_angle_rabi_map`` for the full, un-reduced
    ``(freq, duration, PL)`` cube per angle.

    Returns
    -------
    list[BorealisRotationFrame]
        One entry per angle file on disk, ordered by ascending ``angle_deg``.
    """
    d = _require_dir(_BOREALIS_DIR)
    angle_files = _borealis_angle_files(d)
    if not angle_files:
        raise FileNotFoundError(f"No '*degrees.csv' rotation-sweep files found in {d}.")
    frames = []
    for angle in sorted(angle_files):
        freq_MHz, _durations_ns, pl = load_borealis_angle_rabi_map(angle)
        signal = pl.mean(axis=1)
        frames.append(BorealisRotationFrame(angle_deg=float(angle), freq_MHz=freq_MHz, signal=signal))
    return frames


def list_borealis_detuning_scan_files() -> list[str]:
    """Filenames of the ``{idx}_{detuning_hz}[-repeat].csv`` calibration scans.

    Not a frequency sweep: ``Detuning`` and ``Coil voltage`` are each a single
    constant value within a file (verified via ``.unique()`` over full
    columns on representative files); the swept axes are
    ``Pulse duration (ns)`` and ``Interpulse duration (ns)``.
    """
    d = _require_dir(_BOREALIS_DIR)
    return sorted(
        p.name
        for p in d.glob("*.csv")
        if not _ANGLE_FILE_RE.match(p.name) and _DETUNING_FILE_RE.match(p.name)
    )


def load_borealis_detuning_scan(filename: str) -> dict[str, np.ndarray]:
    """Load one raw pulse/coil-voltage calibration file by name.

    Parameters
    ----------
    filename : str
        One of ``list_borealis_detuning_scan_files()``, e.g. ``"0_2867000.csv"``.

    Returns
    -------
    dict[str, np.ndarray]
        Column name -> 1D float array (``Pulse duration (ns)``,
        ``Interpulse duration (ns)``, ``Photoluminescence (Arb. Units)``,
        ``Detuning``, ``Coil voltage``).
    """
    d = _require_dir(_BOREALIS_DIR)
    if not _DETUNING_FILE_RE.match(filename):
        raise ValueError(
            f"{filename!r} is not a detuning-scan filename "
            "(expected '{idx}_{detuning_hz}[-repeat].csv')"
        )
    path = d / filename
    _require_file(path, "borealis detuning-scan file")
    df = pd.read_csv(path, index_col=0)
    return {col: df[col].to_numpy(dtype=np.float64) for col in df.columns}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: name -> zero-argument loader (every loader above has defaults for its
#: optional selector argument, so each is directly callable with no args).
EXTERNAL_DATASETS: dict[str, Any] = {
    "zenodo_ml_scan": load_zenodo_ml_scan_spectrum,
    "zenodo_zerofield": load_zenodo_zerofield_odmr,
    "harvard_lowfield": load_harvard_lowfield_odmr,
    "darus_gradiometry": load_darus_gradiometry_table,
    "borealis_sbquantum": load_borealis_rotation_sequence,
}
