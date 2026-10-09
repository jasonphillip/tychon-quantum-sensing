"""Compare available external ODMR spectra with the default SimOS ensemble model."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Callable

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.datasets import external_datasets as ed
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT, generate_multi_axis_spectrum
from nv_sensor_sim.validation.reference_comparison import compare_spectra, load_experimental_odmr

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIRS = {
    "zenodo_ml_scan": "zenodo_ml_scan_7481960",
    "zenodo_zerofield": "zenodo_zerofield_10629041",
    "harvard": "harvard_lowfield_6TFFPG",
    "borealis": "borealis_sbquantum_DRTLGW",
    "zenodo_odmr": "zenodo_odmr",
    "darus_gradiometry": "darus_gradiometry_2817",
}
ROW_KEYS = (
    "dataset", "item", "n_points", "overlap_fraction", "overlap_ok", "shape_mse",
    "contrast_exp", "contrast_sim", "contrast_ratio", "linewidth_exp_hz",
    "linewidth_sim_hz", "max_abs_peak_offset_hz", "noise_exp", "sim_field_source",
    "B_lab_mT", "comparable", "reason",
)
FIELD_GRID_MT = (0, 0.5, 1, 2, 3, 5)


def _blank_row(dataset: str, item: str, reason: str, n_points: int | None = None) -> dict:
    row = dict.fromkeys(ROW_KEYS)
    row.update(dataset=dataset, item=item, n_points=n_points, comparable=False, reason=reason)
    return row


def _is_zenodo_ml_scan_spectrum(name: str, freq: np.ndarray, signal: np.ndarray) -> bool:
    """Accept only a named 1-D signal aligned with its frequency axis."""
    return (
        name not in {"freqs", "freq", "req"}
        and np.ndim(signal) == 1
        and np.size(signal) == np.size(freq)
    )


def build_comparison_row(
    dataset: str,
    item: str,
    exp_freq: np.ndarray,
    exp_signal: np.ndarray,
    adapter: SimOSAdapter,
    *,
    exp_freq_unit: str = "MHz",
    B_lab_T: np.ndarray | None = None,
    sim_field_source: str | None = None,
    reason: str = "",
    simulate: Callable = generate_multi_axis_spectrum,
) -> dict:
    """Build one row; a missing field is selected by minimum valid shape MSE."""
    freq = np.asarray(exp_freq, dtype=float).reshape(-1)
    signal = np.asarray(exp_signal, dtype=float).reshape(-1)
    if freq.size < 2 or freq.size != signal.size or not np.isfinite(freq).all():
        raise ValueError(f"{dataset}/{item}: invalid frequency or signal shape")
    if not np.isfinite(signal).all() or float(np.ptp(freq)) <= 0:
        raise ValueError(f"{dataset}/{item}: nonfinite signal or constant frequency")
    scale = {"MHz": 1e6, "Hz": 1.0}[exp_freq_unit]
    freq_range = (float(np.min(freq) * scale), float(np.max(freq) * scale))
    if B_lab_T is None:
        candidates = [np.zeros(3)] + [
            magnitude * 1e-3 * axis
            for magnitude in FIELD_GRID_MT[1:]
            for axis in NV_AXES_UNIT
        ]
        source = "fitted-grid"
    else:
        candidates = [np.asarray(B_lab_T, dtype=float)]
        source = sim_field_source or "documented"

    best = None
    for field in candidates:
        sim_freq, sim_signal = simulate(
            adapter, field, freq_range=freq_range, n_points=len(freq)
        )
        comparison = compare_spectra(
            sim_freq, sim_signal, freq, signal, exp_freq_unit=exp_freq_unit
        )
        score = comparison.shape_mse
        if best is None or (math.isfinite(score) and score < best[0]):
            best = (score, field, comparison)
    assert best is not None
    _, field, comparison = best
    offsets = [abs(x) for x in comparison.peak_offsets_hz if math.isfinite(x)]
    row = _blank_row(dataset, item, reason, len(freq))
    row.update(
        overlap_fraction=comparison.overlap_fraction,
        overlap_ok=comparison.overlap_ok,
        shape_mse=comparison.shape_mse,
        contrast_exp=comparison.contrast_exp,
        contrast_sim=comparison.contrast_sim,
        contrast_ratio=comparison.contrast_ratio,
        linewidth_exp_hz=comparison.linewidth_exp_hz,
        linewidth_sim_hz=comparison.linewidth_sim_hz,
        max_abs_peak_offset_hz=max(offsets) if offsets else None,
        noise_exp=comparison.noise_exp,
        sim_field_source=source,
        B_lab_mT=(field * 1e3).tolist(),
        comparable=bool(comparison.overlap_ok),
    )
    if not comparison.overlap_ok:
        row["reason"] = "Frequency overlap below comparison threshold"
    return row


def _dataset_rows(adapter: SimOSAdapter, max_items: int) -> list[dict]:
    rows = []

    def add(dataset: str, item: str, freq: np.ndarray, signal: np.ndarray, **kwargs) -> None:
        rows.append(build_comparison_row(dataset, item, freq, signal, adapter, **kwargs))

    try:
        selected = 0
        for name in ed.list_zenodo_ml_scan_spectra():
            if name in {"freqs", "freq", "req"}:
                continue
            spectrum = ed.load_zenodo_ml_scan_spectrum(name)
            if not _is_zenodo_ml_scan_spectrum(name, spectrum.freq_MHz, spectrum.signal):
                continue
            add("zenodo_ml_scan", name, spectrum.freq_MHz, spectrum.signal)
            selected += 1
            if selected >= max_items:
                break
    except FileNotFoundError as exc:
        rows.append(_blank_row("zenodo_ml_scan", "dataset", str(exc)))

    try:
        grid = ed.load_zenodo_zerofield_odmr()
        for i, label in enumerate(grid.position_labels[:max_items]):
            add("zenodo_zerofield", label, grid.freq_MHz, grid.signal[:, i],
                B_lab_T=np.zeros(3), sim_field_source="zero")
    except FileNotFoundError as exc:
        rows.append(_blank_row("zenodo_zerofield", "dataset", str(exc)))

    try:
        grid = ed.load_harvard_lowfield_odmr("0.5mT")
        # The Dataverse sidecar says "off-axis field" but gives no vector.
        # Use the first NV axis and expose this assumption in every row.
        for i, sweep in enumerate(grid.sweep_axis[:max_items]):
            add("harvard", str(sweep), grid.freq_MHz, grid.signal[:, i],
                B_lab_T=0.5e-3 * NV_AXES_UNIT[0], sim_field_source="documented",
                reason="0.5 mT documented; direction assumed first NV axis")
    except FileNotFoundError as exc:
        rows.append(_blank_row("harvard", "dataset", str(exc)))

    try:
        filenames = ed.list_borealis_detuning_scan_files()[:max_items]
        if not filenames:
            rows.append(_blank_row("borealis", "dataset", "No detuning scan files found"))
        for filename in filenames:
            scan = ed.load_borealis_detuning_scan(filename)
            rows.append(_blank_row(
                "borealis", filename,
                "Pulsed calibration data: each file sweeps pulse and interpulse duration at one fixed detuning; the simulator models CW ODMR",
                len(scan["Photoluminescence (Arb. Units)"]),
            ))
    except FileNotFoundError as exc:
        rows.append(_blank_row("borealis", "dataset", str(exc)))

    for index in (0, 12, 24)[:max_items]:
        item = f"f{index}_odmr.csv"
        try:
            freq_hz, signal = load_experimental_odmr(str(ed.DATA_DIR / "zenodo_odmr" / item))
            add("zenodo_odmr", item, freq_hz, signal, exp_freq_unit="Hz")
        except FileNotFoundError as exc:
            rows.append(_blank_row("zenodo_odmr", item, str(exc)))

    rows.append(_blank_row("darus_gradiometry", "dataset",
                           "Allan-deviation tables, not spectra"))
    return rows


def _clean(value):
    """Convert NumPy scalars and nonfinite metrics to strict JSON values."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _markdown(rows: list[dict]) -> str:
    lines = ["# External ODMR validation", "",
             "| " + " | ".join(ROW_KEYS) + " |",
             "| " + " | ".join("---" for _ in ROW_KEYS) + " |"]
    for row in rows:
        cells = []
        for key in ROW_KEYS:
            value = row[key]
            if isinstance(value, list):
                value = ", ".join(f"{x:.6g}" for x in value)
            cells.append(str(value if value is not None else "—").replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "## How to read this", "",
        "overlap_ok false means the comparison is not valid; contrast_ratio far from 1 "
        "means the simulation's contrast model disagrees even when the shape agrees.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/experimental"))
    parser.add_argument("--out-dir", type=Path, default=Path("docs"))
    parser.add_argument("--max-items-per-dataset", type=int, default=3)
    args = parser.parse_args()
    if args.max_items_per_dataset < 1:
        parser.error("--max-items-per-dataset must be positive")
    started = time.perf_counter()
    data_dir = args.data_dir.resolve()
    out_dir = args.out_dir.resolve()
    ed.DATA_DIR = data_dir
    adapter = SimOSAdapter(SimulationConfig())
    rows = _dataset_rows(adapter, args.max_items_per_dataset)
    file_counts = {name: sum(p.is_file() for p in (data_dir / dirname).rglob("*"))
                   for name, dirname in DATASET_DIRS.items()}
    payload = _clean({
        "date": date.today().isoformat(),
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "dataset_dir": str(data_dir),
        "per_dataset_file_counts": file_counts,
        "wall_s": time.perf_counter() - started,
        "rows": rows,
    })
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "external_validation_results.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (out_dir / "external_validation_results.md").write_text(
        _markdown(payload["rows"]), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
